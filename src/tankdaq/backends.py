"""Independent producers. Importing this module never imports NI-DAQmx."""
from __future__ import annotations
import math
from pathlib import Path
import queue
import threading
import time
import traceback
from typing import Any
import numpy as np
from .models import AnalogBlock, Clock, CounterPoint, StreamInfo, WorkerFault, WorkerOutcome

class Worker:
    def __init__(self, name: str):
        self.name = name
        self.outcome = WorkerOutcome(name)

    def prepare(self) -> None:
        pass

    def close(self) -> None:
        self.outcome.closed = True

    @staticmethod
    def publish(out: queue.Queue, item: Any) -> None:
        try:
            out.put(item, timeout=1.0)
        except queue.Full as exc:
            raise RuntimeError("Acquisition queue is full; aborting instead of silently dropping data") from exc

    def produce(self, clock: Clock, out: queue.Queue, stop: threading.Event) -> None:
        raise NotImplementedError

    def guarded(self, clock: Clock, out: queue.Queue, faults: queue.SimpleQueue,
                stop: threading.Event) -> None:
        try:
            if not stop.is_set():
                self.produce(clock, out, stop)
        except Exception as exc:
            faults.put(WorkerFault(self.name, str(exc), traceback.format_exc()))
            stop.set()
        finally:
            try:
                self.close()
            except Exception as exc:
                faults.put(WorkerFault(self.name, "Task close failed: "+str(exc), traceback.format_exc()))
                stop.set()

class SimAnalog(Worker):
    def __init__(self, stream: str, cfg: dict[str, Any], seed: int = 742):
        super().__init__(stream)
        self.cfg, self.rng = cfg, np.random.default_rng(seed + (0 if stream=="rtd" else 1))

    def produce(self, clock: Clock, out: queue.Queue, stop: threading.Event) -> None:
        self.outcome.started = True
        rate = self.cfg["sampling"][self.name+"_hz"]
        t0 = clock.elapsed()
        self.outcome.metadata = dict(actual_rate_hz=rate, requested_rate_hz=rate,
                                     t0_est_s=t0, simulated=True, timing="synthetic_sample_grid")
        self.publish(out, StreamInfo(self.name, self.outcome.metadata))
        index = 0
        while not stop.is_set():
            # Simulate a sample period, not a claim about actual NI conversion delay.
            due = t0+(index+1)/rate
            if stop.wait(max(0, due-clock.elapsed())):
                break
            n = min(self.cfg["sampling"]["max_block_samples"], max(1, int((clock.elapsed()-t0)*rate)-index))
            times = np.arange(index, index+n)/rate
            if self.name == "rtd":
                base = np.array([29.0, 25.0, 21.3, 21.0])[:, None]
                values = base + 0.2*np.sin(times/15)[None, :] + self.rng.normal(0, .015, (4,n))
            else:
                # Synthetic VOLTAGES: no fictitious sensor specifications are used here.
                base = np.array([2.92, 3.6, 3.47, 1.0, .85, 1.6, 2.6])[:, None]
                values = base + .012*np.sin(times/7)[None, :] + self.rng.normal(0, .001, (7,n))
            self.publish(out, AnalogBlock(self.name,index,rate,t0,clock.elapsed(),values,True))
            index += n
            self.outcome.samples_per_channel = index

class SimCounter(Worker):
    def __init__(self, cfg: dict[str, Any]):
        super().__init__("counter")
        self.cfg = cfg

    def produce(self, clock: Clock, out: queue.Queue, stop: threading.Event) -> None:
        self.outcome.started = True
        t0 = clock.elapsed()
        self.outcome.metadata = dict(simulated=True, nominal_simulated_frequency_hz=15.0,
                                     timing="host_poll_midpoint", t0_est_s=t0)
        self.publish(out, StreamInfo("counter", self.outcome.metadata))
        index = 0
        while not stop.is_set():
            t = clock.elapsed()
            count = int(max(0.,t-t0)*15.0) % (1<<32)
            self.publish(out, CounterPoint(index,t,0.,count,True))
            index += 1
            self.outcome.samples_per_channel = index
            due = t0+index/self.cfg["sampling"]["counter_poll_hz"]
            if stop.wait(max(0,due-clock.elapsed())):
                break

def simulation_workers(cfg: dict[str, Any]) -> list[Worker]:
    return [SimAnalog("rtd",cfg), SimAnalog("analog",cfg), SimCounter(cfg)]

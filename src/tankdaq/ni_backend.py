"""NI hardware backend: AI and counter INPUT tasks only. No actuator writes."""
from __future__ import annotations
import math
from pathlib import Path
import queue
import threading
import time
import uuid
from typing import Any
import numpy as np
from .backends import Worker
from .models import AnalogBlock, Clock, CounterPoint, StreamInfo

# Kept behind the backend boundary so all simulation/data tools run without NI.
def api():
    try:
        import nidaqmx
        import nidaqmx.constants as constants
        from nidaqmx.stream_readers import AnalogMultiChannelReader
        from nidaqmx.system import System
    except ImportError as exc:
        raise RuntimeError("Install this project with .[ni] and separately install the NI-DAQmx driver") from exc
    return nidaqmx, constants, AnalogMultiChannelReader, System

def inventory() -> dict[str, Any]:
    _, _, _, System = api()
    try:
        system = System.local()
        ver = system.driver_version
        data: dict[str, Any] = {"driver_version": f"{ver.major_version}.{ver.minor_version}.{ver.update_version}", "devices": []}
        for d in system.devices:
            item: dict[str, Any] = {"name": d.name}
            for prop in ("product_type", "dev_serial_num", "is_simulated", "terminals"):
                try:
                    item[prop] = getattr(d, prop)
                except Exception as exc:
                    item[prop+"_unavailable"] = str(exc)
            for prop in ("ai_physical_chans", "ci_physical_chans"):
                try:
                    item[prop] = [x.name for x in getattr(d,prop)]
                except Exception as exc:
                    item[prop+"_unavailable"] = str(exc)
            data["devices"].append(item)
        return data
    except Exception as exc:
        raise RuntimeError("NI-DAQmx inventory failed. Check driver installation, USB chassis and NI MAX: "+str(exc)) from exc

def verify_inventory(cfg: dict[str, Any], info: dict[str, Any]) -> None:
    devices = {d["name"]:d for d in info["devices"]}
    hw = cfg["hardware"]
    for key, model in (("chassis","9173"),("rtd_module","9217"),("analog_module","9204"),("counter_module","9401")):
        name = hw[key]
        if name not in devices:
            raise RuntimeError(f"Required {key} {name} not found. Available: {list(devices)}")
        d = devices[name]
        if model not in str(d.get("product_type","")):
            raise RuntimeError(f"{name}: expected model {model}, found {d.get('product_type')}")
        if d.get("is_simulated") is not False:
            raise RuntimeError(f"{name}: physical hardware status not verified; NI-MAX simulated devices are refused")
    for stream, key in (("rtd","rtd_module"),("analog","analog_module")):
        available = devices[hw[key]].get("ai_physical_chans", [])
        for ch in cfg[stream]["channels"]:
            if ch["physical"] not in available:
                raise RuntimeError(f"Physical channel missing: {ch['physical']}; available: {available}")
    counters = [ch for d in devices.values() for ch in d.get("ci_physical_chans",[])]
    terms = [t for d in devices.values() for t in d.get("terminals",[])]
    for ch in cfg["counter"]["channels"]:
        if ch["counter_channel"] not in counters:
            raise RuntimeError(f"Counter {ch['counter_channel']} not enumerated. Set the exact available name: {counters}")
        if ch["pulse_terminal"] not in terms:
            raise RuntimeError(f"Pulse terminal {ch['pulse_terminal']} not enumerated. Inspect 'tankdaq devices' PFI terminals")

class NIAnalog(Worker):
    def __init__(self, stream: str, cfg: dict[str, Any], folder: Path):
        super().__init__(stream)
        self.cfg, self.folder, self.task = cfg, folder, None
        self.reader = None
        self.rate = 0.
        self.stopped = False

    def prepare(self) -> None:
        nidaqmx, c, Reader, _ = api()
        self.task = nidaqmx.Task(new_task_name=f"tankdaq_{self.name}_{uuid.uuid4().hex[:8]}")
        try:
            for ch in self.cfg[self.name]["channels"]:
                if self.name == "rtd":
                    r = self.cfg["rtd"]
                    channel = self.task.ai_channels.add_ai_rtd_chan(
                        ch["physical"], name_to_assign_to_channel=ch["raw_name"],
                        min_val=r["measurement_range_c"][0], max_val=r["measurement_range_c"][1],
                        units=c.TemperatureUnits.DEG_C, rtd_type=getattr(c.RTDType,r["type"]),
                        resistance_config=c.ResistanceConfiguration.FOUR_WIRE,
                        current_excit_source=c.ExcitationSource.INTERNAL,
                        current_excit_val=r["excitation_a"], r_0=r["r0_ohm"])
                    channel.ai_adc_timing_mode = getattr(c.ADCTimingMode, r["adc_mode"])
                else:
                    self.task.ai_channels.add_ai_voltage_chan(
                        ch["physical"], name_to_assign_to_channel=ch["raw_name"],
                        terminal_config=c.TerminalConfiguration.DIFF,
                        min_val=ch["daq_range_v"][0], max_val=ch["daq_range_v"][1],
                        units=c.VoltageUnits.VOLTS)
            requested = self.cfg["sampling"][self.name+"_hz"]
            buffer_samples = max(1000, math.ceil(requested*self.cfg["sampling"]["buffer_seconds"]))
            self.task.timing.cfg_samp_clk_timing(requested, sample_mode=c.AcquisitionType.CONTINUOUS,
                                                samps_per_chan=buffer_samples)
            self.task.in_stream.auto_start = False
            self.task.in_stream.over_write = c.OverwriteMode.DO_NOT_OVERWRITE_UNREAD_SAMPLES
            if self.cfg["storage"]["tdms"]:
                # Separate files: no concurrent writers to a shared TDMS file.
                self.task.in_stream.configure_logging(
                    str((self.folder/f"{self.name}_raw.tdms").resolve()),
                    logging_mode=c.LoggingMode.LOG_AND_READ, group_name=self.name,
                    operation=c.LoggingOperation.CREATE)
            # Reserve/commit every task before starting any acquisition.
            self.task.control(c.TaskMode.TASK_COMMIT)
            self.rate = float(self.task.timing.samp_clk_rate)
            if not math.isfinite(self.rate) or self.rate <= 0:
                raise RuntimeError("Driver returned invalid sample-clock rate")
            self.reader = Reader(self.task.in_stream)
            self.outcome.metadata.update(requested_rate_hz=requested,actual_rate_hz=self.rate,
                                         input_buffer_samples=int(self.task.in_stream.input_buf_size),
                                         sample_clock_source=self.task.timing.samp_clk_src,
                                         simulated=False,hardware_synchronized_to_other_tasks=False,
                                         timestamp_basis="host_start_call_midpoint_plus_sample_index_over_rate",
                                         intra_scan_delays_corrected=False,filter_delays_corrected=False)
        except Exception:
            self.close()
            raise

    def _read(self, count: int, index: int, t0: float, clock: Clock, out: queue.Queue) -> int:
        nchan = len(self.cfg[self.name]["channels"])
        buf = np.empty((nchan,count),dtype=np.float64)
        got = int(self.reader.read_many_sample(buf,number_of_samples_per_channel=count,timeout=1.0))
        if got != count:
            raise RuntimeError(f"Short DAQ read: requested {count}, received {got}; refusing silent gaps")
        self.publish(out, AnalogBlock(self.name,index,self.rate,t0,clock.elapsed(),buf,False))
        self.outcome.samples_per_channel += got
        return got

    def produce(self, clock: Clock, out: queue.Queue, stop: threading.Event) -> None:
        before = clock.elapsed()
        self.task.start()
        after = clock.elapsed()
        self.outcome.started = True
        t0 = (before+after)/2
        self.outcome.metadata.update(start_call_begin_s=before,start_call_end_s=after,t0_est_s=t0,
                                     start_call_span_s=after-before)
        self.publish(out, StreamInfo(self.name, dict(self.outcome.metadata)))
        index, last_data = 0, time.monotonic()
        while not stop.is_set():
            available = int(self.task.in_stream.avail_samp_per_chan)
            if available:
                n = min(available,self.cfg["sampling"]["max_block_samples"])
                index += self._read(n,index,t0,clock,out)
                last_data = time.monotonic()
            elif time.monotonic()-last_data > self.cfg["sampling"]["idle_timeout_s"]:
                raise TimeoutError(f"No {self.name} samples within idle_timeout_s")
            else:
                stop.wait(0.02)
        # Normal stop: stop hardware first, then drain readable buffered samples.
        # auto_start=False prevents an accidental restart during this drain.
        self.task.stop()
        self.stopped = True
        self.outcome.metadata["stopped_at_s"] = clock.elapsed()
        deadline = time.monotonic()+3.0
        while True:
            available = int(self.task.in_stream.avail_samp_per_chan)
            if not available:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Drain timed out; buffered tail may be incomplete")
            index += self._read(min(available,self.cfg["sampling"]["max_block_samples"]),index,t0,clock,out)
        self.outcome.metadata["buffered_tail_drained"] = True

    def close(self) -> None:
        if self.task is not None:
            task, self.task = self.task, None
            # DAQmx ClearTask releases a running task as well as its resources.
            task.close()
        self.outcome.closed = True

class NICounter(Worker):
    def __init__(self, cfg: dict[str, Any]):
        super().__init__("counter")
        self.cfg = cfg
        self.tasks: list[Any] = []

    def prepare(self) -> None:
        nidaqmx, c, _, _ = api()
        edge = getattr(c.Edge, self.cfg["counter"]["edge"])
        try:
            for ch_cfg in self.cfg["counter"]["channels"]:
                task = nidaqmx.Task(new_task_name=f"tankdaq_counter_{ch_cfg['name']}_{uuid.uuid4().hex[:6]}")
                ch = task.ci_channels.add_ci_count_edges_chan(
                    ch_cfg["counter_channel"], name_to_assign_to_channel=ch_cfg["raw_name"],
                    edge=edge, initial_count=0, count_direction=c.CountDirection.COUNT_UP)
                ch.ci_count_edges_term = ch_cfg["pulse_terminal"]
                task.in_stream.auto_start = False
                task.control(c.TaskMode.TASK_COMMIT)
                self.tasks.append(task)
            self.outcome.metadata.update(
                channels=[c["name"] for c in self.cfg["counter"]["channels"]],
                physical_counters=[c["counter_channel"] for c in self.cfg["counter"]["channels"]],
                terminals=[c["pulse_terminal"] for c in self.cfg["counter"]["channels"]],
                timing="hardware_cumulative_counts_host_poll_midpoints",
                simulated=False, hardware_sample_clock=False)
        except Exception:
            self.close()
            raise

    def produce(self, clock: Clock, out: queue.Queue, stop: threading.Event) -> None:
        for task in self.tasks:
            task.start()  # Start exactly once: successive reads are cumulative.
        self.outcome.started = True
        t0 = clock.elapsed()
        self.outcome.metadata["start_observed_s"] = t0
        self.publish(out, StreamInfo("counter", dict(self.outcome.metadata)))
        index = 0
        channels = self.cfg["counter"]["channels"]
        while not stop.is_set():
            before = clock.elapsed()
            counts = [int(task.read(timeout=1.0)) for task in self.tasks]
            after = clock.elapsed()
            midpoint = (before + after) / 2
            duration = after - before
            for ch_cfg, count in zip(channels, counts):
                self.publish(out, CounterPoint(index, ch_cfg["name"], midpoint, duration, count, False))
            index += 1
            self.outcome.samples_per_channel = index
            due = t0 + index / self.cfg["sampling"]["counter_poll_hz"]
            # Never invent fixed read times: the actual midpoint is logged.
            if stop.wait(max(0, due - clock.elapsed())):
                break
        for task in self.tasks:
            task.stop()

    def close(self) -> None:
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            try:
                task.close()
            except Exception:
                pass
        self.outcome.closed = True

def hardware_workers(cfg: dict[str, Any], folder: Path) -> tuple[list[Worker], dict[str, Any]]:
    info = inventory()
    verify_inventory(cfg,info)
    return [NIAnalog("rtd",cfg,folder),NIAnalog("analog",cfg,folder),NICounter(cfg)],info

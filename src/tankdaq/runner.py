"""Run coordinator: bounded queues, one writer, clean stop, failure provenance."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import shutil
import signal
import threading
import time
import traceback
from typing import Any
import uuid
import yaml
from .backends import simulation_workers
from .config import ConfigError, validate
from .models import Clock, WorkerFault
from .storage import RunStore, json_dump, sha256_file

def run(cfg: dict[str, Any], config_path: Path, output_root: Path, *, backend: str,
        duration_s: float | None, raw_only: bool, acknowledge_wiring: bool,
        quiet: bool = False, stop_event: threading.Event | None = None) -> tuple[Path, str]:
    validate(cfg,backend=backend,raw_only=raw_only,acknowledge_wiring=acknowledge_wiring)
    if duration_s is not None and (not math.isfinite(duration_s) or duration_s <= 0):
        raise ConfigError("duration must be positive; omit it for a continuous run")
    output_root.mkdir(parents=True,exist_ok=True)
    minimum_bytes = int(cfg["storage"]["min_free_mb"]*1024*1024)
    if shutil.disk_usage(output_root).free < minimum_bytes:
        raise RuntimeError("Insufficient free disk space for a run")
    # Unique run directory. A previous experiment is never overwritten.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    folder = output_root / f"{stamp}_{backend.upper()}_{cfg['run']['label']}_{uuid.uuid4().hex[:6]}"
    folder.mkdir()
    shutil.copy2(config_path,folder/"config_original.yaml")
    (folder/"config_resolved.yaml").write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
    (folder/"RUNNING").write_text("Acquisition is not finalized. Do not move this directory.\n",encoding="utf-8")
    clock = Clock.now()
    store = RunStore(folder,cfg,clock,backend,raw_only)
    store.meta["original_config_sha256"] = sha256_file(folder/"config_original.yaml")
    store.meta["requested_duration_s"] = duration_s
    store.meta["external_impeller"] = cfg["external"]
    stop = stop_event if stop_event is not None else threading.Event()
    out: queue.Queue = queue.Queue(maxsize=cfg["sampling"]["queue_blocks"])
    fault_queue: queue.SimpleQueue = queue.SimpleQueue()
    failures: list[dict[str, Any]] = []
    workers,threads = [],[]
    signal_seen = False
    writer_healthy = True
    old_handlers: dict[int, Any] = {}
    reason = "completed"
    log = (folder/"acquisition.log").open("a",encoding="utf-8",buffering=1)

    def log_line(message: str) -> None:
        log.write(datetime.now(timezone.utc).isoformat()+" "+message+"\n")

    def handle_signal(signum, _frame):
        nonlocal signal_seen
        signal_seen = True
        stop.set()

    def record_fault(source: str, message: str, trace: str = "") -> None:
        nonlocal writer_healthy
        failure = dict(stream=source,message=message,traceback=trace)
        failures.append(failure)
        try:
            log_line("ERROR "+source+": "+message)
        except OSError:
            pass
        if writer_healthy:
            try:
                store.event("ERROR",source,message)
            except Exception:
                writer_healthy = False
        stop.set()

    try:
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT,signal.SIGTERM):
                old_handlers[sig] = signal.signal(sig,handle_signal)
        log_line(f"backend={backend} raw_only={raw_only}")
        if not quiet:
            print(f"Run directory: {folder.resolve()}",flush=True)
            print("SIMULATION - NOT EXPERIMENTAL DATA" if backend=="sim" else "NI hardware acquisition; no actuator control",flush=True)
        if backend == "ni":
            from .ni_backend import hardware_workers
            workers,info = hardware_workers(cfg,folder)
            store.meta["ni_inventory"] = info
            json_dump(folder/"devices.json",info)
        else:
            workers = simulation_workers(cfg)
        # Construct and commit all resources before any of the tasks can start.
        for worker in workers:
            worker.prepare()
        # Acquisition t=0 is now fixed, after preparation, for all output streams.
        clock = Clock.now()
        store.clock = clock
        store.meta["anchor"] = asdict(clock)
        store.meta["status"] = "running"
        store.event("INFO","coordinator","All tasks prepared. Starting independent producers")
        store.save_metadata()
        for worker in workers:
            thread = threading.Thread(target=worker.guarded,args=(clock,out,fault_queue,stop),
                                      name=f"tankdaq-{worker.name}",daemon=True)
            thread.start()
            threads.append(thread)
        last_report,last_disk = 0.,0.
        stopping_since: float | None = None
        while True:
            now = clock.elapsed()
            if duration_s is not None and now >= duration_s:
                stop.set()
            if signal_seen:
                reason = "interrupted"
            if stop.is_set() and stopping_since is None:
                stopping_since = time.monotonic()
            while not fault_queue.empty():
                fault: WorkerFault = fault_queue.get()
                record_fault(fault.stream,fault.message,fault.traceback)
            try:
                item = out.get(timeout=.05)
                if writer_healthy:
                    try:
                        store.write(item)
                    except Exception as exc:
                        writer_healthy = False
                        record_fault("writer",str(exc),traceback.format_exc())
            except queue.Empty:
                pass
            if now-last_disk >= 5.:
                last_disk = now
                if shutil.disk_usage(folder).free < minimum_bytes:
                    record_fault("disk","Free disk space dropped below configured threshold")
            if not quiet and now-last_report >= 5.:
                last_report = now
                print(f"{now:7.1f}s  rows: RTD={store.rows['rtd']} analog={store.rows['analog']} counter={store.rows['counter']}",flush=True)
            alive = any(t.is_alive() for t in threads)
            if not alive and out.empty():
                break
            if stopping_since is not None and time.monotonic()-stopping_since > 15.:
                record_fault("coordinator","Worker shutdown exceeded 15 s; run is incomplete")
                break
        for t in threads:
            t.join(timeout=.2)
        while not fault_queue.empty():
            fault = fault_queue.get()
            record_fault(fault.stream,fault.message,fault.traceback)
        if not stop.is_set():
            record_fault("coordinator","All workers exited before a stop was requested")
        for worker in workers:
            if worker.outcome.samples_per_channel == 0:
                record_fault(worker.name,"No samples acquired on this required stream")
    except Exception as exc:
        record_fault("coordinator",str(exc),traceback.format_exc())
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2.)
        # Never close a task from the writer thread while its reader still uses it.
        active = {t.name for t in threads if t.is_alive()}
        for worker in workers:
            if f"tankdaq-{worker.name}" not in active and not worker.outcome.closed:
                try:
                    worker.close()
                except Exception as exc:
                    record_fault(worker.name,"Cleanup failed: "+str(exc))
        while not out.empty():
            item = out.get_nowait()
            if writer_healthy:
                try:
                    store.write(item)
                except Exception as exc:
                    writer_healthy = False
                    record_fault("writer","Final drain: "+str(exc))
        while not fault_queue.empty():
            fault = fault_queue.get()
            record_fault(fault.stream,fault.message,fault.traceback)
        # A signal can arrive during the last queue read, after the loop
        # checked signal_seen. Classify interruption again at finalization.
        status = "failed" if failures else ("interrupted" if signal_seen else reason)
        outcomes = [asdict(w.outcome) for w in workers]
        try:
            store.finalize(status,failures,outcomes)
        except Exception as exc:
            status = "failed"
            failures.append(dict(stream="finalize",message=str(exc)))
            try:
                store.db.close()
            except Exception:
                pass
            # A sidecar remains useful if the SQL writer cannot finalize.
            try:
                json_dump(folder/"FAILURE.json",dict(status=status,faults=failures,workers=outcomes))
            except OSError:
                pass
        for sig,handler in old_handlers.items():
            signal.signal(sig,handler)
        try:
            (folder/"RUNNING").unlink(missing_ok=True)
            (folder/status.upper()).write_text(status+"\n",encoding="utf-8")
            log_line("Final status: "+status)
        finally:
            log.close()
    if not quiet:
        print(f"Status: {status}. Data: {folder.resolve()}",flush=True)
        for f in failures:
            print(f"ERROR [{f['stream']}]: {f['message']}",flush=True)
    return folder,status

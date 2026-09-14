"""Single-writer, transactional storage. No database work occurs in DAQ threads."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sqlite3
import time
from typing import Any
from . import __version__
from .models import AnalogBlock, Clock, CounterPoint, StreamInfo
from .scaling import FlowWindow, convert_voltage

SCHEMA = '''
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE channels (
 name TEXT PRIMARY KEY, raw_name TEXT NOT NULL, stream TEXT NOT NULL,
 physical_channel TEXT NOT NULL, unit TEXT NOT NULL, definition_json TEXT NOT NULL);
CREATE TABLE samples (
 stream TEXT NOT NULL, sample_index INTEGER NOT NULL, channel TEXT NOT NULL,
 physical_channel TEXT NOT NULL, device_time_s REAL NOT NULL,
 t_rel_s_est REAL NOT NULL, utc_ns_est INTEGER NOT NULL, read_rel_s REAL NOT NULL,
 raw_value REAL, raw_unit TEXT NOT NULL, value REAL, unit TEXT NOT NULL,
 quality TEXT NOT NULL, simulated INTEGER NOT NULL,
 PRIMARY KEY (stream, sample_index, channel));
CREATE TABLE counter (
 poll_index INTEGER PRIMARY KEY, t_rel_s_est REAL NOT NULL, utc_ns_est INTEGER NOT NULL,
 read_duration_s REAL NOT NULL, count_raw INTEGER NOT NULL, count_unwrapped INTEGER NOT NULL,
 window_start_s REAL NOT NULL, window_end_s REAL NOT NULL, window_counts INTEGER NOT NULL,
 frequency_hz REAL, flow_l_min REAL, one_count_resolution_l_min REAL,
 quality TEXT NOT NULL, simulated INTEGER NOT NULL);
CREATE TABLE events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, utc_ns INTEGER NOT NULL,
 t_rel_s REAL, severity TEXT NOT NULL, source TEXT NOT NULL, message TEXT NOT NULL);
'''

def json_dump(path: Path, data: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False, default=str)+"\n", encoding="utf-8")
    temporary.replace(path)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024*1024), b""):
            h.update(part)
    return h.hexdigest()

def environment() -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for package in ("numpy", "PyYAML", "nidaqmx", "pyarrow"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    root = Path(__file__).parent
    source_hash = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        source_hash.update(path.name.encode())
        source_hash.update(path.read_bytes())
    return dict(tankdaq=__version__, python=platform.python_version(), platform=platform.platform(),
                packages=versions, source_sha256=source_hash.hexdigest())

class RunStore:
    def __init__(self, folder: Path, cfg: dict[str, Any], clock: Clock, backend: str, raw_only: bool):
        self.folder, self.cfg, self.clock = folder, cfg, clock
        self.raw_only = raw_only
        self.db = sqlite3.connect(folder/"measurements.sqlite", timeout=10)
        self.db.executescript(SCHEMA)
        self.last_commit = time.monotonic()
        self.flow = FlowWindow(cfg["sampling"]["flow_window_s"], cfg["counter"]["hz_per_l_min"])
        self.rows = {"rtd": 0, "analog": 0, "counter": 0}
        self.next_index = {"rtd": 0, "analog": 0, "counter": 0}
        self.meta = dict(run_id=folder.name, backend=backend, simulated=backend=="sim",
                         raw_only=raw_only, status="initializing", anchor=asdict(clock),
                         environment=environment(), config=cfg, streams={}, row_counts=self.rows,
                         timing_policy="Independent hardware-timed AI tasks; host-estimated start offsets. "
                         "Counter polls have host-midpoint timestamps. No cross-module synchronization guarantee.")
        for stream in ("rtd", "analog"):
            for ch in cfg[stream]["channels"]:
                self.db.execute("INSERT INTO channels VALUES (?,?,?,?,?,?)",
                                (ch["name"], ch["raw_name"], stream, ch["physical"],
                                 ch.get("unit", "degC"), json.dumps(ch)))
        self.save_metadata()

    def event(self, severity: str, source: str, message: str) -> None:
        self.db.execute("INSERT INTO events(utc_ns,t_rel_s,severity,source,message) VALUES(?,?,?,?,?)",
                        (time.time_ns(), self.clock.elapsed(), severity, source, message))

    def save_metadata(self) -> None:
        for key, value in self.meta.items():
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)", (key, json.dumps(value, default=str)))
        self.db.commit()
        self.last_commit = time.monotonic()
        json_dump(self.folder/"metadata.json", self.meta)

    def write(self, item: AnalogBlock | CounterPoint | StreamInfo) -> None:
        if isinstance(item, StreamInfo):
            self.meta["streams"][item.stream] = item.info
            self.event("INFO", item.stream, json.dumps(item.info, default=str))
            self.save_metadata()
            return
        if isinstance(item, AnalogBlock):
            channels = self.cfg[item.stream]["channels"]
            if item.values.ndim != 2 or item.values.shape[0] != len(channels):
                raise ValueError("DAQ block shape does not match channel configuration")
            if item.first_index != self.next_index[item.stream]:
                raise ValueError(f"Sample-index gap/duplicate in {item.stream}")
            n = item.values.shape[1]
            rows = []
            for j in range(n):
                index = item.first_index+j
                relative = item.t0_est_s+index/item.rate_hz
                for k, ch in enumerate(channels):
                    raw = float(item.values[k, j])
                    if item.stream == "rtd":
                        value = raw*ch["gain"]+ch["offset_c"] if math.isfinite(raw) else None
                        quality = "DAQMX_RTD_LINEARIZATION" if value is not None else "NONFINITE_INPUT"
                        if math.isfinite(raw) and not self.cfg["rtd"]["measurement_range_c"][0] <= raw <= self.cfg["rtd"]["measurement_range_c"][1]:
                            quality += "|OUTSIDE_RTD_EXPECTED_RANGE"
                        raw_unit, unit = "degC", "degC"
                    else:
                        result = convert_voltage(raw, ch, raw_only=self.raw_only)
                        value, quality = result.value, result.quality
                        raw_unit, unit = "V", ch["unit"]
                    if item.simulated:
                        quality = "SIMULATED|"+quality
                    rows.append((item.stream, index, ch["name"], ch["physical"], index/item.rate_hz,
                                 relative, self.clock.epoch_for(relative), item.read_rel_s,
                                 raw if math.isfinite(raw) else None, raw_unit, value, unit,
                                 quality, int(item.simulated)))
            self.db.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.next_index[item.stream] += n
            self.rows[item.stream] += len(rows)
        else:
            if item.index != self.next_index["counter"]:
                raise ValueError("Counter-poll index gap/duplicate")
            c = self.cfg["counter"]
            result = self.flow.update(item.t_rel_s, item.count, scale_confirmed=c["calibration_confirmed"],
                                      raw_only=self.raw_only, valid_range=c["valid_flow_l_min"])
            quality = ("SIMULATED|" if item.simulated else "")+result["quality"]
            self.db.execute("INSERT INTO counter VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (item.index, item.t_rel_s, self.clock.epoch_for(item.t_rel_s), item.read_duration_s,
                             item.count, result["count_unwrapped"], result["window_start_s"], result["window_end_s"],
                             result["window_counts"], result["frequency_hz"], result["flow_l_min"],
                             result["one_count_resolution_l_min"], quality, int(item.simulated)))
            self.next_index["counter"] += 1
            self.rows["counter"] += 1
        if time.monotonic()-self.last_commit >= self.cfg["storage"]["commit_interval_s"]:
            self.db.commit()
            self.last_commit = time.monotonic()

    def finalize(self, status: str, faults: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> None:
        self.meta.update(status=status, ended_utc=datetime.now(timezone.utc).isoformat(),
                         duration_s=self.clock.elapsed(), faults=faults, workers=outcomes,
                         row_counts=dict(self.rows), samples_per_channel=dict(self.next_index))
        self.event("ERROR" if status=="failed" else "INFO", "coordinator", "Run ended: "+status)
        self.save_metadata()
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close()

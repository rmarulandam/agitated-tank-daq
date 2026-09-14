"""Post-processing and read-only monitoring; these never access DAQ hardware."""
from __future__ import annotations
import csv
import json
import math
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Any
import uuid
from .storage import json_dump,sha256_file

TABLES = ("samples","counter","events","channels","metadata")

def connect_readonly(folder: Path) -> sqlite3.Connection:
    path = (folder/"measurements.sqlite").resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    db = sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=10)
    db.row_factory = sqlite3.Row
    return db

def export_run(folder: Path, fmt: str, output: Path | None = None) -> Path:
    if (folder/"RUNNING").exists():
        raise RuntimeError("Stop/finalize acquisition before exporting a consistent complete run")
    if fmt not in {"csv","parquet"}:
        raise ValueError("format must be csv or parquet")
    if fmt == "parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError("Parquet export requires: python -m pip install '.[parquet]'") from exc
    output = output or folder/f"export_{fmt}_{uuid.uuid4().hex[:6]}"
    output.mkdir(parents=True,exist_ok=False)
    db = connect_readonly(folder)
    try:
        for name in TABLES:
            # Table names are from the constant allow-list, never user SQL.
            query = f"SELECT * FROM {name}"
            if name=="samples": query += " ORDER BY stream,sample_index,channel"
            elif name=="counter": query += " ORDER BY poll_index"
            cursor = db.execute(query)
            columns = [x[0] for x in cursor.description]
            if fmt == "csv":
                with (output/f"{name}.csv").open("w",encoding="utf-8",newline="") as fh:
                    w=csv.writer(fh)
                    w.writerow(columns)
                    while rows:=cursor.fetchmany(10000):
                        w.writerows(rows)
            else:
                # Explicit types prevent an all-null first batch from fixing a null schema.
                sqlcols = db.execute(f"PRAGMA table_info({name})").fetchall()
                schema = pa.schema([(r["name"], {"TEXT":pa.string(),"REAL":pa.float64(),"INTEGER":pa.int64()}[r["type"]]) for r in sqlcols])
                with pq.ParquetWriter(output/f"{name}.parquet",schema,compression="zstd") as writer:
                    while rows:=cursor.fetchmany(10000):
                        table = pa.Table.from_pylist([dict(r) for r in rows],schema=schema)
                        writer.write_table(table)
        json_dump(output/"export_manifest.json",dict(source_run=folder.resolve(),format=fmt,
                 source_database_sha256=sha256_file(folder/"measurements.sqlite"),
                 notes="Long-form samples; raw values, quality flags and independent stream times are preserved."))
    finally:
        db.close()
    return output

def inspect_run(folder: Path) -> dict[str, Any]:
    db=connect_readonly(folder)
    try:
        info={r["key"]:json.loads(r["value_json"]) for r in db.execute("SELECT * FROM metadata")}
        summary = {"status":info.get("status"),"run_id":info.get("run_id"),"simulated":info.get("simulated"),
                   "raw_only":info.get("raw_only"),"integrity":db.execute("PRAGMA quick_check").fetchone()[0]}
        summary["channel_samples"] = [dict(r) for r in db.execute(
            "SELECT stream,channel,count(*) AS n,min(sample_index) AS first_index,max(sample_index) AS last_index FROM samples GROUP BY stream,channel")]
        summary["counter_polls"] = db.execute("SELECT count(*) FROM counter").fetchone()[0]
        summary["faults"] = info.get("faults",[])
        return summary
    finally:
        db.close()

def watch(folder: Path,interval: float=2.0,once: bool=False) -> None:
    if not math.isfinite(interval) or interval<=0:
        raise ValueError("Monitor interval must be positive")
    db=connect_readonly(folder)
    try:
        names = [r[0] for r in db.execute("SELECT name FROM channels ORDER BY stream,name")]
        while True:
            print("\n"+time.strftime("%H:%M:%S")+" | "+folder.name)
            # A display-only connection, deliberately independent of DAQ task ownership.
            for name in names:
                row = db.execute("SELECT t_rel_s_est,raw_value,raw_unit,value,unit,quality FROM samples WHERE channel=? ORDER BY rowid DESC LIMIT 1",(name,)).fetchone()
                if row:
                    value = "unscaled" if row["value"] is None else f"{row['value']:.5g} {row['unit']}"
                    raw = "null" if row["raw_value"] is None else f"{row['raw_value']:.5g}"
                    print(f"{name:22} {value:20} raw={raw:10} {row['raw_unit']:5} {row['quality']}")
            flow=db.execute("SELECT * FROM counter ORDER BY poll_index DESC LIMIT 1").fetchone()
            if flow:
                print("water pulses:",flow["count_raw"],"frequency:",flow["frequency_hz"],"flow L/min:",flow["flow_l_min"],flow["quality"])
            if once: break
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()

def add_note(folder: Path,message: str) -> None:
    path=folder/"measurements.sqlite"
    if not path.exists(): raise FileNotFoundError(path)
    if not message.strip(): raise ValueError("A nonempty note is required")
    db=sqlite3.connect(path,timeout=10)
    try:
        anchor=json.loads(db.execute("SELECT value_json FROM metadata WHERE key='anchor'").fetchone()[0])
        now=time.time_ns()
        # Cross-process manual notes use wall-clock offset, explicitly identified.
        db.execute("INSERT INTO events(utc_ns,t_rel_s,severity,source,message) VALUES(?,?,?,?,?)",
                   (now,(now-anchor["epoch_ns"])/1e9,"INFO","operator_wall_clock",message))
        db.commit()
    finally:
        db.close()

def attach_rpm(folder: Path, source: Path, alignment_note: str) -> Path:
    if (folder/"RUNNING").exists():
        raise RuntimeError("Attach external RPM after stopping the run")
    if not (folder/"measurements.sqlite").exists(): raise FileNotFoundError(folder)
    if not alignment_note.strip(): raise ValueError("Explain how external timestamps align with DAQ t=0")
    with source.open(encoding="utf-8-sig",newline="") as fh:
        reader=csv.DictReader(fh)
        required={"t_rel_s","n_impeller_rpm","method","uncertainty_rpm"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("RPM CSV columns must include "+", ".join(sorted(required)))
        previous=-math.inf
        count=0
        for row in reader:
            t,rpm=float(row["t_rel_s"]),float(row["n_impeller_rpm"])
            if not math.isfinite(t) or not math.isfinite(rpm) or t<0 or rpm<0 or t<=previous:
                raise ValueError("RPM timestamps must be finite, nonnegative and increasing; RPM must be finite and nonnegative")
            if not row["method"].strip(): raise ValueError("Every external RPM row requires its calculation method")
            if row["uncertainty_rpm"].strip():
                u=float(row["uncertainty_rpm"])
                if not math.isfinite(u) or u<0: raise ValueError("RPM uncertainty must be nonnegative or blank")
            previous=t;count+=1
        if count==0: raise ValueError("RPM CSV contains no records")
    target=folder/"external_rpm"
    target.mkdir(exist_ok=False)
    shutil.copy2(source,target/"record.csv")
    json_dump(target/"provenance.json",dict(source_file=source.name,source_sha256=sha256_file(source),
              records=count,acquisition="external_calculation_not_cDAQ",alignment_note=alignment_note,
              joined_to_samples=False,interpolation_applied=False))
    return target

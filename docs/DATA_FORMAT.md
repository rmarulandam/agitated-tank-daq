# Stored data

## measurements.sqlite

`channels` stores the channel name, stream (`rtd`, `analog`, or `counter`), physical channel, unit and the exact channel definition JSON. `samples` stores the four RTD and seven analog channels in long form. Its primary key is `(stream, sample_index, channel)`. Within each stream the writer enforces contiguous block indices.

The `channel` field in `samples` matches the channel `name` in the `channels` table. `raw_value` is V for NI-9204, and **DAQmx-linearized degC** for NI-9217. No resistance or ADC-code capture is claimed. `value` contains an engineering conversion, or SQL NULL when scaling is unconfirmed/raw-only. RTD configured gain and offset are applied on top of the DAQmx temperature. `raw_value` remains unchanged. NaN/infinite inputs are stored as NULL with `NONFINITE_INPUT`, rather than ambiguous nonstandard JSON/SQLite NaNs.

`counter` contains one row per counter channel (`water_flow_in`, `water_flow_out`, `impeller_rpm`) per host poll, with primary key `(poll_index, channel)`: channel name, physical counter, pulse terminal, poll timestamp, read duration, raw count, unwrapped count relative to the first snapshot, actual rolling-window timestamps/counts, estimated `frequency_hz`, confirmed `value` (`L/min` or `rpm`), `unit`, `one_count_resolution` and `quality`. The initial row for each channel has no frequency/value. Subsequent warm-up rows are estimates over a short, explicitly recorded window. No-pulse rows are marked as ambiguous zero-rate/signal-loss observations.

`metadata` contains JSON values for configuration, environment/package versions, source-code hash, inventory, actual stream settings, clock anchor, run status, worker outcomes and errors. `metadata.json` mirrors these values at initialization/stream configuration/finalization; per-sample row counts in that file are finalized at run end. `events` includes runtime configuration/error records and operator notes. `acquisition.log` is a human-readable supplementary log.

## Quality strings

Multiple flags are joined with `|`. `SIMULATED` is attached to all simulated samples. `OK` means that an established transfer function was applied and nominal electrical limits were not exceeded; it is **not** an overall calibration certificate or proof of physical validity.

`RAW_ONLY`, `UNCONFIRMED_SCALE`, `AT_DAQ_LIMIT`, `OUTSIDE_NOMINAL_SIGNAL`, `NONFINITE_INPUT`, `DAQMX_RTD_LINEARIZATION`, and `OUTSIDE_RTD_EXPECTED_RANGE` describe sample-conversion conditions. Counter flags include `WARMUP`, `NO_PULSES_FLOW_OR_SIGNAL_LOSS`, and `OUTSIDE_SENSOR_FLOW_RANGE`.

Flags are data diagnostics, not safety-interlock commands. Out-of-range finite readings are retained, never clipped to a plausible endpoint. No missing value is replaced with the last valid sample.

## Other files

Real NI runs optionally contain `rtd_raw.tdms` and `analog_raw.tdms` from DAQmx LOG_AND_READ. They are separate per task; their channel scales should be interpreted with NI-aware TDMS tooling. The SQLite file is the common application-level record across all streams. The simulator produces SQLite but not TDMS.

A completed run has a `COMPLETED`, `INTERRUPTED` or `FAILED` status marker. A leftover `RUNNING` marker means the process did not finalize. On exceptional finalization failure, a `FAILURE.json` sidecar is attempted. Full recovery from power loss, filesystem failure or disconnected storage cannot be guaranteed.

CSV/Parquet export writes all five database tables (`samples`, `counter`, `events`, `channels`, `metadata`) and an `export_manifest.json` into a dedicated subfolder (`export_csv_<hash>/` or `export_parquet_<hash>/`).

Exports can occur in two ways:
1. **Automatic Export upon Finalization:** When `auto_export_csv: true` or `auto_export_parquet: true` is configured in `storage:`, the runner automatically exports the tables immediately after the database writer has finalized and the `RUNNING` sentinel is cleared.
2. **Manual Post-Run Export:** Execute `tankdaq export <run_folder> --format csv` (or `--format parquet`) at any time on a finalized run folder.

Exports do not alter the source database, rescale old measurements, infer missing calibrations, or synchronize streams. An export is refused while `RUNNING` exists. A note added later changes the database; prior exported copies remain snapshots of the earlier database state.

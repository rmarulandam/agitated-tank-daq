# Stored data

## measurements.sqlite

`channels` stores the engineering name, raw channel name, stream, physical channel, unit and the exact channel definition JSON. `samples` stores the four RTD and seven analog channels in long form. Its primary key is `(stream, sample_index, channel)`. Within each stream the writer enforces contiguous block indices.

The `channel` field is the engineering identifier; its associated `raw_name` is in the `channels` table. `raw_value` is V for NI-9204, and **DAQmx-linearized degC** for NI-9217. No resistance or ADC-code capture is claimed. `value` contains an engineering conversion, or SQL NULL when scaling is unconfirmed/raw-only. RTD configured gain and offset are applied on top of the DAQmx temperature. `raw_value` remains unchanged. NaN/infinite inputs are stored as NULL with `NONFINITE_INPUT`, rather than ambiguous nonstandard JSON/SQLite NaNs.

`counter` contains one row per host poll per channel: `(poll_index, channel)` forms the compound primary key. It stores raw count, unwrapped count relative to the first snapshot, actual rolling-window timestamps/counts, estimated frequency, confirmed flow, resolution and quality. Channels include `q_water_in_l_min` and `q_water_out_l_min`. The initial row for each channel has no frequency/flow. Subsequent warm-up rows are estimates over a short, explicitly recorded window. No-pulse rows are marked as ambiguous zero-flow/signal-loss observations.

`metadata` contains JSON values for configuration, environment/package versions, source-code hash, inventory, actual stream settings, clock anchor, run status, worker outcomes and errors. `metadata.json` mirrors these values at initialization/stream configuration/finalization; per-sample row counts in that file are finalized at run end. `events` includes runtime configuration/error records and operator notes. `acquisition.log` is a human-readable supplementary log.

## Quality strings

Multiple flags are joined with `|`. `SIMULATED` is attached to all simulated samples. `OK` means that an established transfer function was applied and nominal electrical limits were not exceeded; it is **not** an overall calibration certificate or proof of physical validity.

`RAW_ONLY`, `UNCONFIRMED_SCALE`, `AT_DAQ_LIMIT`, `OUTSIDE_NOMINAL_SIGNAL`, `NONFINITE_INPUT`, `DAQMX_RTD_LINEARIZATION`, and `OUTSIDE_RTD_EXPECTED_RANGE` describe sample-conversion conditions. Counter flags include `WARMUP`, `NO_PULSES_FLOW_OR_SIGNAL_LOSS`, and `OUTSIDE_SENSOR_FLOW_RANGE`.

Flags are data diagnostics, not safety-interlock commands. Out-of-range finite readings are retained, never clipped to a plausible endpoint. No missing value is replaced with the last valid sample.

## Other files

Real NI runs optionally contain `rtd_raw.tdms` and `analog_raw.tdms` from DAQmx LOG_AND_READ. They are separate per task; their channel scales should be interpreted with NI-aware TDMS tooling. The SQLite file is the common application-level record across all streams. The simulator produces SQLite but not TDMS.

A completed run has a `COMPLETED`, `INTERRUPTED` or `FAILED` status marker. A leftover `RUNNING` marker means the process did not finalize. On exceptional finalization failure, a `FAILURE.json` sidecar is attempted. Full recovery from power loss, filesystem failure or disconnected storage cannot be guaranteed.

CSV/Parquet export writes all five database tables and a manifest. It does not alter the source, rescale old measurements, infer missing calibrations, or synchronize streams. An export is refused while `RUNNING` exists. A note added later changes the database; prior exported copies remain snapshots of the earlier database state.

External RPM attachments live under `external_rpm/` and retain their original content and hash. Run-level constant RPM is in `metadata.external_impeller`; neither is a cDAQ measurement.

# Timing model and limits

## Independent acquisition clocks

The NI backend creates one continuous RTD task and one continuous voltage task. cDAQ-9173 supports multiple AI timing engines; the two tasks are committed independently and started from their owning worker threads. This implementation does not route a common hardware start trigger or explicitly share a sample clock between them. DAQmx-returned sample rates are stored, rather than assuming requested rates were accepted exactly.

For each analog stream the application saves:

- `sample_index`: contiguous index starting at zero.
- `device_time_s = sample_index / actual_rate_hz`: the nominal time on that stream's sample grid.
- `t_rel_s_est = host_start_call_midpoint + device_time_s`.
- `utc_ns_est = anchor_epoch_ns + round(t_rel_s_est * 1e9)`.
- `read_rel_s`: when the containing block was received by the Python reader.

The start-call midpoint is an estimate, **not a hardware timestamp**. Its recorded bracket is not a bound on actual acquisition-start uncertainty. It does not include all driver scheduling, USB, filtering or conversion latency. The first sample may not occur exactly at that midpoint. The NI-9217 is scanned, and NI-9204 differential channels do not become simultaneous just because they are in one scan. All channels in a block carry nominal scan-grid times; channel-specific conversion offsets and filter delays are not corrected.

Within a task, spacing comes from the hardware sample clock. Across tasks, absolute phase is not validated. Do not interpolate to a common grid and claim higher synchronization accuracy than has been physically established. For fast transient identification or tight simultaneous heat balances, first implement and verify a hardware trigger/clock synchronization design and account for module filtering and scanned channel delays.

The monotonically increasing host clock is used for elapsed times. The UTC clock is anchored once after task preparation; subsequent computer wall-clock corrections do not rewrite analog or counter sample times. The metadata records both clock anchors. Acquisition duration includes thread/task start latency and shutdown may append a small buffered tail; inspect actual stream start/stop information for the usable experimental interval.

## Counter timing

The counter starts once and accumulates rising edges in hardware. Python takes an on-demand snapshot; timestamp is the midpoint between the beginning and end of that read. This is not hardware-latched sampling and is not phase-locked to either analog task. The read duration is recorded.

The rolling window uses the newest preceding snapshot at or just before the target window start. Its actual start/end and count difference are saved; its duration can slightly exceed the requested window. During initial filling it is shorter and marked `WARMUP`. Frequency = window counts / actual elapsed window; flow = frequency / confirmed Hz-per-(L/min) coefficient. Nonuniform polling therefore does not silently become an assumed uniform gate.

The 32-bit raw counter wraps at 2^32. Differences are computed modulo 2^32, assuming fewer than one wrap between polls and no counter resets. At the sensor's quoted frequency range this is a reasonable acquisition condition, but the software does not support an external counter reset while a run is active. `count_unwrapped` is cumulative **relative to the first polled count**, not an assertion that every edge before that initial poll was included in a volume calculation.

The one-count flow step is shown as a resolution aid only. It excludes poll-time uncertainty, clock error, sensor calibration/nonlinearity, fluid effects and installation error. A low or unchanged count cannot diagnose physical zero flow versus wiring failure.

## Manual records

External RPM is retained as its own measurement source. `t_rel_s` in an attached RPM CSV must already refer to this run's acquisition anchor. Attachment requires a written alignment explanation; no time shift, forward filling or interpolation is applied automatically. Manual notes added from a second process are labeled `operator_wall_clock`; do not use them as precision hardware events.

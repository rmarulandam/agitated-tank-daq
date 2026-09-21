# Agitated Tank DAQ - v0.1.0

A text-based, **acquisition-only** Python application for the agreed experimental rig:

- cDAQ-9173 with:
  - NI-9217: four 4-wire PT100 temperatures.
  - NI-9204: seven differential voltage channels.
  - NI-9401: two Hall water-flow pulse trains (inlet & outlet) routed to chassis counters (5 V TTL).


The NI backend uses NI's `nidaqmx` Python API and the separately installed NI-DAQmx driver. The simulator needs neither NI hardware nor the NI driver.

**Release status:** The included `TEST_REPORT.md` states exactly what was tested. Commission the rig before collecting dissertation data.

## 1. First run on Windows: no hardware needed

Install 64-bit Python 3.12, extract the ZIP, and open PowerShell in the `agitated-tank-daq` folder. Python 3.11+ is accepted by the package. The following commands do not require activating the virtual environment or changing PowerShell's execution policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m tankdaq validate --config configs\demo.yaml
.\.venv\Scripts\python.exe -m tankdaq run --config configs\demo.yaml --backend sim --duration 60
```

Dependencies are downloaded from the Python package index when installing; they are not bundled. The simulation is wall-clock paced. Its temperatures, voltages and pulse train are synthetic, not a calibrated tank model. `demo.yaml` has `simulation_only: true`; the hardware backend refuses to use it.

After the run:

```powershell
$run = (Get-ChildItem .\runs -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
.\.venv\Scripts\python.exe -m tankdaq inspect "$run"
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format csv
```

For a live terminal display, run the following in a second PowerShell window while acquisition continues:

```powershell
$run = (Get-ChildItem .\runs -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
.\.venv\Scripts\python.exe -m tankdaq watch "$run"
```

Stopping the **watch** command does not stop acquisition. Press Ctrl+C in the **run** window to stop acquisition. A run stopped by Ctrl+C is marked `interrupted`, with received data retained; a duration-limited successful run is `completed`.

Optional convenience scripts are in `scripts/`. The commands above are sufficient; no script execution-policy changes are needed.

## 2. what is implemented

Two continuous, hardware-clocked analog-input tasks run independently: a four-channel RTD task and a seven-channel voltage task. A third worker task starts cumulative rising-edge counters once on two independent chassis counters, then polls their counts. Each producer has a bounded queue feeding one transactional database writer.

Default requested acquisition settings are **1 sample/s/channel for RTDs**, **10 samples/s/channel for analog voltages**, and **2 counter polls/s**. RTD ADC mode is explicitly `HIGH_RESOLUTION`. NI-DAQmx verifies/commits the tasks and the application records the driver-returned sample rates. Unsupported configurations fail.

Two independent Hall-effect water flow channels are acquired:
- **Inlet Flow (`q_water_in_l_min`)**: G1-1/2 sensor with nominal equation $f_{\text{Hz}} = 0.5 \cdot Q_{\text{in}}$ (L/min), range 5–150 L/min, routed to chassis counter `ctr0` on NI-9401 terminal `PFI0`.
- **Outlet Flow (`q_water_out_l_min`)**: GREDIA GR-S403 G3/4" sensor with nominal equation $f_{\text{Hz}} = 5.5 \cdot Q_{\text{out}} \pm 2\%$ (L/min), range 1–60 L/min ($\le 1.2\text{ MPa}$), routed to chassis counter `ctr1` on NI-9401 terminal `PFI1`.

The application estimates frequency for each sensor from differences of cumulative hardware counts over an actual elapsed-time rolling window, then applies the configured coefficient. The default window is 10 seconds. The beginning of a run is flagged `WARMUP` until the window is established.

There is no pulse-period timeout at zero flow: cumulative count reads can return an unchanged count. An unchanged count is flagged `NO_PULSES_FLOW_OR_SIGNAL_LOSS`, because software cannot distinguish stopped water from a failed/disconnected signal. Poll timestamps and duration are saved. Frequency estimates are rolling averages, not instantaneous flow measurements.

The application handles 32-bit count rollover between polls. External counter resets during a run are not supported. Counts, elapsed windows and nominal/calibrated flow are retained separately.

## 3. Channel map

Device names below are configuration defaults, not a claim about the names assigned by NI MAX on your PC.

| Stream | NI channel | Negative terminal signal | Raw data name | Engineering name |
|---|---|---|---|---|
| RTD | `cDAQ1Mod1/ai0` | 4-wire RTD connection | `t_air_in_raw_c` | `t_air_in_c` |
| RTD | `cDAQ1Mod1/ai1` | 4-wire RTD connection | `t_air_out_raw_c` | `t_air_out_c` |
| RTD | `cDAQ1Mod1/ai2` | 4-wire RTD connection | `t_water_upper_raw_c` | `t_water_upper_c` |
| RTD | `cDAQ1Mod1/ai3` | 4-wire RTD connection | `t_water_bulk_raw_c` | `t_water_bulk_c` |
| Analog | `cDAQ1Mod2/ai0` | `AI8` | `v_changor_t_v` | `t_ambient_c` |
| Analog | `cDAQ1Mod2/ai1` | `AI9` | `v_changor_rh_v` | `rh_ambient_pct` |
| Analog | `cDAQ1Mod2/ai2` | `AI10` | `v_p_atm_v` | `p_atm_pa` |
| Analog | `cDAQ1Mod2/ai3` | `AI11` | `v_p_water_in_v` | `p_water_in_pa` |
| Analog | `cDAQ1Mod2/ai4` | `AI12` | `v_p_water_out_v` | `p_water_out_pa` |
| Analog | `cDAQ1Mod2/ai5` | `AI13` | `v_dp_air_v` | `dp_air_duct_pa` |
| Analog | `cDAQ1Mod2/ai6` | `AI14` | `v_air_velocity_v` | `v_air_m_s` |
| Counter | `cDAQ1Mod3/ctr0` | source `/cDAQ1Mod3/PFI0` | `water_in_pulse_count` | `f_water_in_hz`, `q_water_in_l_min` |
| Counter | `cDAQ1Mod3/ctr1` | source `/cDAQ1Mod3/PFI1` | `water_out_pulse_count` | `f_water_out_hz`, `q_water_out_l_min` |

The NI-9204 is explicitly configured as `DIFF`. Its negative inputs are not added as extra DAQ channels. `ai7/ai15` remains unused. R1, R2, R3, R4 and R5 are associated with Changor T, Changor RH, barometric pressure, air differential pressure, and air velocity respectively. R6-R10 are spares and have no software channels. The unused fourth chassis slot remains unused.

Counter resources are selected explicitly; `tankdaq devices` lists the available counter names and PFI terminals. If your installation enumerates counters under the chassis rather than the module (e.g. `cDAQ1/ctr0`), set each channel's `counter_channel` to the exact listed resource. Keep `pulse_terminal` pointed at the physical NI-9401 inputs (`/cDAQ1Mod3/PFI0` and `/cDAQ1Mod3/PFI1`). Resource existence is checked first; DAQmx task commit validates the route. The software never substitutes another input automatically.

## 4. Commission the real hardware

Install an NI-DAQmx driver version that supports **all four actual hardware models** on your Windows version. The Python wheel alone is not the driver. Close NI MAX test panels, LabVIEW VIs and any other process that owns the same hardware before acquisition.

Install the Python interface and enumerate devices:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ni,test]"
.\.venv\Scripts\python.exe -m tankdaq devices --output devices.json
Copy-Item configs\rig.yaml configs\rig.local.yaml
notepad configs\rig.local.yaml
```

In `rig.local.yaml`, use the exact NI device and channel names. Do not edit `demo.yaml` into a hardware configuration: its ranges are synthetic examples.

Before enabling hardware, verify the physical wiring against the manufacturers' connector diagrams, supplies, shunts, common-mode limits and the laboratory electrical design. Then set the following checks to `true` only when completed:

```yaml
checks:
  wiring_verified: true
  sensor_supplies_verified: true
  rtd_curve_verified: true
  hall_logic_verified: true
```

The RTD template uses NI's `PT_3851` curve, 100 ohms at 0 C, four wires and 1 mA internal excitation. Verify the selected curve against the delivered PT100 documentation/certificate, rather than inferring it solely from the quotation's rounded alpha. No custom Callendar-Van Dusen curve is implemented. The temperature interval in the config is a requested acquisition interval, not a temperature safety limit.

The provisional Changor design has two independent 4-20 mA outputs. This assumption remains in the configuration; software cannot establish whether the delivered device actually has those outputs. The airflow sensor also needs an actual model, configured output range and installation before its channel is considered experimental data.

First collect **raw commissioning data**:

```powershell
.\.venv\Scripts\python.exe -m tankdaq validate --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring --duration 60
```

`validate` checks configuration only; it does not open hardware or certify wiring. `run` additionally verifies inventory and prepares/commits the tasks. Preparing an RTD task may establish excitation. No hardware acquisition starts without explicit acknowledgement. NI MAX simulated devices are refused by the hardware backend; use the built-in simulator instead.

In raw-only mode, all seven analog voltages and counter counts/frequency are recorded, but transmitter engineering values and water flow in L/min are null. RTD temperatures remain available because the NI-9217 task already returns DAQmx-linearized degrees Celsius. Those are not raw resistance/ADC codes and should not be represented as such.

Next establish each transmitter's delivered signal variant and engineering endpoints in the config. Use the actual measured shunt resistance in `shunt_ohm`. Set `scale.confirmed: true` and give a meaningful `calibration_id` or verified-datasheet identifier. In this application, **confirmed means that the selected transfer function is established**, not that an accredited calibration has been performed. Store the calibration certificate and uncertainty assessment separately.

A current-loop channel computes:

```text
I_mA = 1000 * V_measured / R_measured
Y = Y_min + (I_mA - I_min) / (I_max - I_min) * (Y_max - Y_min)
Y_corrected = Y * post_gain + post_offset
```

A voltage-output channel uses the same interpolation with its confirmed voltage endpoints. No engineering values are clipped at the configured endpoints. Out-of-range signals receive quality flags. Raw values are always kept.

Confirm each Hall sensor's coefficient, set `calibration_confirmed: true` in its channel definition, and record its source in `calibration_id` (for example, the confirmed GREDIA GR-S403 outlet sensor coefficient $5.5\text{ Hz/(L/min)}$). Once all scales are confirmed, omit `--raw-only`:

```powershell
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --acknowledge-wiring --duration 3600
```

Omit `--duration` for an operator-stopped run. Omitting it does not create background scheduling: the terminal process must remain running. Do not allow Windows sleep/hibernation during acquisition.

## 5. Run files and exports

Every run creates a unique directory; existing run directories are not overwritten:

```text
runs/<UTC>_NI_agitated_tank_<unique>/
  config_original.yaml        # exact source config supplied to the command
  config_resolved.yaml        # configuration actually used
  metadata.json               # environment, source/config hashes, times, status
  devices.json                # real-hardware runs only
  measurements.sqlite         # raw samples, scaled values, counter, events
  rtd_raw.tdms                 # hardware runs when storage.tdms is true
  analog_raw.tdms              # hardware runs when storage.tdms is true
  acquisition.log
  COMPLETED / INTERRUPTED / FAILED
```

`RUNNING` exists until normal finalization. A stale `RUNNING` marker after a crash means the run was not cleanly finalized; do not simply rename it to `COMPLETED`. SQLite `-wal` and `-shm` files may exist while writing. Do not copy only the database during an active run, place live databases on a network/sync folder, or move the run directory while acquisition is active. Copy the entire finalized run to long-term storage.

SQLite is the always-on application record, with one writer, WAL mode and full synchronization at commits. The default commit interval is one second. An abrupt process/power failure can lose the current uncommitted tail; UPS/storage reliability remains an experimental responsibility. Queue overflow, driver errors, sample-index discontinuities, missing required streams, disk threshold violations and writer failures fail the run rather than being silently ignored. Shutdown attempts to stop each analog task and drain its buffered tail; a drain failure is recorded, not reported as complete.

NI runs additionally request **separate driver TDMS files for each AI task**. These use `LOG_AND_READ`; reads must continue for NI-DAQmx to stream the data. TDMS is not an independent fail-safe logger if Python or the read loop stalls. Counter polls and external RPM are not written to those TDMS files; their records are SQLite and external attachments respectively. The simulator does not fabricate TDMS files.

Export a finalized run:

```powershell
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format csv
.\.venv\Scripts\python.exe -m pip install -e ".[parquet]"
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format parquet
```

Exports are long-form: one row per channel and sample, retaining raw and engineering values, quality flags and stream timestamps. CSV requires no additional library. Parquet requires optional PyArrow. The export does not interpolate channels onto a common time grid. See `docs/DATA_FORMAT.md` and `docs/TIMING.md` before combining streams.

## 6. External impeller RPM and operator notes

For a constant operating level, put your externally calculated `impeller_rpm`, calculation `method` and, if established, `uncertainty_rpm` in `external` before a run. The software records your value; it does not calculate or measure RPM.

For a changing operating level, prepare a separate CSV with:

```csv
t_rel_s,n_impeller_rpm,method,uncertainty_rpm
0,36,external calibration curve revision 1,0.8
300,48,external calibration curve revision 1,0.8
```

Those numbers are illustrative, not your experiment's established settings or uncertainties. `examples/external_rpm_TEMPLATE.csv` contains only the header. Attach your completed file after the run:

```powershell
.\.venv\Scripts\python.exe -m tankdaq attach-rpm "$run" --csv .\my_rpm.csv --alignment-note "External record aligned to this run's acquisition t=0; describe how and give any known timing uncertainty."
```

The original CSV and SHA-256 are preserved. No interpolation or timestamp offset is guessed. For events during a run:

```powershell
.\.venv\Scripts\python.exe -m tankdaq note "$run" "Operator changed the externally recorded impeller setting."
```

Operator notes use host wall-clock time and are labeled accordingly; clock changes can affect their alignment.

## 7. What this release does not claim

The tasks are **not hardware-synchronized to each other**. Timestamps on different modules must not be treated as exactly simultaneous. RTD and multiplexed analog channel conversion/filter delays are not corrected. The default architecture is for low-rate thermal measurements, not proof of suitability for fast transient system identification. See the timing document.

The application does not verify pressure plumbing, gauge versus absolute pressure reference, Hall pull-up wiring, 24 V common-mode safety, airflow profile representativeness, or exact sensor electrical variants. Those are physical commissioning requirements. It does not infer volumetric airflow from a single velocity reading, infer water heat duty from two tank temperatures, or calculate psychrometrics/heat-transfer coefficients without the missing physical assumptions.

There is no browser dashboard in this release; the live display is the implemented terminal `watch` command. There is no LabVIEW component, Modbus backend, motor controller, automatic restart of a failed acquisition, or automatic replacement of a missing sensor by simulated data.

## 8. Tests, structure and sources

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

`src/tankdaq/` contains separate configuration, scaling, backend, storage, coordinator and CLI modules. `tests/` covers safety/configuration gates, differential channel mapping, scaling, count rollover, zero-pulse ambiguity, rolling-window timing, raw-only acquisition, failure handling, simulation integration, CSV export and API contract construction. Optional Parquet tests skip when PyArrow is absent.

The source basis is the agreed wiring specification and the two supplied DAQ Solutions quotations. Unknown or contradictory sensor details remain unconfirmed. NI API behaviors were checked against primary NI documentation. See `docs/SOURCES.md`, `docs/COMMISSIONING.md`, `TEST_REPORT.md` and the included test output.

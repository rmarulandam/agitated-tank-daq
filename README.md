# Agitated Tank DAQ - v0.1.0

A text-based, **acquisition-only** Python application for the agreed experimental rig:

- cDAQ-9173 with NI-9217: four 4-wire PT100 water temperatures (`t_water_in_c`, `t_water_out_c`, `t_water_level_quarter_c`, `t_water_level_three_quarters_c`).
- NI-9204: eight differential voltage channels, including seven 250-ohm shunts (`t_air_in_c`, `rh_air_in`, `t_air_out_c`, `rh_air_out`, `p_atm_pa`, `rh_ambient_pct`, `dp_air_duct_pa`) and one 0–10 V linear channel (`power_motor_w`).
- NI-9411 or NI-9401: three pulse-counter channels (`water_flow_in`, `water_flow_out`, `impeller_rpm`) routed to chassis counters (`ctr0`, `ctr1`, `ctr2`).

The NI backend uses NI's `nidaqmx` Python API and the separately installed NI-DAQmx driver. The simulator needs neither NI hardware nor the NI driver.

**Release status:** application/simulator tested in the build environment; NI API calls checked against NI documentation and exercised with fake API contract tests. No physical NI chassis, sensors or Windows installation was available for hardware acceptance testing. The included `TEST_REPORT.md` states exactly what was tested. Commission the rig following [`docs/COMMISSIONING.md`](docs/COMMISSIONING.md) before collecting dissertation data.

## 1. First run on Windows: synthetic data

Install 64-bit Python (Python 3.11–3.13 are supported; Python 3.12 or 3.13 recommended), extract the package, and open PowerShell in the `agitated-tank-daq` folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m tankdaq validate --config configs\demo.yaml
.\.venv\Scripts\python.exe -m tankdaq run --config configs\demo.yaml --backend sim --duration 60
```

Dependencies are downloaded from the Python package index when installing; they are not bundled. The simulation is wall-clock paced. Its temperatures, voltages and pulse trains are synthetic. `demo.yaml` has `simulation_only: true`; the hardware backend refuses to use it.

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

## 2. What is implemented

The application coordinates two fundamentally different acquisition modes—continuous hardware-clocked analog sampling and on-demand digital counter polling—into a unified, crash-resilient data stream.

### Architecture & Concurrency Pipeline

Acquisition, storage, and visualization run on separate threads to prevent disk latency or UI interactions from stalling hardware reads:

- **Independent Acquisition Workers:**
  - **Analog Tasks:** Two continuous, hardware-clocked analog input tasks run independently: a 4-channel RTD task (NI-9217) and a 7-channel differential voltage task (NI-9204).
  - **Counter Tasks:** A third worker starts cumulative rising-edge counting once across three chassis counters (NI-9411 or NI-9401) for inlet water flow, outlet water flow, and axis impeller revolutions, polling count snapshots at regular intervals.
- **Transactional Bounded Pipeline:** Producers push sample blocks into a shared, memory-bounded queue. A dedicated writer thread consumes this queue and commits records to an SQLite database in Write-Ahead Logging (WAL) mode. This isolates acquisition from disk latency; if disk writes fall behind, the bounded queue triggers an immediate, clean failure rather than silently discarding samples.
- **Decoupled Terminal Monitor:** The live terminal monitor (`tankdaq watch`) queries `measurements.sqlite` in read-only mode (`?mode=ro`). Because the display never owns or communicates directly with the DAQ tasks, viewing, pausing, resizing, or closing the monitor cannot interrupt ongoing acquisition or drop hardware samples.

### Analog Sampling & Hardware Verification

- **Configured Sampling Rates:** Default requested acquisition settings are **1 sample/s/channel for RTDs** (well-suited for slow thermal mass) and **10 samples/s/channel for analog voltages** (capturing air, pressure, level, and power dynamics).
- **High-Resolution Thermal Filtering:** The RTD ADC timing mode is explicitly configured to `HIGH_RESOLUTION`, utilizing the NI-9217 delta-sigma converter's built-in 50/60 Hz power-line noise rejection.
- **Fail-Closed Hardware Verification:** NI-DAQmx verifies and commits task configurations before acquisition starts. The application records the exact driver-returned clock rates in run metadata rather than assuming requested rates were accepted verbatim. Unsupported configurations fail immediately; the software will never silently alter wiring polarity, downgrade ADC modes, or substitute fake measurements.

### Pulse Counting & Rolling Window (Flow & Impeller RPM)

Water flow rates (`water_flow_in`, `water_flow_out`) and axis impeller speed (`impeller_rpm`) are measured by tracking cumulative rising edges rather than sampling raw waveforms:

- **Rolling-Window Frequency Estimation:** Frequency ($f_{\text{Hz}}$) is estimated for each counter channel from differences in cumulative hardware counts over an actual elapsed-time rolling window (default: 10 seconds). Engineering rate ($Y$) is then calculated using each channel's configured calibration coefficient ($f_{\text{Hz}} = \text{hz\_per\_unit} \cdot Y$).
- **Warmup & Resolution:** The beginning of a run is flagged `WARMUP` until the full 10-second rolling window is established. Under the nominal Hall flowmeter coefficient ($\text{hz\_per\_unit} = 0.5\,\text{Hz}/(\text{L/min})$), one count over 10 seconds corresponds to $0.2\,\text{L/min}$ counting resolution (**this is digital resolution, not total measurement uncertainty**).
- **Signal Loss vs. Zero Rate Ambiguity:** Cumulative counter reads do not time out at zero flow or zero speed; they return an unchanged count. Because software cannot distinguish stagnant water or a stopped shaft from a broken wire or sensor failure, unchanged counts are explicitly flagged `NO_PULSES_FLOW_OR_SIGNAL_LOSS`.
- **Rollover & Monotonicity:** The application automatically handles 32-bit integer count rollover between successive polls. Polling timestamps are recorded as host call midpoints, and counts, elapsed windows, and engineering rates are preserved independently.

## 3. Hardware topology and channel mapping

The software enforces the **physical module and terminal topology**, while channel identifiers (`name`, `unit`, and scaling) are **fully user-configurable in YAML**:

- **Slot 1: NI-9217 (4-wire RTD)**: Exactly 4 channels on physical inputs `ai0` through `ai3`.
  - Raw values: Linearized degrees Celsius from DAQmx.
- **Slot 2: NI-9204 (Differential Voltage / Current Loops)**: Exactly 8 differential pairs on `ai0/ai8` through `ai7/ai15`.
  - Raw values: Measured voltage (V) across differential inputs (or across shunt resistors for 4–20 mA loops).
- **Slot 3: NI-9411 or NI-9401 (Digital Counter)**: Three digital input terminals (e.g. `PFI0`, `PFI1`, `PFI2`) routed to chassis counter resources (e.g. `ctr0`, `ctr1`, `ctr2`).
  - Raw values: Cumulative hardware pulse count per channel.

All channel names (`name`) can be customized in your YAML configuration (e.g. `rig.local.yaml`) to match your experiment. Names must use 1–50 ASCII letters, digits, or underscores starting with a letter (`[A-Za-z][A-Za-z0-9_]{0,49}`), and must be unique across all streams.

### Reference template mapping (default `configs/rig.yaml`)

The table below illustrates the default template included with `configs/rig.yaml`. These specific sensor names and assignments can be customized in your configuration:

| Stream | NI physical channel | Negative terminal | Default channel name | Template sensor description |
|---|---|---|---|---|
| RTD | `cDAQ1Mod1/ai0` | 4-wire connection | `t_water_in_c` | Water inlet temperature |
| RTD | `cDAQ1Mod1/ai1` | 4-wire connection | `t_water_out_c` | Water outlet temperature |
| RTD | `cDAQ1Mod1/ai2` | 4-wire connection | `t_water_level_quarter_c` | Tank water temperature at 1/4 level |
| RTD | `cDAQ1Mod1/ai3` | 4-wire connection | `t_water_level_three_quarters_c` | Tank water temperature at 3/4 level |
| Analog | `cDAQ1Mod2/ai0` | `AI8` | `t_air_in_c` | Inlet air temperature (Changor T/RH model, 4–20 mA, shunt R1) |
| Analog | `cDAQ1Mod2/ai1` | `AI9` | `rh_air_in` | Inlet air relative humidity (Changor T/RH model, 4–20 mA, shunt R2) |
| Analog | `cDAQ1Mod2/ai2` | `AI10` | `t_air_out_c` | Outlet air temperature (Changor T/RH model, 4–20 mA, shunt R3) |
| Analog | `cDAQ1Mod2/ai3` | `AI11` | `rh_air_out` | Outlet air relative humidity (Changor T/RH model, 4–20 mA, shunt R4) |
| Analog | `cDAQ1Mod2/ai4` | `AI12` | `p_atm_pa` | Barometric pressure (4–20 mA, shunt R5) |
| Analog | `cDAQ1Mod2/ai5` | `AI13` | `rh_ambient_pct` | Ambient relative humidity (4–20 mA, shunt R6) |
| Analog | `cDAQ1Mod2/ai6` | `AI14` | `dp_air_duct_pa` | Air differential pressure (4–20 mA, shunt R7) |
| Analog | `cDAQ1Mod2/ai7` | `AI15` | `power_motor_w` | Motor electrical power (0–10 V voltage linear) |
| Counter | `cDAQ1Mod3/ctr0` | source `/cDAQ1Mod3/PFI0` | `water_flow_in` | Water inlet flow pulses (Hall sensor) |
| Counter | `cDAQ1Mod3/ctr1` | source `/cDAQ1Mod3/PFI1` | `water_flow_out` | Water outlet flow pulses (Hall sensor) |
| Counter | `cDAQ1Mod3/ctr2` | source `/cDAQ1Mod3/PFI2` | `impeller_rpm` | Axis impeller revolutions (pulse tachometer) |

The NI-9204 is explicitly configured as `DIFF`. Its negative inputs are paired differential returns (`AI8` through `AI15`) and are not added as extra DAQ channels; all eight differential channels (`ai0/ai8` through `ai7/ai15`) are utilized. In the template configuration, Changor transmitter models provide two distinct outputs (temperature and relative humidity) for both inlet air (`t_air_in_c` on `ai0/ai8`, `rh_air_in` on `ai1/ai9`) and outlet air (`t_air_out_c` on `ai2/ai10`, `rh_air_out` on `ai3/ai11`). R1–R7 are associated with the seven current-loop channels (`ai0` through `ai6`); the 0–10 V channel (`ai7` for motor electrical power in `W`) is configured with `scale.kind: voltage_linear` and connects directly without a shunt. Tank water level (`level_water_m`) is no longer included. The unused fourth chassis slot remains unused.

Each counter channel's resource is selected explicitly under `counter.channels`; `tankdaq devices` lists the available counter names and PFI terminals. If your installation enumerates counters under the chassis rather than the module, set each channel's `physical` field to the exact listed resource (e.g. `cDAQ1/ctr0`, `cDAQ1/ctr1`, `cDAQ1/ctr2`). Keep each `pulse_terminal` pointed at the physical NI-9411 or NI-9401 input (`PFI0`, `PFI1`, `PFI2`). Resource existence is checked first; DAQmx task commit validates the routes. The software never substitutes another input automatically.

## 4. Hardware commissioning

To avoid duplicate documentation, detailed step-by-step procedures, electrical checks, scaling transfer functions, and operational acceptance tests are consolidated in the **[Hardware Commissioning Guide & Checklist](docs/COMMISSIONING.md)**.

Before collecting research data with the physical rig, follow [`docs/COMMISSIONING.md`](docs/COMMISSIONING.md).

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

`RUNNING` exists until normal finalization. A stale `RUNNING` marker after a crash means the run was not cleanly finalized. SQLite `-wal` and `-shm` files may exist while writing. Do not copy only the database during an active run, place live databases on a network/sync folder, or move the run directory while acquisition is active. Copy the entire finalized run to long-term storage.

SQLite is the always-on application record, with one writer, WAL mode and full synchronization at commits. The default commit interval is one second. An abrupt process/power failure can lose the current uncommitted tail; UPS/storage reliability remains an experimental responsibility. Queue overflow, driver errors, sample-index discontinuities, missing required streams, disk threshold violations and writer failures fail the run rather than being silently ignored. Shutdown attempts to stop each analog task and drain its buffered tail; a drain failure is recorded.

NI runs additionally request **separate driver TDMS files for each AI task**. These use `LOG_AND_READ`; reads must continue for NI-DAQmx to stream the data. TDMS is not an independent fail-safe logger if Python or the read loop stalls. Counter polls (water flow and impeller RPM) are stored in SQLite. Impeller rotation is acquired exclusively through the hardware counter channel `impeller_rpm` on `cDAQ1Mod3/ctr2`. The simulator does not fabricate TDMS files.

### Automatic Export on Completion (Optional)

You can configure the runner to automatically export CSV or Parquet files as soon as acquisition finalizes cleanly (without having to run a separate export command) by setting true/false flags under `storage:` in your YAML configuration:

```yaml
storage:
  tdms: true
  auto_export_csv: true        # Automatically generates export_csv_<hash>/ upon finalization
  auto_export_parquet: false   # Automatically generates export_parquet_<hash>/ (requires PyArrow)
  min_free_mb: 500.0
  commit_interval_s: 1.0
```

When enabled, the coordinator runs the export immediately after all buffered samples are drained and SQLite transactions are closed. Any export failure is safely captured without compromising the underlying SQLite database.

### Manual Export of a Finalized Run

You can also export any finalized run manually at any time:

```powershell
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format csv
.\.venv\Scripts\python.exe -m pip install -e ".[parquet]"
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format parquet
```

Exports are long-form: one row per channel and sample, retaining raw and engineering values, quality flags and stream timestamps. CSV requires no additional library. Parquet requires optional PyArrow. The export does not interpolate channels onto a common time grid. See `docs/DATA_FORMAT.md` and `docs/TIMING.md` before combining streams.

## 6. Operator notes during acquisition

Operator events and observations (e.g. setpoint changes, manual valve adjustments, visual milestones) can be recorded into the run's audit trail at any time from a separate terminal:

```powershell
.\.venv\Scripts\python.exe -m tankdaq note "$run" "Operator changed the impeller speed setting."
```

Operator notes use host wall-clock time and are labeled accordingly; clock changes can affect their alignment.

## 7. What this release does not claim

The tasks are **not hardware-synchronized to each other**. Timestamps on different modules must not be treated as exactly simultaneous. RTD and multiplexed analog channel conversion/filter delays are not corrected. The default architecture is for low-rate thermal and process measurements, not proof of suitability for fast transient system identification. See the timing document.

The application does not verify pressure plumbing, gauge versus absolute pressure reference, Hall pull-up wiring, 24 V common-mode safety, airflow profile representativeness, or exact sensor electrical variants. Those are physical commissioning requirements.

There is no browser dashboard in this release; the live display is the implemented terminal `watch` command. There is no LabVIEW component, Modbus backend, motor controller, automatic restart of a failed acquisition, or automatic replacement of a missing sensor by simulated data.

## 8. Tests, structure and sources

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated suite: **66 passed** tests covering safety/configuration gates, configurable channel names and syntax validation, differential channel mapping, multi-channel counter routing, scaling, count rollover, zero-pulse ambiguity, rolling-window timing, raw-only acquisition, failure handling, simulation integration, CSV export, Parquet export, and NI API contract mocks (including both NI-9411 and NI-9401 digital counter modules).

### Repository Structure

```text
agitated-tank-daq/
├── .gitattributes            # Git LFS tracking configuration for binary assets
├── configs/                  # Configurations: template (rig.yaml), simulation (demo.yaml), and pilot demo (pilot.demo.yaml)
├── docs/                     # Technical documentation
│   ├── calibrations/         # Calibration certificates, provenance register, and Git LFS storage
│   ├── COMMISSIONING.md      # Five-phase hardware commissioning checklist
│   ├── DATA_FORMAT.md        # SQLite and export schema specification
│   ├── SOURCES.md            # Hardware quotes, sensor specifications, and references
│   └── TIMING.md             # Timing, sampling, counter latency, and jitter documentation
├── examples/                 # Sample simulated run artifacts
├── scripts/                  # Convenience PowerShell scripts (setup.ps1, run_demo.ps1)
├── src/tankdaq/              # Core Python package
│   ├── __init__.py           # Package metadata and version
│   ├── __main__.py           # Entrypoint for python -m tankdaq
│   ├── backends.py           # Worker abstractions and synthetic simulation producers
│   ├── cli.py                # CLI parser and command dispatch
│   ├── config.py             # Config loading, syntax validation, and safety verification
│   ├── data_tools.py         # Read-only inspection, live terminal monitor, and export
│   ├── models.py             # Data classes (AnalogBlock, CounterPoint, Clock, WorkerOutcome)
│   ├── ni_backend.py         # NI-DAQmx hardware workers (NI-9217, NI-9204, NI-9411/NI-9401)
│   ├── runner.py             # Coordinator: worker threads, bounded queue, failure tracking
│   ├── scaling.py            # Voltage scaling, current loop math, and rolling pulse-rate calculation
│   └── storage.py            # Transactional SQLite writer, WAL checkpoints, metadata tracking
└── tests/                    # Automated pytest suite (66 tests across 3 test modules)
```

The source basis is the agreed wiring specification and the two supplied DAQ Solutions quotations. Unknown or contradictory sensor details remain unconfirmed. NI API behaviors were checked against primary NI documentation. See [`docs/SOURCES.md`](docs/SOURCES.md), [`docs/COMMISSIONING.md`](docs/COMMISSIONING.md), [`TEST_REPORT.md`](TEST_REPORT.md), and the included test output.

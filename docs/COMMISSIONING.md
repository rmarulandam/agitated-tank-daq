# Hardware Commissioning Guide & Checklist

This guide provides the complete physical installation, electrical checkout, scaling formulas, and operational acceptance procedures for the agitated-tank DAQ rig before collecting research data.

> [!WARNING]
> **Safety First:** This is an acquisition-only software checklist. It does not replace proper laboratory electrical safety and engineering controls. Only qualified laboratory personnel should energize the rig.

---

## Phase 0: Software & Driver Prerequisites

Complete these steps on the host PC before connecting field instrumentation:

- [ ] **Install NI-DAQmx Driver:** Download and install the official NI-DAQmx driver suite for Windows (via NI Package Manager).
  > [!IMPORTANT]
  > The Python package (`pip install nidaqmx`) is merely an API wrapper. The official NI-DAQmx driver suite must be installed separately on Windows to provide the required kernel drivers, hardware services, and runtime libraries (`nicaiu.dll`).
- [ ] **Close Conflicting Software:** Close NI MAX test panels, LabVIEW VIs, and any other process holding hardware handles before starting acquisition.
- [ ] **Prepare Python Environment:** Ensure Python (3.11–3.13) is installed with NI dependencies:
  ```powershell
  py -3.12 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -e ".[ni,test]"
  ```
- [ ] **Verify Chassis & Module Detection (NI MAX):** Connect the cDAQ-9173 via USB, open NI MAX, and verify all modules appear under **Devices and Interfaces**:
  - Slot 1: NI-9217 (4-channel RTD)
  - Slot 2: NI-9204 (7 differential analog voltage channels)
  - Slot 3: NI-9411 or NI-9401 (3 digital counter inputs)
- [ ] **Generate Python Hardware Inventory:**
  ```powershell
  .\.venv\Scripts\python.exe -m tankdaq devices --output devices.json
  ```
  *(Note: NI MAX simulated devices are strictly refused by the hardware backend; use `--backend sim` for synthetic demonstrations.)*
- [ ] **Create Site Configuration File:**
  ```powershell
  Copy-Item configs\rig.yaml configs\rig.local.yaml
  ```
  > [!NOTE]
  > Do not edit `demo.yaml` into a hardware configuration: `demo.yaml` has `simulation_only: true` and the hardware backend will refuse it. Local files named `configs/*.local.yaml` and `devices.json` are git-ignored, preventing site-specific calibrations and hardware serial numbers from being committed inadvertently. A complete reference showing how a calibrated local file should look is provided in [`configs/pilot.demo.yaml`](../configs/pilot.demo.yaml).
- [ ] **Align Resource Names:** Verify device names in `configs/rig.local.yaml` match `devices.json` exactly (e.g. `cDAQ1Mod1`, `cDAQ1Mod2`, `cDAQ1Mod3/ctr0` through `ctr2` or `cDAQ1/ctr0` through `ctr2`, and `/cDAQ1Mod3/PFI0` through `PFI2`). If your chassis enumerates counters under the chassis rather than the module, update each channel's `physical` field under `counter.channels` accordingly.

---

## Phase 1: Physical Wiring & Electrical Verification

Keep agitator motor, valves, and heater **physically locked out and unpowered** during electrical checkout.

### 1.1 Power Supplies & Common Ground (`sensor_supplies_verified`)
- [ ] **Power Distribution:** Confirm 24 V DC and 5 V DC sensor power rails are regulated and within specification.
- [ ] **Isolation & Bonding:** Confirm protective earth bonding and instrument signal returns (COM) are wired according to the lab electrical design.
- [ ] **Common-Mode Limits:** Verify that differential voltages and common-mode voltages relative to chassis COM do not exceed the NI-9204 ±10 V limit.

### 1.2 RTD Module Wiring (`rtd_curve_verified`)
- [ ] **Lead Configuration:** Wire all four PT100 water temperature probes (`t_water_in_c`, `t_water_out_c`, `t_water_level_quarter_c`, `t_water_level_three_quarters_c`) using 4-wire connections on `cDAQ1Mod1/ai0` through `ai3`.
- [ ] **Overvoltage Protection:** The NI-9217 provides internal 1 mA excitation.
- [ ] **Curve Selection:** Confirm sensor alpha against the manufacturer's calibration certificate (NI standard curve `PT_3851` with $R_0 = 100\,\Omega$ is selected in the template).
- [ ] **Acquisition Range:** Note that the temperature interval in the configuration is a requested acquisition interval.

### 1.3 Differential Voltage & Shunt Resistors (`wiring_verified`)
- [ ] **Differential Pairs:** Wire analog inputs to the NI-9204 as differential pairs (`ai0/ai8` through `ai6/ai14`). Unused `ai7/ai15` must remain disconnected.
- [ ] **Measure Shunt Resistors ($R_1$–$R_5$):** Measure each 250 $\Omega$ precision current-loop shunt resistor (`ai0` through `ai4`) with a calibrated bench multimeter. Record the exact measured resistance under `shunt_ohm` in `configs/rig.local.yaml` (do not rely on nominal 250.0 $\Omega$ tolerance).
- [ ] **Current-Loop Burden Compliance:** Verify loop power supplies provide sufficient compliance voltage across the 250 $\Omega$ burden and sensor drops. (The software reads voltage across these shunts).
- [ ] **Transmitter Output Verification:**
  - **Air In / Out Temperature Transmitters (`ai0`, `ai1`):** Confirm 4–20 mA current loop wiring across shunts $R_1$ and $R_2$ and verify configured temperature range endpoints.
  - **Barometric Pressure Transmitter (`ai2`):** Confirm the unit is the 4–20 mA analog variant across shunt $R_3$. (A delivered RS485-only transmitter requires separate hardware/software integration).
  - **Ambient Relative Humidity Transmitter (`ai3`):** Confirm 4–20 mA current loop wiring across shunt $R_4$ and verify RH scaling endpoints.
  - **Air Differential Pressure Transmitter (`ai4`):** Confirm differential pressure ports/polarity and 4–20 mA loop wiring across shunt $R_5$.
  - **Tank Water Level & Motor Electrical Power (`ai5`, `ai6`):** Confirm 0–10 V linear voltage outputs and verify level (`m`) and power (`W`) scaling endpoints.

### 1.4 Digital Counters: Water Flow & Impeller RPM (`hall_logic_verified`)
- [ ] **Module Support:** Verify the digital module is either an NI-9411 or NI-9401.
- [ ] **Pulse Conditioning:** Confirm pulse sensor output topologies (5 V TTL vs. open-collector) for inlet flow (`water_flow_in`), outlet flow (`water_flow_out`), and axis impeller tachometer (`impeller_rpm`). Ensure required external pull-up resistors are installed if using open-collector sensors.
- [ ] **Terminal Routes:** Verify physical pulse wiring connects to the configured terminal routes (`/cDAQ1Mod3/PFI0` for `ctr0`, `/cDAQ1Mod3/PFI1` for `ctr1`, and `/cDAQ1Mod3/PFI2` for `ctr2`).

---

## Phase 2: Bench Signal Injection & Quiet Checks

Before connecting installed plant transmitters, test each channel with reference sources where available:

- [ ] **Voltage & Current Loops:** Inject known test signals (e.g. 4 mA, 12 mA, 20 mA across the measured 250 $\Omega$ shunts to observe ~1 V, 3 V, 5 V; and 0–10 V on `ai5`/`ai6`). Record deviations.
- [ ] **RTDs:** Connect a precision decade box or reference RTD; confirm stable, plausible temperature readings in degrees Celsius.
- [ ] **Pulse Counters:** Inject a known pulse frequency (e.g. 10–50 Hz TTL) into each counter channel; confirm counts increment monotonically and frequency calculation matches the input.
- [ ] **Signal Loss Check:** Disconnect pulse signals; verify frequency decays to zero after the rolling window clears and quality flags `NO_PULSES_FLOW_OR_SIGNAL_LOSS`.

---

## Phase 3: Raw Acquisition Commissioning Run

Once physical checks are complete, mark the four gates as `true` in `configs/rig.local.yaml`:

```yaml
checks:
  wiring_verified: true
  sensor_supplies_verified: true
  rtd_curve_verified: true
  hall_logic_verified: true
```

- [ ] **Validate Configuration:**
  ```powershell
  .\.venv\Scripts\python.exe -m tankdaq validate --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring
  ```
  *(Note: `validate` checks configuration syntax only; it does not open hardware).*
- [ ] **Execute 60-Second Raw Test Run:**
  ```powershell
  .\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring --duration 60
  ```
  *(Note: `run` verifies hardware inventory and reserves/commits tasks. Preparing an RTD task may establish excitation. No hardware acquisition starts without explicit `--acknowledge-wiring`.)*
- [ ] **Inspect Output:**
  ```powershell
  $run = (Get-ChildItem .\runs -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
  .\.venv\Scripts\python.exe -m tankdaq inspect "$run"
  ```
- [ ] **Verify Raw Data Behavior:**
  - All seven analog voltages (V) and all three counter pulse counts/frequencies are logged.
  - Transmitter engineering values and counter engineering values (`L/min`, `rpm`) remain `null` (raw-only mode prevents applying unverified equations).
  - RTD temperatures remain available because the NI-9217 returns DAQmx-linearized degrees Celsius.

---

## Phase 4: Establish & Confirm Engineering Scales

Once raw signals are validated, establish each sensor's mathematical transfer function in `configs/rig.local.yaml`.

### 4.1 Scaling Mathematics

- **Current-Loop Channels (4–20 mA over measured shunt $R$):**
  $$I_{\text{mA}} = 1000 \cdot \frac{V_{\text{measured}}}{R_{\text{measured}}}$$
  $$Y = Y_{\min} + \frac{I_{\text{mA}} - I_{\min}}{I_{\max} - I_{\min}} \cdot (Y_{\max} - Y_{\min})$$
  $$Y_{\text{corrected}} = Y \cdot \text{post\_gain} + \text{post\_offset}$$

- **Voltage-Linear Channels (e.g. 0–10 V):**
  $$Y = Y_{\min} + \frac{V_{\text{measured}} - V_{\min}}{V_{\max} - V_{\min}} \cdot (Y_{\max} - Y_{\min})$$
  $$Y_{\text{corrected}} = Y \cdot \text{post\_gain} + \text{post\_offset}$$

- **RTD Probe Corrections:**
  $$T_{\text{corrected}} = T_{\text{linearized}} \cdot \text{gain} + \text{offset\_c}$$
  *(Default gain 1.0 and offset 0.0 apply no probe-specific correction).*

- **Counter Pulse Rate Calculation (Flow & Impeller RPM):**
  $$Y = \frac{f_{\text{Hz}}}{\text{hz\_per\_unit}}$$
  *(For Hall flowmeters: $f_{\text{Hz}} = 0.5 \cdot Q_{\text{L/min}}$, where 1 count over a 10-second window gives 0.2 L/min counting resolution. For impeller RPM: $\text{hz\_per\_unit} = \text{pulses\_per\_rev} / 60$).*

> [!NOTE]
> **No Clipping:** Values are deliberately never clipped at configured endpoints, preserving overrange evidence. Out-of-range signals receive quality flags (`AT_DAQ_LIMIT`, `OUTSIDE_NOMINAL_SIGNAL`, `OUTSIDE_SENSOR_FLOW_RANGE`).

### 4.2 Confirmation Checklist
- [ ] **Measured Shunt Resistance:** Enter exact measured ohms under `shunt_ohm` for each current loop (`R1`–`R5`).
- [ ] **Limits:** Enter verified minimum/maximum physical endpoints ($Y_{\min}$, $Y_{\max}$) using standard units (`degC`, `Pa`, `percent_RH`, `m`, `W`).
- [ ] **Counter Calibrations:** Confirm the actual `hz_per_unit` coefficients for `water_flow_in`, `water_flow_out`, and `impeller_rpm`.
- [ ] **Confirm Scales:** Set `scale.confirmed: true` on all 7 analog channels and `calibration_confirmed: true` on all 3 counter channels.
- [ ] **Record Provenance:** Enter a meaningful `calibration_id` or datasheet reference for each confirmed channel. In this application, *confirmed* means the transfer function is established.
- [ ] **Store Calibration Certificates:** Store digital certificates, factory inspection sheets, or measurement logs in [`docs/calibrations/`](calibrations/README.md) and record their file path and metadata in [`docs/calibrations/CAL-INDEX.csv`](calibrations/CAL-INDEX.csv). Binary assets (PDFs, scans, images) in `docs/calibrations/` are tracked via **Git Large File Storage (Git LFS)** as defined in [`.gitattributes`](../.gitattributes). Run `git lfs install` before adding large files.

---

## Phase 5: Powered-Rig Pilot & Operational Acceptance

Once all scales are confirmed (refer to [`configs/pilot.demo.yaml`](../configs/pilot.demo.yaml) as an example of a fully confirmed and calibrated pilot configuration), execute calibrated acquisition:

```powershell
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --acknowledge-wiring --duration 3600
```
*(Omit `--duration` for an operator-stopped run. The terminal process must remain active; do not allow Windows sleep or hibernation).*

- [ ] **Electrical Noise Evaluation:** Energize agitator motor, heater, and fan under independent laboratory control. Inspect raw signal noise for VFD ground loops or inductive coupling. (A software filter or rolling window is not a substitute for proper grounding and shielding).
- [ ] **Live Monitor Test:** In a second terminal window, verify real-time monitoring runs without interfering with acquisition:
  ```powershell
  .\.venv\Scripts\python.exe -m tankdaq watch "$run"
  ```
- [ ] **Graceful Interruption Test:** Stop a test run using `Ctrl+C`. Verify that tasks release cleanly, status finalizes as `interrupted`, and buffered samples are completely drained.
- [ ] **Data Export Verification:** Verify data export to CSV (and Parquet if PyArrow is installed). If `auto_export_csv: true` was enabled in `storage:`, the export folder (`export_csv_<hash>/`) is created automatically upon run finalization. Otherwise, export manually:
  ```powershell
  .\.venv\Scripts\python.exe -m tankdaq export "$run" --format csv
  ```
- [ ] **Archive Experimental Records:** Save the run folder, `devices.json`, `metadata.json`, calibration certificates, and pilot logs into long-term research storage.

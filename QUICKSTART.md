# Quick start

Extract the project and open PowerShell in the `agitated-tank-daq` folder. Python 3.11–3.13 are supported (Python 3.12 or 3.13 recommended).

## Demonstrate without hardware

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tankdaq inspect examples\simulated_run
.\.venv\Scripts\python.exe -m tankdaq watch examples\simulated_run --once
.\.venv\Scripts\python.exe -m tankdaq run --config configs\demo.yaml --backend sim --duration 15
```

## Prepare for the real rig

1. Install a Windows NI-DAQmx driver version supporting cDAQ-9173, NI-9217,
   NI-9204, and NI-9411 (or NI-9401).
2. Close NI MAX test panels and any LabVIEW programs.
3. Install the NI Python interface and inspect the connected hardware:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ni,test]"
.\.venv\Scripts\python.exe -m tankdaq devices --output devices.json
Copy-Item configs\rig.yaml configs\rig.local.yaml
notepad configs\rig.local.yaml
```

Set actual device/resource names (cDAQ-9173 chassis with NI-9217, NI-9204, and NI-9411 or NI-9401 digital module; channel names can be customized). Note that `configs/*.local.yaml` and `devices.json` are git-ignored. Complete the four physical-verification checks;
set their fields true only when verified. The unknown analog and counter scales may remain
unconfirmed for raw commissioning:

```powershell
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring --duration 60
```

After sensor ranges, measured shunt resistances and counter coefficients are
confirmed in `rig.local.yaml`, run without `--raw-only`:

```powershell
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --acknowledge-wiring --duration 3600
```

Every run stores a unique SQLite record and metadata. Real NI runs also request
per-task TDMS. Cross-module timestamps are estimates, not hardware-synchronized.
This is acquisition software, not motor control or an emergency stop.

Validation: 61 automated tests passed (includes custom channel naming, 3-channel counter support, and NI-9401/NI-9411 support). Physical
NI hardware and Windows acceptance testing remain outstanding. See TEST_REPORT.md.

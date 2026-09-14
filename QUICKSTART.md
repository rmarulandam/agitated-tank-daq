# Quick start

Extract the ZIP and open PowerShell in the `agitated-tank-daq` folder.

## Demonstrate without hardware

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m tankdaq run --config configs\demo.yaml --backend sim --duration 60
$run = (Get-ChildItem .\runs -Directory | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
.\.venv\Scripts\python.exe -m tankdaq inspect "$run"
.\.venv\Scripts\python.exe -m tankdaq export "$run" --format csv
```

In another terminal, `python -m tankdaq watch "$run"` provides a live text display.
Use the virtual environment's Python path as above. The monitor can stop without
stopping acquisition. Ctrl+C in the acquisition terminal stops that run.

## Before using the real rig

Read `README.md` and `docs/COMMISSIONING.md`. Install the NI-DAQmx driver separately.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ni,test]"
.\.venv\Scripts\python.exe -m tankdaq devices --output devices.json
Copy-Item configs\rig.yaml configs\rig.local.yaml
notepad configs\rig.local.yaml
```

Set actual device/resource names. Complete the four physical-verification checks;
set their fields true only when verified. The unknown analog scales may remain
unconfirmed for raw commissioning:

```powershell
.\.venv\Scripts\python.exe -m tankdaq run --config configs\rig.local.yaml --backend ni --raw-only --acknowledge-wiring --duration 60
```

For engineering-unit acquisition, establish and confirm every transmitter range
and the Hall coefficient in the config, then omit `--raw-only`.

Default rates: RTD 1 sample/s/channel, analog 10 samples/s/channel, counter polling
2/s with a 10-second rolling flow window. Impeller RPM is an external record.

Every run stores a unique SQLite record and metadata. Real NI runs also request
per-task TDMS. Cross-module timestamps are estimates, not hardware-synchronized.
This is acquisition software, not motor control or an emergency stop.

Validation: 52 automated tests passed, one optional Parquet test skipped. Physical
NI hardware and Windows acceptance testing remain outstanding. See TEST_REPORT.md.

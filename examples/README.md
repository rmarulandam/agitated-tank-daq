# Example data

`simulated_run/` is a real output of a 12-second wall-clock execution of the supplied
simulator. It contains all eleven configured RTD/analog channels, Hall-counter
snapshots, metadata and CSV exports. Every sample is marked SIMULATED. It is not
experimental evidence or a calibrated physical model of the tank.

Inspect it after installing the package:

```powershell
.\.venv\Scripts\python.exe -m tankdaq inspect examples\simulated_run
.\.venv\Scripts\python.exe -m tankdaq watch examples\simulated_run --once
```

The raw file is SQLite; the simulated backend deliberately does not create NI TDMS
files. Absolute build-host paths in the generated export manifest record where
this sample was generated; no such path is required to use the project.

`external_rpm_TEMPLATE.csv` is a blank header template for your separate,
externally calculated RPM record. It contains no invented RPM observations.

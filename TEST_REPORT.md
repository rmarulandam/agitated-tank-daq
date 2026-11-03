# Release test report - Agitated Tank DAQ 0.1.0

## Executed in the build environment

- Automated suite: **66 passed**. The included `TEST_OUTPUT.txt` is the captured pytest result.
- Configuration checks: required measurement set (4 RTD, 7 analog, 3 counter channels), differential-pair mapping, unique counter/PFI routing, exact hardware acknowledgement, simulation/hardware separation, required engineering-scale confirmations, invalid rates and acquisition-range checks.
- Numerical tests: current-loop and 0–10 V voltage-linear transfer functions, measured shunt resistance, null handling, unclipped overrange, 32-bit pulse-count rollover, nonuniform polling times, warm-up, zero-pulse ambiguity and rolling-window flow/RPM calculation.
- Integration tests: actual simulator producers, transactional SQLite writes, contiguous sample indices, raw-only mode, CSV and Parquet export, operator notes, external RPM attachment, display-only monitor, injected worker failure, low-disk refusal and explicit queue-overflow failure.
- NI contract tests: fake API objects with explicit method signatures checked the application's construction of four RTD channels, seven differential voltage channels, three edge-counting counter tasks (`ctr0`–`ctr2` on `PFI0`–`PFI2`), internal RTD excitation/ADC settings, and driver-logging requests. Inventory tests check wrong module/resource rejection and rejection of NI-MAX simulated hardware. These are NOT installed-driver tests.
- Additional subprocess shutdown test: SIGINT produced exit code 130, status `interrupted`, and closure of all simulator workers on the build host.
- Additional 12-second wall-clock simulation: completed, with **48 RTD rows, 840 analog-voltage rows, and 75 counter rows (25 polls across 3 counter channels)**. SQLite quick_check returned `ok`; CSV export succeeded. This run is included under `examples/simulated_run/`.
- Python source compilation: succeeded.
- Packaging: a Python wheel was built without fetching dependencies, installed into a separate test directory, and its CLI successfully read the included sample run.
- Missing NI-package path: `tankdaq devices` returned a clear installation error and exit status 2; it did not silently use simulated hardware.

Build environment: CPython 3.13.5, NumPy, PyYAML, PyArrow, pytest 9.0.2. See the example run's metadata for the detailed environment and source hash.

## Not executed or not established

**No physical NI hardware or NI-DAQmx driver was available.** Real device enumeration, actual task/route reservation, hardware sampling, RTD ADC behavior, hardware disconnect handling, hardware stop/drain behavior, and driver-generated TDMS files remain subject to commissioning on the experiment PC. The official NI Python API documentation was consulted, but a compatible installed-driver matrix was not tested.

PyArrow is available; Parquet and CSV export tests were both executed successfully.

The simulator does not validate electronics, grounding, transmitter outputs, calibration, fluid/thermal physics, duct installation or experiment accuracy. Neither the simulator nor fake NI objects reproduce NI hardware timing. Cross-module hardware synchronization is not implemented or claimed. Physical emergency-stop and motor/pump shutdown are outside the application.

This is a runnable software release with application-level test evidence, not a certification of the installed experiment.

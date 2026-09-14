# Release test report - Agitated Tank DAQ 0.1.0

## Executed in the build environment

- Automated suite: **52 passed, 1 skipped**. The included `TEST_OUTPUT.txt` is the captured pytest result.
- Configuration checks: required measurement set, differential-pair mapping, exact hardware acknowledgement, simulation/hardware separation, required engineering-scale confirmations, invalid rates and acquisition-range checks.
- Numerical tests: current-loop and voltage transfer functions, measured shunt resistance, null handling, unclipped overrange, 32-bit pulse-count rollover, nonuniform polling times, warm-up, zero-pulse ambiguity and rolling-window flow.
- Integration tests: actual simulator producers, transactional SQLite writes, contiguous sample indices, raw-only mode, CSV export, operator notes, external RPM attachment, display-only monitor, injected worker failure, low-disk refusal and explicit queue-overflow failure.
- NI contract tests: fake API objects with explicit method signatures checked the application's construction of four RTD channels, seven differential voltage channels, internal RTD excitation/ADC settings, edge-counter terminal routing and driver-logging requests. Inventory tests check wrong module/resource rejection and rejection of NI-MAX simulated hardware. These are NOT installed-driver tests.
- Additional subprocess shutdown test: SIGINT produced exit code 130, status `interrupted`, and closure of all simulator workers on the Linux build host.
- Additional 12-second wall-clock simulation: completed, with **48 RTD rows, 840 analog-voltage rows, and 25 counter polls**. SQLite quick_check returned `ok`; CSV export succeeded. This run is included under `examples/simulated_run/`.
- Python source compilation: succeeded.
- Packaging: a Python wheel was built without fetching dependencies, installed into a separate test directory, and its CLI successfully read the included sample run.
- Missing NI-package path: `tankdaq devices` returned a clear installation error and exit status 2; it did not silently use simulated hardware.

Build environment: Linux, CPython 3.13.5, NumPy 2.3.5, PyYAML 6.0.3, pytest 9.0.2. See the example run's metadata for the detailed environment and source hash.

## Not executed or not established

**No physical NI hardware, NI-DAQmx driver or Windows environment was available.** Real device enumeration, actual task/route reservation, hardware sampling, RTD ADC behavior, hardware disconnect handling, hardware stop/drain behavior, and driver-generated TDMS files remain subject to commissioning on the experiment PC. The official NI Python API documentation was consulted, but a compatible installed-driver matrix was not tested.

The optional PyArrow package was unavailable, so the Parquet execution test was skipped. Its export implementation is included but not executed in this environment. CSV export was executed successfully.

The simulator does not validate electronics, grounding, transmitter outputs, calibration, fluid/thermal physics, duct installation or experiment accuracy. Neither the simulator nor fake NI objects reproduce NI hardware timing. Cross-module hardware synchronization is not implemented or claimed. Physical emergency-stop and motor/pump shutdown are outside the application.

This is a runnable software release with application-level test evidence, not a certification of the installed experiment.

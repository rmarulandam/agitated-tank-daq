# Hardware commissioning checklist

This is an acquisition-software checklist, not a replacement electrical installation design. Only a qualified person responsible for the laboratory setup should energize the rig. The software cannot verify physical connector pin numbering, instrument common mode, protective earth, branch protection or isolation.

## Before acquisition

Keep motors and other actuators independently disabled during signal checkout. Verify the actual modules are NI-9217, NI-9204 and the added NI-9411 in a cDAQ-9173. Confirm that the NI-9411 is actually installed: it was an addition to the original two-module quotation. Install supported NI-DAQmx drivers and confirm device names/resources with NI MAX and `tankdaq devices`. Close test panels before running the application.

Check the four sensor-side RTD lead pairs and the installed standard curve. The template selects NI PT_3851, four wires, 100 ohms and 1 mA internal excitation. The quotation gives a rounded alpha; use the delivered sensor documentation/certificate to settle the curve. Do not apply 24 V to RTD terminals. The `rtd_curve_verified` check is a physical/documentary acknowledgement, not a software identification procedure.

Confirm 24 V and 5 V power distribution, sensor return/common arrangements and protective bonding independently of signal cables. Confirm each NI-9204 differential pair, its common-mode voltage relative to COM and polarity. The input range is not a substitute for verifying common-mode limits. Measure and record R1-R5; do not confuse nominal resistor tolerance with calibrated shunt uncertainty. Verify current-loop compliance with the shunt burden. This software reads voltage across those shunts, never commands current.

The Changor dual-loop wiring remains provisional until confirmed on the actual unit. Confirm whether each transmitter is active-output or two-wire loop-powered. Confirm that the atmospheric-pressure unit is actually the 4-20 mA variant. A delivered RS485-only transmitter requires different hardware/software integration; this release has no Modbus backend. The water-pressure voltage variant, pinout, supply and gauge/absolute reference must be established. Never use the provisional 0.5-4.5 V curve for a 0-5 V unit.

Confirm differential-air-pressure range, sign and pressure-port assignment. Confirm the selected airflow transmitter's actual model, configured velocity range and output, and the representativeness of its duct installation. The software deliberately does not pick an AliExpress range or claim that an unspecified sensor measures mean cross-sectional velocity.

For the Hall sensor, confirm output topology, logic level, pull-up requirements and NI-9411 single-ended/differential wiring from the actual manuals. The flow-task code routes the configured PFI input to a counter; it does not configure a missing external pull-up. Confirm `devices.json` enumerates the counter resource and PFI terminal you intend to use.

## Signal injection and quiet tests

With field equipment appropriately disconnected, use a suitable calibrator and reference meter to check each voltage/current input. Verify the raw voltage near the intended minimum, midpoint and maximum. For each measured 250-ohm shunt, a nominal 4/12/20 mA input should produce approximately 1/3/5 V; use measured resistance when assessing the expected value. Record observed deviations and instrument calibration information.

For RTDs, use a suitable resistance standard or known-temperature comparison appropriate for four-wire measurements. Verify channel labels and physical locations before relying on inlet/outlet differences. Check expected ambient readings without treating agreement between sensors as a traceable calibration.

Use a compatible pulse source, safely conditioned for the NI-9411, to check increasing counts and the configured coefficient. Check a stopped pulse train: frequency must eventually become zero after the rolling window clears, with a no-pulse ambiguity flag. Check pulse rates over the intended operating range. Confirm count polling remains responsive when no pulses arrive.

Only after the physical checks are complete should the four `checks` fields be marked true. Start with `--raw-only` for at least 60 seconds. Inspect all eleven analog/RTD channel records plus the counter. The seven transmitter engineering values and water-flow engineering value should remain null in raw-only mode; DAQmx RTD temperatures and raw voltages/counts remain available.

## Scale establishment

Fill exact engineering endpoints and voltage/current endpoints from delivered sensors and calibration. Set `confirmed` only after the intended transfer function has been established; record its source under `calibration_id`. For current loops, enter actual shunt resistance. For water pressure, settle both voltage endpoints and pressure reference. Use Pa consistently for pressure outputs. Confirm the Hall Hz-per-(L/min) coefficient rather than silently relying on the quotation for a different model.

Individual RTD correction is `gain * DAQmx_temperature + offset_c`. Default gain 1/offset 0 means no individual correction, not proof of calibrated probes. The software does not estimate coefficients or uncertainty from calibration data.

## Powered-rig checks and acceptance

Run with motors off, then with the actual fan/impeller operating under independent laboratory controls. Compare raw signal noise and offsets. A software lowpass or long averaging window is not a remedy for unsafe/common-mode wiring. Verify every cable label, pressure tap and logged channel against physical changes one at a time.

Exercise Ctrl+C and timed termination; verify all tasks release and the next run starts. Simulate signal loss using a safe procedure; verify faults/quality flags and retained raw data. A program shutdown does not stop the motor or pump. Check the laboratory emergency stop independently.

For a representative-duration pilot, confirm no missing required streams, contiguous indices per stream, expected actual rates, adequate free disk, final status and SQLite integrity. Check `metadata.json`, events, TDMS files and CSV export. Verify how external RPM timestamps align. Archive the config, sensor/DAQ identifiers, calibration records and pilot results.

This release has not been commissioned on the physical rig. Passing the included software tests is not a substitute for this acceptance process.

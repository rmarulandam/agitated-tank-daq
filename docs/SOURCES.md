# Source basis and unresolved details

## User-supplied project sources

1. **DAQ Solutions DSC-742-R3, 06/02/2026, pages 1-2**, supplied file `DSC-742-R3 Universidad de los Andes_Suministro de sensores.pdf`. Supports the four TL4050 PT100 four-wire probes, Changor T/RH transmitter with listed 4-20 mA output, atmospheric transmitter with listed alternative output types, G1-1/2 Hall flow sensor with 5-150 L/min range and quoted F=0.5*Q relation, and two 0-80 psi pressure sensors with alternative voltage outputs. It does not settle all delivered variants, connector pinouts or transmitter scaling endpoints. No missing details were promoted to verified sensor specifications.
2. **DAQ Solutions DSC-737-R1, 22/10/2025, pages 1-2**, supplied file `DSC-737-R1 Universidad de los Andes_Equipos academicos para la toma de valores de temperatura, humedad y presion.pdf` (original filename uses accents). Supports the cDAQ-9173, NI-9204, NI-9217 and ten precision 250-ohm resistors. It does not include the subsequently proposed NI-9411.
3. **Agreed wiring specification in this conversation**. Sets the four temperature locations, two provisional independent Changor outputs, analog differential-pair allocation, NI-9411 Hall acquisition, additional duct differential-pressure and air-velocity measurements, and impeller RPM recorded/calculated outside cDAQ.

The implementation takes these as its experimental basis. The code does not depend on other thesis files or claim that they were retrieved during software development.

## Primary NI documentation checked for implementation

These are external API/hardware behavior references, distinct from the user's sensor specifications. Checked for this release on 2026-09-06 (the build's UTC timestamps may be on the following day).

- Official NI Python interface, installation and driver dependency:
  https://nidaqmx-python.readthedocs.io/en/
- Task/channel creation, including explicit RTD excitation and four-wire arguments:
  https://nidaqmx-python.readthedocs.io/en/stable/task_collections.html
- Stream configuration, TDMS LOG_AND_READ, auto-start and buffers:
  https://nidaqmx-python.readthedocs.io/en/stable/task.html
- AnalogMultiChannelReader bulk reads:
  https://nidaqmx-python.readthedocs.io/en/stable/stream_readers.html
- ADC timing modes and count-input source terminal properties:
  https://nidaqmx-python.readthedocs.io/en/stable/task_channels.html
- Constants including logging modes, overwrite policy and ADC mode:
  https://nidaqmx-python.readthedocs.io/en/stable/constants.html
- Device/channel/terminal inventory:
  https://nidaqmx-python.readthedocs.io/en/stable/device.html
- cDAQ-9173/9177 independent analog input timing engines:
  https://www.ni.com/docs/en-US/bundle/cdaq-9170-9173-9177/page/performing-analog-input.html
- NI-DAQmx cumulative edge-count behavior (explicit Start, then repeated Read):
  https://www.ni.com/docs/en-LS/bundle/ni-daqmx/page/edge-counting.html
- NI-9217 datasheet, internal 1 mA excitation and scanned conversion architecture:
  https://download.ni.com/support/manuals/374187a_02.pdf

The API reference presented version 1.6.0 when inspected. The project accepts nidaqmx >=1.4,<2; the NI package and NI driver were not executable in the build environment. The fake API tests verify the application's intended call construction, not a installed-driver compatibility matrix.

## Deliberate unresolved items

Unknown analog engineering endpoints are null or explicitly unconfirmed in `rig.yaml`. The water-pressure range and barometer range transcribe the quotation but remain unconfirmed for the delivered unit. `demo.yaml` ranges are illustrative and cannot be used with the NI backend. PT_3851 is a configurable NI standard-curve choice that requires verification. Physical pin-number verification belongs to electrical commissioning, not the software's channel-name validation.

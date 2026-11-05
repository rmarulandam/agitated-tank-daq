# Changelog

## 0.1.0

Initial acquisition-only implementation for the agreed agitated-tank instrumentation.
Includes simulator, two NI AI tasks, Hall edge counting, configuration/confirmation gates,
raw and engineering logging, driver TDMS request, SQLite, optional Parquet and standard CSV
export, terminal monitoring, hardware counter impeller RPM acquisition on cDAQ1Mod3/ctr2,
paired Changor temperature and relative humidity transmitter channels for inlet and outlet air,
standardized exclusively on the installed NI-9401 digital module (removing NI-9411 references
and enforcing NI-9401 module validation in the inventory verification check),
commissioning docs and software tests.
Hardware commissioning is pending; no physical-hardware validation is claimed.

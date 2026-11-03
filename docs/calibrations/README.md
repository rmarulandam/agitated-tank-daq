# Sensor Calibration Certificates & Provenance Records

This directory stores calibration certificates, manufacturer inspection reports, factory test sheets, and shunt measurement records for all instruments connected to the agitated tank DAQ rig.

## Directory Structure

```text
docs/calibrations/
├── README.md               # This index and procedure guide
├── CAL-INDEX.csv           # Structured register mapping channel name -> calibration_id -> file
├── templates/              # Optional template files (e.g. shunt resistance logging sheet)
└── <calibration_files>     # Certificate files (PDF, image, or text/CSV)
```

## Large File Storage (Git LFS)

To avoid repository bloat as calibration PDFs and high-resolution scans are added, repository-level Git LFS rules are preconfigured in `.gitattributes` for `docs/calibrations/*`:
* `*.pdf`, `*.PDF`
* `*.png`, `*.jpg`, `*.jpeg`, `*.tif`, `*.tiff`

### Installing & Using Git LFS

1. Ensure Git LFS is installed on your workstation (if using Windows, Git for Windows includes Git LFS):
   ```powershell
   git lfs install
   ```
2. When adding a new certificate to this directory, stage and commit normally:
   ```powershell
   git add docs/calibrations/CAL-2026-PT100-01.pdf
   git commit -m "docs: add PT100 probe 1 calibration certificate"
   ```
3. To verify that a file is managed via Git LFS:
   ```powershell
   git lfs ls-files
   ```

## Calibration Register (`CAL-INDEX.csv`)

Whenever a sensor's transfer function is established and its `calibration_id` is updated in `configs/rig.local.yaml`, document it in [CAL-INDEX.csv](file:///docs/calibrations/CAL-INDEX.csv) using the following columns:

| Column | Description | Example |
| :--- | :--- | :--- |
| `channel_name` | Rig channel identifier | `t_water_in_c` |
| `physical_terminal` | NI terminal | `cDAQ1Mod1/ai0` |
| `sensor_model` | Instrument model / type | `Omega Class A Pt100 4-wire` |
| `sensor_serial` | Physical serial number | `SN-74892` |
| `calibration_id` | Matching ID string in `rig.local.yaml` | `CAL-2026-PT100-01` |
| `calibrated_date` | Date of verification or certificate | `2026-10-15` |
| `certificate_file` | Relative path to certificate file | `CAL-2026-PT100-01.pdf` |
| `transfer_function_summary` | Summary of scale/curve used | `IEC 60751 standard curve PT_3851 (gain=1.0, offset=0.0)` |
| `notes` | Lab / metrology comments | `Ice bath test verified 0.02 C offset` |

## Naming Convention

Name certificate files after their `calibration_id` or sensor serial number:
* `CAL-<YEAR>-<SENSOR_TAG>.pdf` (e.g., `CAL-2026-PT100-01.pdf`, `CAL-2026-DP-AI4.pdf`)
* `MFR-<MODEL>-<SERIAL>.pdf` (e.g., `MFR-YOKOGAWA-EJA110E-98421.pdf`)


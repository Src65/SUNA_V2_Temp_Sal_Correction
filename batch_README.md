## Temperature and Salinity Input

The temperature/salinity correction requires external temperature and
salinity measurements corresponding to the SUNA measurement times.

By default, temperature/salinity CSV files are expected to contain:

- `utc_time` — measurement date and time in UTC
- `temp` — water temperature in degrees Celsius
- `sal` — salinity in PSU

Example:

| utc_time | temp | sal |
|---|---:|---:|
| 2026-09-01T08:00:03Z | 13.6745 | 32.9150 |
| 2026-09-01T08:05:02Z | 13.6328 | 32.9195 |

Multiple CSV files may be placed in the T/S input directory. The batch
processor combines the files chronologically and linearly interpolates
temperature and salinity to the exact time of each SUNA measurement.

Interpolation is not performed across gaps larger than
`MAX_TS_GAP_MINUTES`.

### QC Flags

Existing QC flag columns are **not required** in the temperature/salinity
input files.

The nitrate temperature/salinity correction itself requires only:

1. A SUNA FULL_ASCII spectrum
2. The appropriate SUNA `.CAL` file
3. Water temperature
4. Salinity
5. Measurement time so the SUNA and T/S observations can be matched

QC flags are therefore **not inputs to the nitrate correction calculation**.

The batch processor generates the following QC fields for the output:

- `nitrate_flg` — QC flag for the original SUNA nitrate measurement
- `temp_flg` — QC flag for the external temperature measurement
- `sal_flg` — QC flag for the external salinity measurement

These flags provide data-quality information but are not used as
coefficients or inputs in the Sakamoto temperature/salinity correction.

The current batch implementation reproduces the range-based QC checks used
by the MLML seawater intake acquisition system:

| Variable | User Range | Sensor Range |
|---|---:|---:|
| Nitrate | 0–60 µmol/L | 0–4000 µmol/L |
| Temperature | 7.5–20 °C | -5–35 °C |
| Salinity | 31–35 PSU | 20–50 PSU |

The live MLML acquisition system also performs history-dependent tests such
as spike and flatline detection. These tests require recent observations
from the monitoring database and therefore are not reproduced by the
standalone historical batch processor.

### Different T/S File Formats

The current batch processor expects the column names:

`utc_time`, `temp`, and `sal`

Temperature/salinity data from another instrument or logger can still be
used, but the input file must currently be converted or renamed to these
column names before processing.

Existing QC columns, instrument-specific metadata, and other columns may
remain in the CSV; they are not required by the nitrate correction.

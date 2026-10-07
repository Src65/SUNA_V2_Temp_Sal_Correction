## Batch Processing Historical SUNA Data

`SUNA_batch_processor.py` provides batch temperature and salinity
correction of historical SUNA V2 FULL_ASCII data.

The processor:

- Searches a directory for SUNA files containing `SATSLF` records.
- Searches a separate directory for temperature/salinity CSV files.
- Converts the SUNA year/day-of-year timestamps to UTC.
- Matches each SUNA measurement to external temperature and salinity.
- Linearly interpolates T/S to the exact SUNA measurement time.
- Rejects interpolation across T/S gaps greater than the configured limit.
- Applies the same Sakamoto et al. (2009) correction implemented in
  `suna_tscorrection.py`.
- Preserves the original SUNA nitrate concentration.
- Calculates corrected nitrate and nitrate-N.
- Recreates the original range-based nitrate, temperature, and salinity
  QC flags.
- Preserves correction RMSE and number of fitted spectral channels as
  diagnostic information.
- Writes all processed measurements to a single chronological CSV.

### Configuration

Edit the user settings near the top of `SUNA_batch_processor.py`:

```python
SUNA_DIR = Path(r"C:\path\to\SUNA\data")
TS_DIR = Path(r"C:\path\to\temperature_salinity\data")
CAL_FILE = Path(r"C:\path\to\SUNA_1110.CAL")

OUTPUT_DIR = Path(r"C:\path\to\output")
OUTPUT_FILE = OUTPUT_DIR / "corrected_nitrate.csv"

MAX_TS_GAP_MINUTES = 15.0

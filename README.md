# SUNA V2 Temperature and Salinity Correction

Real-time Python temperature and salinity correction for SUNA V2 nitrate measurements using external T/S data and the Sakamoto et al. (2009) method.

## Overview

The SUNA V2 calculates nitrate concentration from UV absorbance spectra. In seawater, changes in temperature and salinity affect the UV absorption spectrum and can introduce error into the nitrate measurement.

This project provides a Python implementation for applying an external temperature and salinity correction to SUNA V2 `FULL_ASCII` data.

The correction is designed to operate independently of the SUNA's internal CTD configuration. Temperature and salinity can therefore come from an external CTD or other instrument and be supplied directly to the Python processing routine.

The original nitrate concentration calculated by the SUNA is always retained.

## Features

- Reads SUNA V2 `SATSLF` FULL_ASCII records
- Preserves the original SUNA onboard nitrate result
- Uses an instrument-specific SUNA `.CAL` file
- Accepts external temperature and salinity measurements
- Applies temperature-compensated salinity subtraction (TCSS)
- Calculates corrected nitrate in µM
- Calculates corrected nitrate-N in mg/L
- Returns fit RMSE and number of wavelengths used
- Supports real-time acquisition and correction
- Can be adapted for post-processing archived SUNA spectra
- Continues collecting original SUNA nitrate if external T/S data are unavailable
- Continues collecting original SUNA nitrate if the calibration file is unavailable

## Processing

The correction uses the full SUNA absorbance spectrum rather than attempting to modify the nitrate value reported by the instrument.

For each SUNA measurement:

1. Read the complete `SATSLF` FULL_ASCII record.
2. Extract the 256-channel intensity spectrum and dark value.
3. Calculate absorbance using the reference spectrum contained in the SUNA calibration file.
4. Adjust the seawater absorption spectrum for the measured water temperature.
5. Scale the seawater contribution using external salinity.
6. Subtract the temperature-corrected seawater contribution.
7. Fit nitrate extinction plus a linear baseline over the selected wavelength range.
8. Return the independently calculated temperature/salinity-corrected nitrate concentration.

The current implementation uses:

- **Wavelength range:** 216.5–240.0 nm
- **Maximum absorbance:** 1.3
- **Baseline:** Linear

## Output

The processing routine retains two distinct nitrate products:

| Variable | Description |
|---|---|
| `nitrate` | Original SUNA onboard nitrate concentration (µM) |
| `nitrogen` | Original SUNA onboard nitrate-N (mg/L) |
| `nitrate_corrected` | Externally temperature/salinity-corrected nitrate (µM) |
| `nitrogen_corrected` | Corrected nitrate-N (mg/L) |
| `correction_rmse` | RMSE of the corrected spectral fit |
| `correction_channels` | Number of spectral channels used in the fit |
| `baseline_intercept` | Fitted linear baseline intercept |
| `baseline_slope` | Fitted linear baseline slope |

The original SUNA nitrate measurement is **never overwritten** by the corrected result.

## External Temperature and Salinity

Temperature and salinity are supplied independently of the SUNA.

For example:

```python
suna = get_suna_data(
    temperature=17.57,
    salinity=32.90,
)
```

If external temperature and salinity are unavailable:

```python
suna = get_suna_data()
```

The SUNA is still polled normally and the original onboard nitrate result is returned. Temperature/salinity-corrected fields remain unavailable until valid external T/S measurements are supplied.

This allows SUNA acquisition to continue if an external CTD fails, is disconnected, or is removed from the system.

## Calibration File

Spectral processing requires the calibration file associated with the individual SUNA instrument.

Example:

```python
SUNA_CAL_FILE = "/path/to/SUNA_1110.CAL"
```

The calibration file supplies instrument-specific information including:

- Wavelength array
- Nitrate extinction coefficients
- Seawater extinction spectrum
- Temperature-dependent seawater information
- Reference spectrum
- Calibration temperature

Calibration files should be archived with the corresponding instrument and deployment records so historical `FULL_ASCII` data can be reprocessed in the future.

Failure to load the calibration file does **not** prevent collection of the original nitrate concentration reported by the SUNA. It only disables the external temperature/salinity correction.

## Raw Data Preservation

For reproducibility, the complete SUNA `FULL_ASCII` record should be retained whenever possible.

The corrected nitrate value is a derived product. Retaining the original spectrum allows measurements to be reprocessed later using:

- Revised processing algorithms
- Corrected external temperature or salinity
- Updated QC procedures
- Archived instrument calibration information

A historical nitrate value cannot be fully reprocessed if only the final onboard nitrate concentration was retained and the original spectrum is no longer available.

## Validation

The Python implementation was compared with processing performed using Sea-Bird UCI 2.0.4 using the same:

- SUNA calibration file
- `FULL_ASCII` spectra
- Temperature
- Salinity
- Wavelength range
- Absorbance limit
- Linear baseline configuration

The independently calculated Python results reproduced the UCI temperature/salinity-corrected nitrate results to rounding precision in the validation dataset.

## Failure Behavior

The acquisition system is designed so that failure of the external temperature/salinity source does not prevent collection of SUNA data.

If valid temperature and salinity are available:

```text
SUNA FULL_ASCII
      +
External Temperature/Salinity
      +
SUNA Calibration File
      |
      v
TCSS Processing
      |
      v
Corrected Nitrate
```

If external temperature or salinity is unavailable:

```text
SUNA FULL_ASCII
      |
      v
Original SUNA Nitrate
```

The original SUNA measurement is therefore retained regardless of whether the external correction can be performed.

## Units

| Parameter | Unit |
|---|---|
| Temperature | °C |
| Salinity | PSU |
| Nitrate | µmol/L (µM) |
| Nitrate-N | mg/L |
| Wavelength | nm |

Nitrate-N is calculated from nitrate concentration using the atomic mass of nitrogen.

## Intended Use

This project was developed for automated environmental monitoring where SUNA V2 measurements are collected alongside an independent temperature and salinity instrument.

Although initially implemented for real-time monitoring, the correction routine is intentionally separated from the source of the external T/S measurements.

This allows the same correction method to be used with:

- Sea-Bird CTDs
- Standalone conductivity/temperature sensors
- Multiparameter sondes
- Data loggers
- Shipboard systems
- Previously recorded temperature and salinity data
- Historical SUNA `FULL_ASCII` datasets

## Reference

Sakamoto, C. M., Johnson, K. S., & Coletti, L. J. (2009).

**Improved algorithm for the computation of nitrate concentrations in seawater using an in situ ultraviolet spectrophotometer.**

*Limnology and Oceanography: Methods, 7*, 132–143.

## Notes

This software calculates a derived nitrate product from SUNA spectral data. The original SUNA-reported nitrate concentration should be retained with the corrected result for data provenance and comparison.

Instrument-specific calibration files should also be permanently archived with the associated data.

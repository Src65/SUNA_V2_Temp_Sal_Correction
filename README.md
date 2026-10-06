# SUNA_V2_Temp_Sal_Correction
Real-time Python temperature and salinity correction for SUNA V2 nitrate measurements using external T/S data.

# SUNA V2 Temperature and Salinity Correction

Real-time Python temperature and salinity correction for SUNA V2 nitrate measurements using external T/S data and the Sakamoto et al. (2009) method.

## Overview

The SUNA V2 calculates nitrate concentration from UV absorbance spectra. In seawater, changes in temperature and salinity affect the UV absorption spectrum and can introduce significant error into the nitrate measurement.

This project provides a Python implementation for applying an external temperature and salinity correction to SUNA V2 FULL_ASCII data.

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

- Wavelength range: **216.5–240.0 nm**
- Maximum absorbance: **1.3**
- Baseline: **linear**

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

The original SUNA nitrate measurement is never overwritten by the corrected result.

## External Temperature and Salinity

Temperature and salinity are optional inputs to SUNA acquisition.

For example:

```python
suna = get_suna_data(
    temperature=17.57,
    salinity=32.90,
)

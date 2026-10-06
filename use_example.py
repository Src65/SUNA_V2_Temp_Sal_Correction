from suna_tscorrection import (
    load_suna_calibration,
    correct_suna_nitrate,
)

# Load the instrument-specific calibration once.
cal = load_suna_calibration(
    "SUNA_1110.CAL"
)

# FULL_ASCII SATSLF record received from SUNA.
suna_raw = "SATSLF1110,..."

# Temperature and salinity can come from any external instrument.
temperature = 17.57
salinity = 32.900

result = correct_suna_nitrate(
    suna_raw,
    temperature,
    salinity,
    cal,
)

print(
    "Corrected nitrate:",
    result["nitrate_corrected"],
    "uM"
)

print(
    "Corrected nitrate-N:",
    result["nitrogen_corrected"],
    "mg/L"
)

print(
    "Fit RMSE:",
    result["correction_rmse"]
)

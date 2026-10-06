"""
suna_tscorrection.py

Temperature and salinity correction for Sea-Bird SUNA V2
FULL_ASCII nitrate measurements.

Implements the temperature-compensated salinity subtraction (TCSS)
approach described by Sakamoto et al. (2009).

The implementation was validated against Sea-Bird UCI 2.0.4 using
the same SUNA calibration file, raw FULL_ASCII spectra, temperature,
salinity, wavelength range, absorbance limit, and linear baseline.

Requirements
------------
numpy
"""

import numpy as np


# ============================================================
# SUNA CALIBRATION FILE
# ============================================================

def load_suna_calibration(cal_file):
    """
    Load an instrument-specific Sea-Bird/Satlantic SUNA .CAL file.

    Parameters
    ----------
    cal_file : str
        Path to the SUNA calibration file.

    Returns
    -------
    dict
        Calibration information containing:

        wavelength : ndarray
            Spectrometer wavelengths in nm.

        no3 : ndarray
            Nitrate extinction coefficients.

        swa : ndarray
            Seawater extinction coefficients.

        tswa : ndarray
            Temperature-related seawater calibration column.

        reference : ndarray
            SUNA reference spectrum.

        t_cal : float
            Seawater calibration temperature in degrees C.
    """

    wavelengths = []
    no3_ext = []
    swa_ext = []
    tswa_ext = []
    reference = []

    t_cal = None

    with open(cal_file, "r", encoding="latin-1") as f:

        for raw_line in f:

            line = raw_line.strip()

            # Prefer the seawater calibration temperature.
            if line.startswith("H,T_CAL_SWA"):

                parts = line.split()

                if len(parts) >= 2:
                    t_cal = float(parts[-1])

            elif line.startswith("H,T_CAL ") and t_cal is None:

                parts = line.split()

                if len(parts) >= 2:
                    t_cal = float(parts[-1])

            # Calibration spectral rows:
            #
            # E,wavelength,NO3,SWA,TSWA,Reference
            #
            elif line.startswith("E,"):

                parts = line.split(",")

                if len(parts) >= 6:

                    wavelengths.append(float(parts[1]))
                    no3_ext.append(float(parts[2]))
                    swa_ext.append(float(parts[3]))
                    tswa_ext.append(float(parts[4]))
                    reference.append(float(parts[5]))

    if len(wavelengths) != 256:

        raise ValueError(
            f"Expected 256 SUNA calibration channels, "
            f"found {len(wavelengths)}"
        )

    if t_cal is None:

        raise ValueError(
            "Could not find T_CAL or T_CAL_SWA "
            "in SUNA calibration file"
        )

    return {
        "wavelength": np.asarray(wavelengths, dtype=float),
        "no3": np.asarray(no3_ext, dtype=float),
        "swa": np.asarray(swa_ext, dtype=float),
        "tswa": np.asarray(tswa_ext, dtype=float),
        "reference": np.asarray(reference, dtype=float),
        "t_cal": float(t_cal),
    }


# ============================================================
# SUNA TEMPERATURE / SALINITY CORRECTION
# ============================================================

def correct_suna_nitrate(
    full_ascii_line,
    temperature,
    salinity,
    calibration,
):
    """
    Apply temperature-compensated salinity subtraction (TCSS)
    to one SUNA SATSLF FULL_ASCII record.

    Parameters
    ----------
    full_ascii_line : str
        Complete SUNA SATSLF FULL_ASCII measurement record.

    temperature : float
        External water temperature in degrees C.

    salinity : float
        External practical salinity (PSU).

    calibration : dict
        Calibration dictionary returned by
        load_suna_calibration().

    Returns
    -------
    dict
        nitrate_corrected : float
            Corrected nitrate concentration in micromolar.

        nitrogen_corrected : float
            Corrected nitrate-N concentration in mg/L.

        correction_rmse : float
            RMSE of the spectral fit.

        correction_channels : int
            Number of spectral channels used.

        baseline_intercept : float
            Linear baseline intercept.

        baseline_slope : float
            Linear baseline slope.
    """

    # --------------------------------------------------------
    # Parse FULL_ASCII SUNA record
    # --------------------------------------------------------

    parts = [
        p.strip()
        for p in full_ascii_line.split(",")
    ]

    if not parts[0].startswith("SATSLF"):

        raise ValueError(
            "Input is not a SUNA SATSLF light frame"
        )

    # FULL_ASCII layout:
    #
    # field 9      = dark value
    # fields 11:267 = 256 spectrometer channels

    if len(parts) < 267:

        raise ValueError(
            f"Incomplete SUNA FULL_ASCII record: "
            f"only {len(parts)} fields"
        )

    dark = float(parts[9])

    intensity = np.asarray(
        [float(x) for x in parts[11:267]],
        dtype=float,
    )

    # --------------------------------------------------------
    # Calibration arrays
    # --------------------------------------------------------

    wl = calibration["wavelength"]
    no3_ext = calibration["no3"]
    swa_cal = calibration["swa"]
    reference = calibration["reference"]
    t_cal = calibration["t_cal"]

    temperature = float(temperature)
    salinity = float(salinity)

    if not np.isfinite(temperature):
        raise ValueError(
            "External temperature must be finite"
        )

    if not np.isfinite(salinity):
        raise ValueError(
            "External salinity must be finite"
        )

    # --------------------------------------------------------
    # Calculate SUNA absorbance
    #
    # A(lambda) =
    #     log10(
    #         REF(lambda) /
    #         (I(lambda) - I_dark)
    #     )
    # --------------------------------------------------------

    corrected_counts = intensity - dark

    valid_counts = (
        (corrected_counts > 0.0)
        & (reference > 0.0)
    )

    absorbance = np.full(
        256,
        np.nan,
        dtype=float,
    )

    absorbance[valid_counts] = np.log10(
        reference[valid_counts]
        / corrected_counts[valid_counts]
    )

    # --------------------------------------------------------
    # Sakamoto et al. (2009)
    # seawater temperature correction
    #
    # epsilon_SW(T) =
    #
    #     epsilon_SW(Tcal)
    #     * (F + T) / (F + Tcal)
    #     * exp[
    #           D * (lambda - 210)
    #           * (T - Tcal)
    #       ]
    #
    # F = A / B
    # --------------------------------------------------------

    SAKAMOTO_A = 1.1500276
    SAKAMOTO_B = 0.02840
    SAKAMOTO_D = 0.001222

    F = SAKAMOTO_A / SAKAMOTO_B

    temperature_factor = (
        (F + temperature)
        / (F + t_cal)
    )

    wavelength_factor = np.exp(
        SAKAMOTO_D
        * (wl - 210.0)
        * (temperature - t_cal)
    )

    swa_temperature_corrected = (
        swa_cal
        * temperature_factor
        * wavelength_factor
    )

    # --------------------------------------------------------
    # Temperature Compensated Salinity Subtraction
    # --------------------------------------------------------

    seawater_absorbance = (
        salinity
        * swa_temperature_corrected
    )

    tcss_absorbance = (
        absorbance
        - seawater_absorbance
    )

    # --------------------------------------------------------
    # Spectral fitting configuration
    #
    # Matches the UCI configuration used for validation:
    #
    # wavelength: 216.5 - 240.0 nm
    # max absorbance: 1.3
    # baseline: linear
    # --------------------------------------------------------

    fit_mask = (
        (wl >= 216.5)
        & (wl <= 240.0)
        & valid_counts
        & np.isfinite(absorbance)
        & np.isfinite(tcss_absorbance)
        & (absorbance <= 1.3)
    )

    n_channels = int(
        np.sum(fit_mask)
    )

    if n_channels < 10:

        raise ValueError(
            "Too few usable SUNA channels "
            f"for nitrate fit: {n_channels}"
        )

    fit_wl = wl[fit_mask]
    fit_no3 = no3_ext[fit_mask]
    fit_abs = tcss_absorbance[fit_mask]

    # --------------------------------------------------------
    # Least-squares nitrate fit
    #
    # corrected absorbance =
    #
    #     [NO3] * epsilon_NO3
    #     + intercept
    #     + slope * wavelength
    # --------------------------------------------------------

    X = np.column_stack(
        (
            fit_no3,
            np.ones(n_channels),
            fit_wl,
        )
    )

    coefficients, _, _, _ = np.linalg.lstsq(
        X,
        fit_abs,
        rcond=None,
    )

    nitrate_corrected = float(
        coefficients[0]
    )

    baseline_intercept = float(
        coefficients[1]
    )

    baseline_slope = float(
        coefficients[2]
    )

    # --------------------------------------------------------
    # Fit diagnostics
    # --------------------------------------------------------

    modeled_absorbance = (
        X @ coefficients
    )

    residual = (
        fit_abs
        - modeled_absorbance
    )

    rmse = float(
        np.sqrt(
            np.mean(
                residual ** 2
            )
        )
    )

    # --------------------------------------------------------
    # Convert nitrate µM to nitrate-N mg/L
    #
    # 1 µM N = 14.0067 µg/L N
    # --------------------------------------------------------

    nitrogen_corrected = (
        nitrate_corrected
        * 14.0067
        / 1000.0
    )

    return {
        "nitrate_corrected":
            nitrate_corrected,

        "nitrogen_corrected":
            nitrogen_corrected,

        "correction_rmse":
            rmse,

        "correction_channels":
            n_channels,

        "baseline_intercept":
            baseline_intercept,

        "baseline_slope":
            baseline_slope,
    }

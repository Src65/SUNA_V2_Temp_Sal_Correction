#!/usr/bin/env python3
"""
batch_process_suna.py

Batch-process directories of SUNA V2 FULL_ASCII files using external
temperature/salinity data stored in monthly CSV files.

Expected inputs
---------------
1. A directory containing SUNA files. Any file containing SATSLF records
   can be processed; file extension and filename do not determine dates.
2. A directory containing monthly T/S CSV files with columns:
       utc_time,temp,sal
3. One instrument-specific SUNA .CAL file.
4. suna_tscorrection.py in the same directory as this script.

Output
------
One chronologically sorted CSV containing original SUNA nitrate,
interpolated external T/S, original range-based QC flags, corrected nitrate,
fit diagnostics, and processing status.

Example
-------
python batch_process_suna.py \
    --suna-dir ./suna_data \
    --ts-dir ./temp_sal_data \
    --cal-file ./SUNA_1110.CAL \
    --output ./corrected_nitrate.csv
"""

from __future__ import annotations

import csv
import math
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from suna_tscorrection import load_suna_calibration, correct_suna_nitrate


OUTPUT_FIELDS = [
    "datetime_utc",
    "source_file",
    "source_line",
    "suna_serial",
    "nitrate_original_umol_L",
    "nitrogen_original_mg_L",
    "nitrate_flg",
    "temperature_C",
    "temp_flg",
    "salinity_PSU",
    "sal_flg",
    "ts_before_seconds",
    "ts_after_seconds",
    "nitrate_corrected_umol_L",
    "nitrogen_corrected_mg_L",
    "correction_rmse",
    "correction_channels",
    "baseline_intercept",
    "baseline_slope",
    "processing_status",
    "processing_message",
]


def finite_float(value: object) -> float:
    """Convert a value to finite float; return NaN if unavailable/invalid."""
    try:
        x = float(value)
        return x if math.isfinite(x) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def range_flag(value: float, minimum: float, maximum: float, fail_flag: int = 4) -> int:
    """
    Simple range flag used for historical batch reprocessing.

    1 = value is within the stated range
    fail_flag = value is outside the stated range or is not finite
    """
    if not math.isfinite(value):
        return fail_flag
    return 1 if minimum <= value <= maximum else fail_flag


def original_qc_flags(nitrate: float, temperature: float, salinity: float) -> dict:
    """
    Recreate the range-based portion of the original intake QC.

    The live intake script also applies history-dependent spike/flatline tests
    to temperature and salinity using recent database observations. Those
    database-history tests cannot be reproduced from the SUNA/T-S batch files
    alone, so this batch output uses the same sensor/user range limits.

    nitrate: sensor 0-4000 uM; user 0-60 uM
    temp:    sensor -5-35 C; user 7.5-20 C
    sal:     sensor 20-50 PSU; user 31-35 PSU
    """
    nitrate_flg = max(
        range_flag(nitrate, 0.0, 4000.0),
        range_flag(nitrate, 0.0, 60.0),
    )
    temp_flg = max(
        range_flag(temperature, -5.0, 35.0),
        range_flag(temperature, 7.5, 20.0),
    )
    sal_flg = max(
        range_flag(salinity, 20.0, 50.0),
        range_flag(salinity, 31.0, 35.0),
    )

    return {
        "nitrate_flg": nitrate_flg,
        "temp_flg": temp_flg,
        "sal_flg": sal_flg,
    }


def parse_iso_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and return timezone-aware UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        # The external T/S input is expected to be UTC.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_suna_datetime(parts: List[str]) -> datetime:
    """
    Parse SUNA fields:
        parts[1] = YYYYDDD (year + day of year)
        parts[2] = decimal UTC hour
    """
    yday = parts[1].strip()
    if len(yday) != 7 or not yday.isdigit():
        raise ValueError(f"Invalid SUNA YYYYDDD field: {yday!r}")

    year = int(yday[:4])
    day_of_year = int(yday[4:])
    decimal_hour = float(parts[2])

    if not (1 <= day_of_year <= 366):
        raise ValueError(f"Invalid SUNA day of year: {day_of_year}")
    if not (0.0 <= decimal_hour < 24.0):
        raise ValueError(f"Invalid SUNA decimal hour: {decimal_hour}")

    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    return start + timedelta(days=day_of_year - 1, hours=decimal_hour)


def suna_serial_from_header(field: str) -> str:
    """SATSLF1110 -> 1110."""
    field = field.strip()
    return field[len("SATSLF"):] if field.startswith("SATSLF") else ""


def load_ts_directory(ts_dir: Path) -> Tuple[List[datetime], List[float], List[float], int]:
    """
    Load all CSV files in a T/S directory.

    Required columns: utc_time, temp, sal

    Duplicate timestamps are collapsed by keeping the last valid row after
    chronological sorting.
    """
    records: Dict[datetime, Tuple[float, float]] = {}
    files_read = 0

    for path in sorted(ts_dir.glob("*.csv")):
        files_read += 1
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fields = set(reader.fieldnames or [])
            required = {"utc_time", "temp", "sal"}
            missing = required - fields
            if missing:
                raise ValueError(
                    f"{path.name} is missing required T/S columns: "
                    + ", ".join(sorted(missing))
                )

            for row_number, row in enumerate(reader, start=2):
                try:
                    dt = parse_iso_utc(row["utc_time"])
                    temp = finite_float(row["temp"])
                    sal = finite_float(row["sal"])
                    if math.isfinite(temp) and math.isfinite(sal):
                        records[dt] = (temp, sal)
                except Exception:
                    # A bad T/S row is skipped rather than aborting the entire batch.
                    continue

    if not records:
        raise ValueError(f"No valid T/S observations found in {ts_dir}")

    ordered = sorted(records.items(), key=lambda item: item[0])
    times = [item[0] for item in ordered]
    temps = [item[1][0] for item in ordered]
    sals = [item[1][1] for item in ordered]
    return times, temps, sals, files_read


def interpolate_ts(
    target: datetime,
    times: List[datetime],
    temps: List[float],
    sals: List[float],
    max_gap_seconds: float,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], str]:
    """
    Linearly interpolate T/S to the exact SUNA timestamp.

    Interpolation is only allowed when the SUNA observation is bracketed by
    valid T/S observations and the total bracket width is <= max_gap_seconds.

    Returns:
        temperature, salinity, seconds_to_before, seconds_to_after, status
    """
    i = bisect_right(times, target)

    # Exact timestamp at i-1.
    if i > 0 and times[i - 1] == target:
        return temps[i - 1], sals[i - 1], 0.0, 0.0, "OK"

    if i == 0 or i >= len(times):
        return None, None, None, None, "NO_TS_BRACKET"

    before_i = i - 1
    after_i = i

    before = times[before_i]
    after = times[after_i]

    before_sec = (target - before).total_seconds()
    after_sec = (after - target).total_seconds()
    span_sec = (after - before).total_seconds()

    if span_sec <= 0:
        return None, None, before_sec, after_sec, "INVALID_TS_INTERVAL"

    if span_sec > max_gap_seconds:
        return None, None, before_sec, after_sec, "TS_GAP"

    fraction = before_sec / span_sec
    temp = temps[before_i] + fraction * (temps[after_i] - temps[before_i])
    sal = sals[before_i] + fraction * (sals[after_i] - sals[before_i])

    return float(temp), float(sal), float(before_sec), float(after_sec), "OK"


def iter_suna_records(suna_dir: Path) -> Iterable[Tuple[Path, int, str]]:
    """
    Yield every SATSLF record from every regular file in the SUNA directory.
    Header/configuration lines are ignored.
    """
    for path in sorted(suna_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="latin-1", errors="replace") as f:
                for line_number, raw in enumerate(f, start=1):
                    line = raw.strip()
                    if line.startswith("SATSLF"):
                        yield path, line_number, line
        except OSError as exc:
            print(f"WARNING: could not read {path.name}: {exc}")


def process_record(
    path: Path,
    line_number: int,
    line: str,
    calibration: dict,
    ts_times: List[datetime],
    ts_temps: List[float],
    ts_sals: List[float],
    max_gap_seconds: float,
) -> dict:
    """Process one SUNA FULL_ASCII record without silently dropping failures."""
    row = {field: "" for field in OUTPUT_FIELDS}
    row["source_file"] = path.name
    row["source_line"] = line_number

    try:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 267:
            raise ValueError(f"incomplete FULL_ASCII record ({len(parts)} fields)")

        suna_dt = parse_suna_datetime(parts)
        row["datetime_utc"] = suna_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        row["suna_serial"] = suna_serial_from_header(parts[0])

        # SATSLF fields validated in the existing acquisition/correction workflow.
        nitrate_original = finite_float(parts[3])
        nitrogen_original = finite_float(parts[4])
        row["nitrate_original_umol_L"] = nitrate_original
        row["nitrogen_original_mg_L"] = nitrogen_original

        # Nitrate QC is based on the original onboard SUNA nitrate.
        row["nitrate_flg"] = original_qc_flags(
            nitrate_original, float("nan"), float("nan")
        )["nitrate_flg"]

        temp, sal, before_sec, after_sec, ts_status = interpolate_ts(
            suna_dt, ts_times, ts_temps, ts_sals, max_gap_seconds
        )

        if before_sec is not None:
            row["ts_before_seconds"] = before_sec
        if after_sec is not None:
            row["ts_after_seconds"] = after_sec

        if ts_status != "OK":
            row["processing_status"] = ts_status
            row["processing_message"] = (
                "No acceptable bracketing temperature/salinity observations"
            )
            return row

        row["temperature_C"] = temp
        row["salinity_PSU"] = sal

        qc = original_qc_flags(nitrate_original, temp, sal)
        row["nitrate_flg"] = qc["nitrate_flg"]
        row["temp_flg"] = qc["temp_flg"]
        row["sal_flg"] = qc["sal_flg"]

        result = correct_suna_nitrate(
            full_ascii_line=line,
            temperature=temp,
            salinity=sal,
            calibration=calibration,
        )

        row["nitrate_corrected_umol_L"] = result["nitrate_corrected"]
        row["nitrogen_corrected_mg_L"] = result["nitrogen_corrected"]
        row["correction_rmse"] = result["correction_rmse"]
        row["correction_channels"] = result["correction_channels"]
        row["baseline_intercept"] = result["baseline_intercept"]
        row["baseline_slope"] = result["baseline_slope"]
        row["processing_status"] = "OK"
        row["processing_message"] = ""

    except Exception as exc:
        row["processing_status"] = "PROCESSING_FAILED"
        row["processing_message"] = str(exc)

    return row



# ============================================================
# USER SETTINGS - EDIT THESE PATHS IF NEEDED
# ============================================================

SUNA_DIR = Path(r"C:\Users\009855027\Documents\pumphouse")
TS_DIR = Path(r"C:\Users\009855027\Documents\tc_lauren")
CAL_FILE = Path(r"C:\Users\009855027\Documents\Sea-Bird-Scientific\SUNA\SUNA_1110.CAL")

OUTPUT_DIR = Path(r"C:\Users\009855027\Documents\laurn_out")
OUTPUT_FILE = OUTPUT_DIR / "corrected_nitrate.csv"

# Do not interpolate across a T/S interval larger than this.
MAX_TS_GAP_MINUTES = 15.0


def main() -> int:
    """Run the complete batch processor using the USER SETTINGS above."""

    if not SUNA_DIR.is_dir():
        raise FileNotFoundError(f"SUNA directory not found: {SUNA_DIR}")

    if not TS_DIR.is_dir():
        raise FileNotFoundError(f"T/S directory not found: {TS_DIR}")

    if not CAL_FILE.is_file():
        raise FileNotFoundError(f"SUNA CAL file not found: {CAL_FILE}")

    if MAX_TS_GAP_MINUTES <= 0:
        raise ValueError("MAX_TS_GAP_MINUTES must be greater than zero")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SUNA V2 Temperature / Salinity Batch Correction")
    print("=" * 60)
    print(f"SUNA input:  {SUNA_DIR}")
    print(f"T/S input:   {TS_DIR}")
    print(f"Calibration: {CAL_FILE}")
    print(f"Output:      {OUTPUT_FILE}")
    print()

    print("Loading SUNA calibration...")
    calibration = load_suna_calibration(CAL_FILE)
    print("Calibration loaded.")

    print()
    print("Loading monthly temperature/salinity files...")
    ts_times, ts_temps, ts_sals, ts_files = load_ts_directory(TS_DIR)

    print(
        f"Loaded {len(ts_times):,} valid T/S observations "
        f"from {ts_files} CSV file(s)"
    )
    print(
        "T/S time range: "
        f"{ts_times[0].isoformat()} through {ts_times[-1].isoformat()}"
    )

    max_gap_seconds = MAX_TS_GAP_MINUTES * 60.0

    rows = []
    files_seen = set()
    status_counts: Dict[str, int] = {}

    print()
    print("Processing SUNA files...")

    for path, line_number, line in iter_suna_records(SUNA_DIR):
        files_seen.add(path.name)

        row = process_record(
            path,
            line_number,
            line,
            calibration,
            ts_times,
            ts_temps,
            ts_sals,
            max_gap_seconds,
        )

        rows.append(row)

        status = row["processing_status"] or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1

    if not rows:
        raise RuntimeError(
            f"No SATSLF records were found in {SUNA_DIR}"
        )

    # Sort chronologically. Records whose timestamp could not be parsed
    # are retained and placed at the end.
    rows.sort(
        key=lambda r: r["datetime_utc"] or "9999"
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=OUTPUT_FIELDS
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 60)
    print("Batch processing complete")
    print("=" * 60)
    print(f"SUNA files containing records: {len(files_seen):,}")
    print(f"SUNA records found:            {len(rows):,}")

    for status in sorted(status_counts):
        print(
            f"{status + ':':28s} "
            f"{status_counts[status]:,}"
        )

    print()
    print(f"Output written to:")
    print(OUTPUT_FILE)
    print("=" * 60)

    return 0


if __name__ == "__main__":
    main()

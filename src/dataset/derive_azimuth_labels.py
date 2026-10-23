#!/usr/bin/env python3
"""Add geometrically computed target azimuth/elevation labels to a MeerKAT CSV.

Requires: pandas, numpy, astropy

Assumptions for the supplied ATLAS/MeerKAT example:
- `ra` is decimal hours (not degrees) by default; use --ra-unit degrees if verified otherwise.
- `dec` is degrees.
- `tstart` is the UTC Modified Julian Date (MJD).
- When `tsamp` and `numTimesteps` exist, the default timestamp is the midpoint of
  the observation: tstart + tsamp*numTimesteps/2 seconds.
- The default site coordinates are approximate MeerKAT array-centre coordinates.

This computes the geometric target direction, not a measured antenna encoder position.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit(
        "Missing dependency: astropy. Install with: python -m pip install astropy pandas numpy"
    ) from exc


def find_column(df: pd.DataFrame, wanted: str) -> str | None:
    """Find a column case-insensitively, ignoring surrounding whitespace."""
    wanted = wanted.strip().casefold()
    for name in df.columns:
        if str(name).strip().casefold() == wanted:
            return str(name)
    return None


def add_labels(
    chunk: pd.DataFrame,
    *,
    ra_col: str,
    dec_col: str,
    tstart_col: str,
    tsamp_col: str | None,
    nt_col: str | None,
    ra_unit: str,
    time_point: str,
    location: EarthLocation,
) -> pd.DataFrame:
    ra = pd.to_numeric(chunk[ra_col], errors="coerce").to_numpy(dtype=np.float64)
    dec = pd.to_numeric(chunk[dec_col], errors="coerce").to_numpy(dtype=np.float64)
    mjd = pd.to_numeric(chunk[tstart_col], errors="coerce").to_numpy(dtype=np.float64)

    if time_point == "midpoint" and tsamp_col and nt_col:
        tsamp = pd.to_numeric(chunk[tsamp_col], errors="coerce").to_numpy(dtype=np.float64)
        nt = pd.to_numeric(chunk[nt_col], errors="coerce").to_numpy(dtype=np.float64)
        valid_duration = np.isfinite(tsamp) & np.isfinite(nt) & (tsamp >= 0) & (nt >= 0)
        seconds = np.zeros(len(chunk), dtype=np.float64)
        seconds[valid_duration] = tsamp[valid_duration] * nt[valid_duration] / 2.0
        # If duration metadata is missing, tstart is used for those rows.
        mjd = mjd + seconds / 86400.0

    valid = (
        np.isfinite(ra)
        & np.isfinite(dec)
        & np.isfinite(mjd)
        & (dec >= -90.0)
        & (dec <= 90.0)
    )

    az = np.full(len(chunk), np.nan, dtype=np.float64)
    el = np.full(len(chunk), np.nan, dtype=np.float64)

    if np.any(valid):
        ra_deg = ra[valid] * (15.0 if ra_unit == "hours" else 1.0)
        # RA expressed in hours must be in [0, 24); degree-valued RA in [0, 360).
        upper = 24.0 if ra_unit == "hours" else 360.0
        valid_indices = np.flatnonzero(valid)
        ra_ok = (ra[valid] >= 0.0) & (ra[valid] < upper)
        if not np.all(ra_ok):
            valid[valid_indices[~ra_ok]] = False
            ra_deg = ra_deg[ra_ok]
            valid_indices = valid_indices[ra_ok]

        if len(valid_indices):
            coords = SkyCoord(
                ra=ra_deg * u.deg,
                dec=dec[valid_indices] * u.deg,
                frame="icrs",
            )
            obstime = Time(mjd[valid_indices], format="mjd", scale="utc")
            horizontal = coords.transform_to(
                AltAz(obstime=obstime, location=location, pressure=0 * u.hPa)
            )
            az[valid_indices] = horizontal.az.to_value(u.deg) % 360.0
            el[valid_indices] = horizontal.alt.to_value(u.deg)

    chunk["target_azimuth_deg"] = az
    chunk["target_elevation_deg"] = el
    chunk["target_position_method"] = "astropy_altaz_geometric"
    chunk["target_position_time"] = (
        "observation_midpoint" if time_point == "midpoint" and tsamp_col and nt_col
        else "tstart_utc_mjd"
    )
    return chunk


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Input observations CSV")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output CSV (default: <input>_with_azimuth.csv)")
    parser.add_argument("--chunksize", type=int, default=50000,
                        help="Rows to process at once (default: 50000)")
    parser.add_argument("--ra-unit", choices=("hours", "degrees"), default="hours",
                        help="Unit of the ra column; supplied example appears to use decimal hours")
    parser.add_argument("--time-point", choices=("start", "midpoint"), default="midpoint",
                        help="Use observation start or midpoint when duration columns exist")
    parser.add_argument("--site-lat", type=float, default=-30.713,
                        help="MeerKAT array-centre latitude in degrees (default: -30.713)")
    parser.add_argument("--site-lon", type=float, default=21.443,
                        help="MeerKAT array-centre longitude in degrees east (default: 21.443)")
    parser.add_argument("--site-height", type=float, default=1080.0,
                        help="Site height in metres (default: 1080)")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    if args.chunksize < 1:
        parser.error("--chunksize must be a positive integer")

    out_path = args.output or args.input.with_name(f"{args.input.stem}_with_azimuth.csv")
    if out_path.resolve() == args.input.resolve():
        parser.error("Output must differ from input; original CSV will not be overwritten")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    location = EarthLocation.from_geodetic(
        lon=args.site_lon * u.deg,
        lat=args.site_lat * u.deg,
        height=args.site_height * u.m,
    )

    try:
        reader = pd.read_csv(args.input, chunksize=args.chunksize, low_memory=False,
                             encoding="utf-8-sig")
        first_chunk = True
        total_rows = 0
        valid_labels = 0
        with out_path.open("w", encoding="utf-8-sig", newline="") as output_file:
            for chunk in reader:
                ra_col = find_column(chunk, "ra")
                dec_col = find_column(chunk, "dec")
                tstart_col = find_column(chunk, "tstart")
                missing = [label for label, col in (("ra", ra_col), ("dec", dec_col),
                                                    ("tstart", tstart_col)) if col is None]
                if missing:
                    raise ValueError(
                        "Required input column(s) not found: " + ", ".join(missing)
                        + f". Found columns: {list(chunk.columns)}"
                    )

                tsamp_col = find_column(chunk, "tsamp")
                nt_col = find_column(chunk, "numTimesteps")
                if args.time_point == "midpoint" and not (tsamp_col and nt_col):
                    if first_chunk:
                        print(
                            "Warning: tsamp and/or numTimesteps not found; using tstart for timing.",
                            file=sys.stderr,
                        )

                chunk = add_labels(
                    chunk, ra_col=ra_col, dec_col=dec_col, tstart_col=tstart_col,
                    tsamp_col=tsamp_col, nt_col=nt_col, ra_unit=args.ra_unit,
                    time_point=args.time_point, location=location,
                )
                total_rows += len(chunk)
                valid_labels += int(chunk["target_azimuth_deg"].notna().sum())
                chunk.to_csv(output_file, index=False, header=first_chunk)
                first_chunk = False

        print(f"Rows processed: {total_rows:,}")
        print(f"Rows with calculated azimuth/elevation: {valid_labels:,}")
        print(f"Output: {out_path}")
        print("Note: labels are computed target directions, not antenna encoder telemetry.")
        return 0

    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"Failed to calculate target coordinates: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

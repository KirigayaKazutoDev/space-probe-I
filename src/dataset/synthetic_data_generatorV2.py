#!/usr/bin/env python3
"""Build Space Probe I feature tables from a real-world CSV plus documented synthetic fields.

This is a FEATURE GENERATOR, not a strict CSV reader: it recognizes common radio-astronomy
column names, maps what exists, and simulates absent fields under explicit assumptions.
It does not turn missing fields into real measurements. Provenance is recorded in
 dataset_manifest.json and in *_feature_origins.csv files.

Recommended input for Breakthrough Listen 2019 event tables includes columns such as
Source, DriftRateMax, Nevent, FreqMid, DriftBW, DriftRates, Freqs, FileID, SNR.

Important:
- target_azimuth_deg is a supervised-learning LABEL, not one of the 17 input features.
  If it is absent, the script writes feature-only datasets without y labels. Use
  --synthetic-target-for-demo only to test software plumbing, never to claim real-world
  azimuth prediction performance.
- Frequency/bandwidth/drift units remain source units in the provenance/raw output.
  Model inputs X are normalized using training-split statistics and the feature order
  used by train7.py. To train on these files, train7.py must load X/y from the NPZ files
  instead of calling its old internal random generate_data() routine.
- Synthetic time/planetary angles are approximate scenario variables, not measured
  ephemerides. Exact values require a timestamp, source coordinates, and observer site.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

NUM_POSITIONS = 11520
FEATURE_COLUMNS = [
    "azimuth_deg", "elevation_deg", "frequency", "bandwidth", "snr", "doppler",
    "polarization", "pulse_period", "signal_type", "noise_level",
    "day_of_year", "hour_of_day", "local_hour_angle", "mars_angle",
    "sun_earth_angle", "sun_mars_angle", "visibility",
]
CONTINUOUS_COLUMNS = [
    "azimuth_deg", "elevation_deg", "frequency", "bandwidth", "snr", "doppler",
    "polarization", "pulse_period", "noise_level",
]

# Keys are normalized by stripping punctuation and lowercasing. First matching alias wins.
ALIASES: dict[str, list[str]] = {
    "azimuth_deg": ["azimuth_deg", "azimuth", "az_deg", "antenna_azimuth", "azimuthangle"],
    "elevation_deg": ["elevation_deg", "elevation", "el_deg", "altitude_angle", "elevationangle"],
    "frequency": ["frequency", "freq", "freqmid", "center_frequency", "centerfreq", "frequency_mhz", "freq_mhz", "freqs"],
    "bandwidth": ["bandwidth", "driftbw", "signal_bandwidth", "bandwidth_hz", "bw"],
    "snr": ["snr", "signal_to_noise", "signaltonoiseratio", "snr_db"],
    # DriftRates is preferred because it can carry signs; DriftRateMax is an absolute maximum.
    "doppler": ["doppler", "driftrates", "driftrate", "driftrate_hz_s", "driftratemax", "drift_rate"],
    "polarization": ["polarization", "pol", "polarisation"],
    "pulse_period": ["pulse_period", "pulseperiod", "period", "period_s", "pulsar_period"],
    "signal_type": ["signal_type", "signaltype", "class_id", "signal_class", "label_type"],
    "noise_level": ["noise_level", "noise", "noise_power", "system_noise"],
    "day_of_year": ["day_of_year", "doy", "dayofyear"],
    "hour_of_day": ["hour_of_day", "hour", "utc_hour", "hourofday"],
    "local_hour_angle": ["local_hour_angle", "lha", "hour_angle"],
    "mars_angle": ["mars_angle", "mars_orbit_angle", "mars_phase"],
    "sun_earth_angle": ["sun_earth_angle", "earth_orbit_angle", "sunearthangle"],
    "sun_mars_angle": ["sun_mars_angle", "sunmarsangle"],
    "visibility": ["visibility", "visible", "is_visible"],
    "target_azimuth_deg": ["target_azimuth_deg", "target_azimuth", "azimuth_target", "label_azimuth_deg", "true_azimuth_deg"],
}


def norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    by_norm = {norm_name(c): c for c in df.columns}
    found: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            key = norm_name(alias)
            if key in by_norm:
                found[canonical] = by_norm[key]
                break
    return found


def parse_numeric_cell(value: Any) -> float:
    """Convert scalar or a list-like cell to a useful numeric summary."""
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip()
    if not text:
        return np.nan
    # Array-like CSV fields such as "[0.1, -0.2]" or "0.1; -0.2".
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, np.ndarray)):
            vals = pd.to_numeric(pd.Series(parsed), errors="coerce").to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if not len(vals):
                return np.nan
            # Preserve signed drift where available; for frequency lists use median below.
            return float(np.median(vals))
        if isinstance(parsed, (int, float)):
            return float(parsed)
    except (ValueError, SyntaxError, TypeError):
        pass
    # Fallback for unbracketed lists.
    if ";" in text or "," in text:
        parts = re.split(r"[;,]", text.strip(" []()"))
        vals = pd.to_numeric(pd.Series(parts), errors="coerce").to_numpy(dtype=float)
        vals = vals[np.isfinite(vals)]
        if len(vals):
            return float(np.median(vals))
    try:
        return float(text)
    except ValueError:
        return np.nan


def parse_drift_cell(value: Any) -> float:
    """Median signed drift from a list, otherwise scalar value. Never invent sign."""
    return parse_numeric_cell(value)


def group_split(groups: pd.Series, test_fraction: float, val_fraction: float,
                rng: np.random.Generator) -> dict[str, np.ndarray]:
    if test_fraction <= 0 or val_fraction < 0 or test_fraction + val_fraction >= 1:
        raise ValueError("Use test_fraction > 0, validation_fraction >= 0 and their sum < 1.")
    # Convert pandas/Arrow string extension arrays to a mutable NumPy array before shuffling.
    # This avoids pandas ArrowStringArray shuffle warnings and guarantees predictable behavior.
    unique = np.asarray(pd.unique(groups.astype(str)), dtype=object)
    if len(unique) < (3 if val_fraction > 0 else 2):
        raise ValueError(
            f"Need at least {3 if val_fraction > 0 else 2} distinct groups for the requested split; "
            f"found {len(unique)}. Choose a dataset with more groups or reduce validation_fraction."
        )
    unique = unique.copy()
    rng.shuffle(unique)
    n_test = max(1, int(round(len(unique) * test_fraction)))
    n_val = max(1, int(round(len(unique) * val_fraction))) if val_fraction > 0 else 0
    while n_test + n_val >= len(unique):
        if n_val > 0 and n_val >= n_test:
            n_val -= 1
        else:
            n_test -= 1
    test_g = set(unique[:n_test])
    val_g = set(unique[n_test:n_test+n_val])
    train_g = set(unique[n_test+n_val:])
    s = groups.astype(str)
    return {
        "train": np.flatnonzero(s.isin(train_g).to_numpy()),
        "validation": np.flatnonzero(s.isin(val_g).to_numpy()),
        "test": np.flatnonzero(s.isin(test_g).to_numpy()),
    }


def robust_sample(reference: np.ndarray, n: int, rng: np.random.Generator,
                  default: float = 0.0, noise_fraction: float = 0.02) -> np.ndarray:
    vals = np.asarray(reference, dtype=float)
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return np.full(n, default, dtype=float)
    # Bootstrap the empirical distribution first. A small perturbation prevents exact copies.
    out = rng.choice(vals, size=n, replace=True).astype(float)
    q25, q75 = np.quantile(vals, [0.25, 0.75])
    iqr = float(q75 - q25)
    if iqr > 0 and noise_fraction > 0:
        out += rng.normal(0.0, noise_fraction * iqr, size=n)
    return out


def make_canonical_table(raw: pd.DataFrame, found: dict[str, str],
                         source_id_col: str | None, rng: np.random.Generator,
                         allow_synthetic_demo_target: bool,
                         reference_features: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    """Map real columns and fill unavailable features with traceable synthetic proxies."""
    n = len(raw)
    frame = pd.DataFrame(index=raw.index)
    origins: dict[str, str] = {}
    notes: dict[str, str] = {}

    # Direct columns and known aliases.
    for canonical in FEATURE_COLUMNS + ["target_azimuth_deg"]:
        if canonical not in found:
            continue
        src = found[canonical]
        if canonical == "signal_type" and raw[src].dtype == object:
            # Stable category encoding for strings; this is an encoding, not a semantic classifier.
            cats = sorted(raw[src].dropna().astype(str).unique())
            mapping = {c: i for i, c in enumerate(cats)}
            vals = raw[src].astype(str).map(mapping).astype(float)
            frame[canonical] = vals.where(raw[src].notna(), np.nan)
            notes[canonical] = f"Categorical encoding of source column {src}; mapping={mapping}"
        else:
            if canonical == "doppler" and norm_name(src) == norm_name("DriftRateMax"):
                vals = pd.to_numeric(raw[src], errors="coerce").to_numpy(dtype=float)
                # DriftRateMax is explicitly a maximum absolute drift, not signed drift.
                frame[canonical] = vals
                notes[canonical] = f"Mapped from {src}; absolute magnitude only (sign unavailable)"
            else:
                frame[canonical] = raw[src].map(parse_drift_cell if canonical == "doppler" else parse_numeric_cell)
                notes[canonical] = f"Mapped/parsed from source column {src}"
            origins[canonical] = "observed_or_source_derived"

    # Frequency: if only a list column Freqs exists, use its median. The alias parser handles lists.
    # Bandwidth: for the BL event table, DriftBW is the source-provided band covered by the group.
    # Fill partially missing direct fields from the training-derived empirical distribution later.

    # Random synthetic geometry prior (only used where the CSV has no relevant columns).
    if "azimuth_deg" not in frame:
        frame["azimuth_deg"] = rng.uniform(0.0, 360.0, n)
        origins["azimuth_deg"] = "synthetic_prior"
        notes["azimuth_deg"] = "Uniform 0..360 degree azimuth prior; not the real telescope pointing"
    if "elevation_deg" not in frame:
        # For an idealized isotropic sky above the horizon, sin(elevation) is uniform.
        u = rng.uniform(0.0, 1.0, n)
        frame["elevation_deg"] = np.degrees(np.arcsin(u))
        origins["elevation_deg"] = "synthetic_prior"
        notes["elevation_deg"] = "Isotropic-above-horizon prior; not observed elevation or telescope schedule"

    # Missing target label is left missing unless explicitly making a demo-only synthetic task.
    if "target_azimuth_deg" not in frame:
        if allow_synthetic_demo_target:
            # Demo-only surrogate: create a nearby synthetic target around the current input pointing.
            # If pointing is itself synthetic, it is just a simulated scenario, not a real label.
            err = rng.normal(0.0, 0.25, n)
            target = np.mod(pd.to_numeric(frame["azimuth_deg"], errors="coerce").to_numpy(dtype=float) - err, 360.0)
            frame["target_azimuth_deg"] = target
            origins["target_azimuth_deg"] = "synthetic_demo_label"
            notes["target_azimuth_deg"] = "Synthetic target = input azimuth - N(0, 0.25 deg) error; software demo only, not observed truth"
            if origins.get("azimuth_deg") == "synthetic_prior":
                origins["azimuth_deg"] = "synthetic_measurement_simulation"
                notes["azimuth_deg"] = "Synthetic simulated antenna input pointing; not real telescope pointing"
        else:
            frame["target_azimuth_deg"] = np.nan
            notes["target_azimuth_deg"] = "Unavailable: input CSV has no target-azimuth label"

    # Frequency is foundational and should not be made up silently. BL tables have FreqMid/Freqs.
    if "frequency" not in frame:
        raise ValueError(
            "No frequency column was recognized. Expected a field such as FreqMid, Freqs, "
            "frequency, or freq_mhz. Frequency cannot be inferred responsibly from SNR alone."
        )

    # Known/simple derivation: if Doppler absent but DriftRateMax exists, the alias resolver should map it.
    if "bandwidth" not in frame and "frequency" in frame:
        # A bandwidth is not derivable from a center frequency. Use an explicit zero-as-unknown code,
        # and record that it is a placeholder, rather than pretending it is measured bandwidth.
        frame["bandwidth"] = 0.0
        origins["bandwidth"] = "unknown_placeholder"
        notes["bandwidth"] = "No bandwidth field; 0 is an unknown placeholder, not a measured zero bandwidth"

    # Source row with detected events: signal_type=1 is only a coarse 'candidate present' indicator.
    if "signal_type" not in frame:
        frame["signal_type"] = 1.0
        origins["signal_type"] = "heuristic_from_event_table"
        notes["signal_type"] = "Set to 1 for rows listed as detected event groups; not a confirmed technosignature label"

    # Use existing SNR to construct a relative noise proxy only if actual noise is missing.
    if "noise_level" not in frame:
        snr = pd.to_numeric(frame.get("snr", pd.Series(np.nan, index=frame.index)), errors="coerce").to_numpy(dtype=float)
        if np.isfinite(snr).any():
            # Unitless inverse-SNR proxy: signal amplitude is unknown, so this is not physical noise power.
            floor = max(float(np.nanpercentile(np.abs(snr[np.isfinite(snr)]), 5)), 1e-6)
            proxy = 1.0 / np.maximum(np.abs(snr), floor)
            proxy[~np.isfinite(proxy)] = np.nan
            frame["noise_level"] = proxy
            origins["noise_level"] = "derived_proxy"
            notes["noise_level"] = "Inverse-|SNR| relative proxy; not calibrated receiver/system noise"
        else:
            frame["noise_level"] = np.nan

    # Polarization and pulse period are not implied by the listed BL event CSV columns.
    if "polarization" not in frame:
        frame["polarization"] = 0.0  # 0 means unknown in this generator's encoding.
        origins["polarization"] = "unknown_placeholder"
        notes["polarization"] = "0 means unknown/unavailable; not a polarization measurement"
    if "pulse_period" not in frame:
        frame["pulse_period"] = 0.0
        origins["pulse_period"] = "unknown_placeholder"
        notes["pulse_period"] = "0 means unavailable; do not interpret as a measured zero period"

    # Deterministic-ish synthetic date and simplified orbital phases. These are not Horizons ephemerides.
    if "day_of_year" not in frame:
        frame["day_of_year"] = rng.integers(1, 367, n).astype(float)
        origins["day_of_year"] = "synthetic_scenario"
        notes["day_of_year"] = "Random day of year; no observation timestamp was present"
    if "hour_of_day" not in frame:
        frame["hour_of_day"] = rng.uniform(0.0, 24.0, n)
        origins["hour_of_day"] = "synthetic_scenario"
        notes["hour_of_day"] = "Random UTC hour; no observation timestamp was present"
    day = pd.to_numeric(frame["day_of_year"], errors="coerce").fillna(183).to_numpy(dtype=float)
    hour = pd.to_numeric(frame["hour_of_day"], errors="coerce").fillna(12).to_numpy(dtype=float)
    if "local_hour_angle" not in frame:
        # Without RA + longitude + timestamp this cannot be calculated as a true local hour angle.
        frame["local_hour_angle"] = rng.uniform(-180.0, 180.0, n)
        origins["local_hour_angle"] = "synthetic_scenario"
        notes["local_hour_angle"] = "Uniform -180..180 deg; true LHA requires target RA, longitude and timestamp"
    if "sun_earth_angle" not in frame:
        frame["sun_earth_angle"] = np.mod(360.0 * ((day - 1.0) + hour / 24.0) / 365.256, 360.0)
        origins["sun_earth_angle"] = "approximate_orbital_phase"
        notes["sun_earth_angle"] = "Circular-orbit phase approximation from synthetic/available day and hour"
    if "mars_angle" not in frame:
        frame["mars_angle"] = np.mod(360.0 * ((day - 1.0) + hour / 24.0) / 686.98, 360.0)
        origins["mars_angle"] = "approximate_orbital_phase"
        notes["mars_angle"] = "Mars orbital phase approximation; not an ephemeris"
    if "sun_mars_angle" not in frame:
        frame["sun_mars_angle"] = frame["mars_angle"].to_numpy(dtype=float).copy()
        origins["sun_mars_angle"] = "approximate_orbital_phase"
        notes["sun_mars_angle"] = "Copied simplified Mars orbital phase; not a sky-projected Sun-Mars angle"
    if "visibility" not in frame:
        frame["visibility"] = (pd.to_numeric(frame["elevation_deg"], errors="coerce").to_numpy(dtype=float) > 0).astype(float)
        origins["visibility"] = "derived_from_synthetic_or_observed_elevation"
        notes["visibility"] = "1 if elevation > 0 deg; ignores terrain, Sun avoidance, weather and instrument limits"

    # Fill missing cells in partially observed columns, and generate absent SNR/Doppler empirically where possible.
    # References here are from the available rows; the main() function separates groups before calling us,
    # but direct observed values are preserved. Fully absent critical values use cautious defaults only.
    for col in FEATURE_COLUMNS:
        if col not in frame:
            frame[col] = np.nan
        vals = pd.to_numeric(frame[col], errors="coerce")
        if vals.isna().any():
            # For features with any real/source data, bootstrap from their non-missing empirical distribution.
            present = vals.dropna().to_numpy(dtype=float)
            missing_idx = vals.isna().to_numpy()
            reference = np.array([], dtype=float)
            if reference_features is not None and col in reference_features:
                reference = pd.to_numeric(reference_features[col], errors="coerce").to_numpy(dtype=float)
                reference = reference[np.isfinite(reference)]
            if len(missing_idx) and missing_idx.any() and len(reference):
                # Imputation distribution comes from TRAIN only; do not fit to validation/test.
                vals.loc[missing_idx] = robust_sample(reference, int(missing_idx.sum()), rng, default=0.0)
                frame[col] = vals
                origins.setdefault(col, "mixed_observed_and_train_empirical_fill")
                notes.setdefault(col, "Missing cells filled by bootstrap from training-partition values")
            elif len(present):
                # Training rows may fill their own missing cells from other training rows.
                vals.loc[missing_idx] = robust_sample(present, int(missing_idx.sum()), rng, default=0.0)
                frame[col] = vals
                origins.setdefault(col, "mixed_observed_and_empirical_fill")
                notes.setdefault(col, "Missing cells filled by bootstrap from non-missing rows in this partition")
            else:
                # Explicit conservative fallbacks for features absent from the entire source file.
                defaults = {"snr": 1.0, "doppler": 0.0, "bandwidth": 0.0,
                            "frequency": np.nan, "noise_level": 1.0}
                if col == "frequency":
                    raise ValueError("Frequency has no usable values after parsing the CSV.")
                vals[:] = defaults.get(col, 0.0)
                frame[col] = vals
                origins.setdefault(col, "unknown_placeholder")
                notes.setdefault(col, f"No source values available; placeholder={defaults.get(col, 0.0)!r}")

    # Physical-ish bounds/encodings. Frequency/bandwidth/doppler units are intentionally not converted here.
    frame["azimuth_deg"] = np.mod(pd.to_numeric(frame["azimuth_deg"], errors="coerce"), 360.0)
    frame["elevation_deg"] = pd.to_numeric(frame["elevation_deg"], errors="coerce").clip(0.0, 90.0)
    frame["day_of_year"] = pd.to_numeric(frame["day_of_year"], errors="coerce").clip(1.0, 366.0)
    frame["hour_of_day"] = pd.to_numeric(frame["hour_of_day"], errors="coerce").clip(0.0, 24.0)
    for col in ("local_hour_angle", "mars_angle", "sun_earth_angle", "sun_mars_angle"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["local_hour_angle"] = ((frame["local_hour_angle"] + 180.0) % 360.0) - 180.0
    for col in ("mars_angle", "sun_earth_angle", "sun_mars_angle"):
        frame[col] = frame[col] % 360.0
    frame["visibility"] = (pd.to_numeric(frame["visibility"], errors="coerce") >= 0.5).astype(float)

    # Keep canonical tables compact; float32 is sufficient for these normalized/scientific features.
    canonical = frame[FEATURE_COLUMNS + ["target_azimuth_deg"]].astype(np.float32, copy=False)
    return canonical, origins, notes


def fit_normalizer(train: pd.DataFrame) -> dict[str, list[float]]:
    """Fit robust min/max scaling on train only; each feature maps approximately to [0,1]."""
    params: dict[str, list[float]] = {}
    for col in FEATURE_COLUMNS:
        vals = pd.to_numeric(train[col], errors="coerce").to_numpy(dtype=float)
        vals = vals[np.isfinite(vals)]
        if not len(vals):
            lo, hi = 0.0, 1.0
        elif col in ("azimuth_deg", "elevation_deg", "day_of_year", "hour_of_day", "mars_angle", "sun_earth_angle", "sun_mars_angle", "visibility"):
            fixed = {
                "azimuth_deg": (0.0, 360.0), "elevation_deg": (0.0, 90.0),
                "day_of_year": (1.0, 366.0), "hour_of_day": (0.0, 24.0),
                "mars_angle": (0.0, 360.0), "sun_earth_angle": (0.0, 360.0),
                "sun_mars_angle": (0.0, 360.0), "visibility": (0.0, 1.0),
            }
            lo, hi = fixed[col]
        elif col == "local_hour_angle":
            lo, hi = -180.0, 180.0
        elif col == "polarization":
            lo, hi = -1.0, 1.0
        elif col == "signal_type":
            lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
            if hi <= lo: hi = lo + 1.0
        else:
            lo, hi = (float(x) for x in np.quantile(vals, [0.01, 0.99]))
            if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
                lo, hi = float(np.min(vals)), float(np.max(vals))
            if hi <= lo:
                hi = lo + 1.0
        params[col] = [float(lo), float(hi)]
    return params


def normalize(df: pd.DataFrame, params: dict[str, list[float]]) -> np.ndarray:
    out = np.empty((len(df), len(FEATURE_COLUMNS)), dtype=np.float32)
    for j, col in enumerate(FEATURE_COLUMNS):
        lo, hi = params[col]
        vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
        # Cyclic azimuth/angles already have defined physical range. Others are clipped to train range.
        vals = np.clip(vals, lo, hi)
        scaled = (vals - lo) / (hi - lo)
        out[:, j] = np.clip(scaled, 0.0, 1.0).astype(np.float32)
    return out


def augment_train(raw_features: pd.DataFrame, factor: int, jitter_fraction: float,
                  rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    """Augment only training rows. Returns expanded data and augmentation labels."""
    if factor < 0 or jitter_fraction < 0 or jitter_fraction > 0.25:
        raise ValueError("augment_factor must be >=0 and jitter_fraction must be in [0, 0.25].")
    frames = [raw_features.copy()]
    aug_ids = [np.full(len(raw_features), "original", dtype=object)]
    if factor == 0:
        return frames[0], aug_ids[0]
    for k in range(factor):
        aug = raw_features.copy(deep=True)
        # Do not jitter simulated calendar/orbit metadata independently.
        for col in ("frequency", "bandwidth", "snr", "doppler", "noise_level", "pulse_period"):
            vals = pd.to_numeric(raw_features[col], errors="coerce").to_numpy(dtype=float)
            finite = vals[np.isfinite(vals)]
            if len(finite) < 2:
                continue
            q25, q75 = np.quantile(finite, [0.25, 0.75])
            sigma = float(q75 - q25) * jitter_fraction
            if sigma > 0:
                aug[col] = vals + rng.normal(0.0, sigma, len(vals))
        aug["azimuth_deg"] = np.mod(
            pd.to_numeric(raw_features["azimuth_deg"], errors="coerce").to_numpy(dtype=float)
            + rng.normal(0.0, 0.25 * jitter_fraction / 0.02 if jitter_fraction else 0.0, len(aug)), 360.0)
        aug["elevation_deg"] = np.clip(pd.to_numeric(aug["elevation_deg"], errors="coerce"), 0.0, 90.0)
        frames.append(aug)
        aug_ids.append(np.full(len(aug), f"aug_{k+1}", dtype=object))
    return pd.concat(frames, ignore_index=True), np.concatenate(aug_ids)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_csv", type=Path, help="Existing CSV of observations/events (arbitrary source column names)")
    p.add_argument("--output-dir", type=Path, default=Path("dataset_out"))
    p.add_argument("--test-fraction", type=float, default=0.15)
    p.add_argument("--validation-fraction", type=float, default=0.15)
    p.add_argument("--augment-factor", type=int, default=2, help="Additional variants per training row; 0 disables")
    p.add_argument("--jitter-fraction", type=float, default=0.02, help="Jitter sigma as fraction of feature IQR")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--group-column", type=str, default=None, help="Column to keep together across splits; defaults to filename, FileID, observation ID, or Source")
    p.add_argument("--synthetic-target-for-demo", action="store_true", help="Create random azimuth labels for software tests only; never use for real evaluation")
    args = p.parse_args()

    if not args.input_csv.is_file():
        raise FileNotFoundError(f"Input CSV not found or not a file: {args.input_csv}")

    # Read only the header first. The ATLAS CSV can contain millions of rows and many
    # provenance columns that the feature generator never needs in memory.
    header = pd.read_csv(args.input_csv, nrows=0, encoding="utf-8-sig")
    found = resolve_columns(header)
    col_lookup = {norm_name(c): c for c in header.columns}

    preferred_group_cols = [args.group_column] if args.group_column else [
        "filename", "file_name", "FileID", "fileid", "observation_id",
        "scan_id", "fileindex", "Source", "sourceName",
    ]
    group_col = None
    for candidate in preferred_group_cols:
        if candidate is None:
            continue
        if candidate in header.columns:
            group_col = candidate
            break
        if norm_name(candidate) in col_lookup:
            group_col = col_lookup[norm_name(candidate)]
            break
    if args.group_column and group_col is None:
        raise ValueError(
            f"Requested --group-column '{args.group_column}' was not found. "
            f"Available columns include: {list(header.columns[:30])}"
        )

    # The full raw CSV contains numerous fields (hostnames, paths, channel metadata, etc.)
    # that are not consumed by this generator. Read only recognized feature columns + group key.
    columns_to_read = list(dict.fromkeys(list(found.values()) + ([group_col] if group_col else [])))
    if not columns_to_read:
        raise ValueError("No recognized model feature columns were found in the input CSV.")
    raw = pd.read_csv(
        args.input_csv,
        usecols=columns_to_read,
        low_memory=False,
        encoding="utf-8-sig",
    )
    if raw.empty:
        raise ValueError("Input CSV contains no rows.")

    rng = np.random.default_rng(args.seed)

    if group_col:
        # Factorize potentially very long filenames to compact int IDs. Keep the mapping
        # separately so provenance is retained without repeating the full path millions of times.
        raw_group_values = raw[group_col].fillna("__missing_group__").astype(str)
        group_codes, group_labels = pd.factorize(raw_group_values, sort=False)
        groups = pd.Series(group_codes.astype(np.int32), index=raw.index, name="group_code")
        source_ids = group_codes.astype(np.int32, copy=False)
        source_group_map = pd.DataFrame({
            "source_id": np.arange(len(group_labels), dtype=np.int32),
            "source_group_column": group_col,
            "source_group_value": pd.Series(group_labels, dtype=str),
        })
        del raw_group_values
        # Drop the repeated group-value string column from the large raw table when it is
        # not also a genuine model feature.
        if group_col not in found.values():
            raw.drop(columns=[group_col], inplace=True)
    else:
        warnings.warn(
            "No observation/source grouping column found; splitting individual rows can leak correlated observations.",
            RuntimeWarning,
        )
        groups = pd.Series(np.arange(len(raw), dtype=np.int32), index=raw.index, name="row_group")
        source_ids = groups.to_numpy(dtype=np.int32, copy=True)
        source_group_map = None

    split_indices = group_split(groups, args.test_fraction, args.validation_fraction, rng)
    split_groups = {name: set(groups.iloc[idx].astype(str)) for name, idx in split_indices.items()}
    if (split_groups["train"] & split_groups["validation"] or
        split_groups["train"] & split_groups["test"] or
        split_groups["validation"] & split_groups["test"]):
        raise RuntimeError("Internal error: source groups overlap across splits")

    canonical_by_split: dict[str, pd.DataFrame] = {}
    origins_by_split: dict[str, dict[str, str]] = {}
    notes_by_split: dict[str, dict[str, str]] = {}
    # Fit missing-field empirical distributions only to the training partition. To keep this compact,
    # make_canonical_table uses within-partition empirical bootstrap for partially missing values;
    # fully absent fields use explicit documented priors/placeholders.
    # Process train first so all empirical imputations for validation/test can reference train only.
    for split_name in ("train", "validation", "test"):
        frame_raw = raw.iloc[split_indices[split_name]]
        ref_features = canonical_by_split["train"][FEATURE_COLUMNS] if split_name != "train" else None
        canon, origins, notes = make_canonical_table(
            frame_raw, found, group_col, rng, args.synthetic_target_for_demo,
            reference_features=ref_features
        )
        canon.insert(0, "source_id", source_ids[split_indices[split_name]])
        canon["_row_index"] = frame_raw.index.to_numpy()
        canonical_by_split[split_name] = canon
        origins_by_split[split_name] = origins
        notes_by_split[split_name] = notes
        del frame_raw

    # Release raw input columns before expanding the training table.
    del raw, groups, source_ids

    # Correct leakage guard: target cannot be essentially copied from input azimuth.
    for split_name, canon in canonical_by_split.items():
        if canon["target_azimuth_deg"].notna().any():
            both = canon["target_azimuth_deg"].notna() & canon["azimuth_deg"].notna()
            if both.any() and ((canon.loc[both, "azimuth_deg"] - canon.loc[both, "target_azimuth_deg"]).abs() < 1e-9).mean() > 0.95:
                raise ValueError("Target leakage: azimuth_deg input equals target_azimuth_deg on >95% of rows. Fix the feature/label definition.")

    # Fit model-input scaling from training rows only.
    norm_params = fit_normalizer(canonical_by_split["train"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if source_group_map is not None:
        source_group_map.to_csv(args.output_dir / "source_groups.csv", index=False)
    manifest: dict[str, Any] = {
        "input_csv": str(args.input_csv),
        "seed": args.seed,
        "source_group_column": group_col,
        "source_group_map_file": "source_groups.csv" if group_col else None,
        "source_id_encoding": "compact integer id mapped to original group value in source_groups.csv" if group_col else "row index id; no group column found",
        "split_group_counts": {k: len(v) for k, v in split_groups.items()},
        "split_original_rows": {k: len(v) for k, v in canonical_by_split.items()},
        "feature_order": FEATURE_COLUMNS,
        "normalization_fit_on_train_only": True,
        "normalization_parameters_min_max": norm_params,
        "column_mapping": {k: v for k, v in found.items()},
        "feature_origins": origins_by_split["train"],
        "feature_generation_notes": notes_by_split["train"],
        "label_available_in_source": "target_azimuth_deg" in found,
        "synthetic_demo_target_enabled": bool(args.synthetic_target_for_demo),
        "warning": (
            "Synthetic fields are not real observations. Synthetic planet phases use a simplified circular-orbit approximation. "
            "This dataset is not scientifically valid for real azimuth prediction unless real target labels are supplied."
        ),
    }

    for split_name in ("train", "validation", "test"):
        canon = canonical_by_split[split_name].copy()
        aug_ids = np.full(len(canon), "original", dtype=object)
        if split_name == "train" and args.augment_factor > 0:
            # Separate target/source provenance before expansion.
            target_copy = canon["target_azimuth_deg"].to_numpy(dtype=float)
            source_copy = canon["source_id"].to_numpy(dtype=np.int32)
            canonical_features = canon[FEATURE_COLUMNS].copy()
            expanded_features, aug_ids = augment_train(canonical_features, args.augment_factor, args.jitter_fraction, rng)
            repeat_n = args.augment_factor + 1
            canon = expanded_features
            canon["target_azimuth_deg"] = np.tile(target_copy, repeat_n)
            canon["source_id"] = np.tile(source_copy, repeat_n)
            canon["_row_index"] = np.tile(canonical_by_split[split_name]["_row_index"].to_numpy(), repeat_n)
        X = normalize(canon[FEATURE_COLUMNS], norm_params)
        csv_out = pd.DataFrame(X, columns=[f"x{i}" for i in range(17)])
        if canon["target_azimuth_deg"].notna().all():
            targets = canon["target_azimuth_deg"].to_numpy(dtype=float)
            if np.any((targets < 0) | (targets > 360)):
                raise ValueError("target_azimuth_deg must be in [0, 360].")
            csv_out["y_class"] = np.rint(targets * 32.0).astype(np.int64) % NUM_POSITIONS
            csv_out["y_reg"] = targets / 360.0
        csv_out["source_id"] = canon["source_id"].to_numpy(dtype=np.int32)
        csv_out["augmentation_id"] = aug_ids.astype(str)
        csv_out.to_csv(args.output_dir / f"{split_name}.csv", index=False)

        npz_fields: dict[str, Any] = {
            "X": X,
            "source_id": canon["source_id"].to_numpy(dtype=np.int32),
            "augmentation_id": aug_ids.astype(str),
            "feature_names": np.asarray(FEATURE_COLUMNS, dtype=str),
        }
        if canon["target_azimuth_deg"].notna().all():
            npz_fields["y"] = np.rint(canon["target_azimuth_deg"].to_numpy(dtype=float) * 32.0).astype(np.int64) % NUM_POSITIONS
            npz_fields["y_reg"] = canon["target_azimuth_deg"].to_numpy(dtype=np.float32) / 360.0
        np.savez_compressed(args.output_dir / f"{split_name}.npz", **npz_fields)

        # Stream the provenance CSV in chunks. A single copy of 2.5M x 18 float64
        # values would request about 350 MiB at once, on top of all currently live arrays.
        origin_path = args.output_dir / f"{split_name}_feature_origins.csv"
        origin_columns = FEATURE_COLUMNS + ["target_azimuth_deg"]
        chunk_rows = 100_000
        for chunk_start in range(0, len(canon), chunk_rows):
            chunk_stop = min(chunk_start + chunk_rows, len(canon))
            chunk = canon.iloc[chunk_start:chunk_stop]
            raw_export = chunk[origin_columns].copy()
            raw_export.insert(
                0, "source_id",
                chunk["source_id"].to_numpy(dtype=np.int32),
            )
            raw_export["augmentation_id"] = aug_ids[chunk_start:chunk_stop].astype(str)
            raw_export.to_csv(
                origin_path,
                index=False,
                mode="w" if chunk_start == 0 else "a",
                header=(chunk_start == 0),
            )
            del raw_export, chunk
        manifest.setdefault("final_rows", {})[split_name] = len(canon)
        manifest.setdefault("labels_written", {})[split_name] = bool(canon["target_azimuth_deg"].notna().all())

    (args.output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(args.output_dir.resolve()),
        "mapped_columns": found,
        "feature_order": FEATURE_COLUMNS,
        "labels_available": manifest["label_available_in_source"] or args.synthetic_target_for_demo,
        "group_column": group_col,
        "rows": manifest["final_rows"],
        "warning": manifest["warning"],
    }, indent=2))


if __name__ == "__main__":
    main()

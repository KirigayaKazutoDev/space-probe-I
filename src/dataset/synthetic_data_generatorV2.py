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

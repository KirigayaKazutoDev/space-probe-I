# Dataset Synthetic Data Generator

## 1. Data Collection

To generate synthetic data from existing radio astronomy observations, first obtain a real dataset.

The Breakthrough Listen ATLAS / MeerKAT data archive contains the file `atlas_hits_2025_11.json.gz` and other datasets:

https://bldata.berkeley.edu/ATLAS/MeerKAT/

Download `atlas_hits_2025_11.json.gz` and place it in the `src/dataset` directory.

## 2. Data Conversion

Convert the downloaded `.json.gz` file into a CSV file:

```powershell
python json_gz_to_csv.py atlas_hits_2025_11.json.gz -o observations.csv
```

The converter produces:

- `observations.csv` — the converted observation data.
- `observations_schema.json` — a report describing the detected JSON structure, column names, example values and row counts.

The converter changes the file format only. It does not generate missing model features or target labels.

## 3. Calculate Azimuth and Elevation Labels

The original ATLAS CSV contains fields such as `ra`, `dec`, `tstart`, `tsamp` and `numTimesteps`.

These can be used to calculate the astronomical direction in the local horizontal coordinate system, provided that the coordinate units, observation time and telescope location are correct.

Install the required Python packages:

```powershell
python -m pip install astropy pandas numpy
```

Generate a new CSV containing the calculated target azimuth and elevation:

```powershell
python derive_azimuth_labels.py observations.csv -o observations_with_azimuth.csv --ra-unit hours --time-point midpoint
```

The output is `observations_with_azimuth.csv`. The original `observations.csv` remains unchanged.

The generated CSV contains two additional columns:

- `target_azimuth_deg` — calculated target azimuth in degrees.
- `target_elevation_deg` — calculated target elevation in degrees.

Additional metadata columns, such as `target_position_method` and `target_position_time`, document how the labels were calculated.

**Important:** These labels represent calculated astronomical target directions, not measured antenna encoder positions. Actual antenna pointing telemetry would be required to obtain the mechanical antenna position.

The option `--ra-unit hours` assumes that right ascension (`ra`) is stored in decimal hours. This assumption must be verified before the labels are used for scientific evaluation.

## 4. Verify the RA Unit and Observation Time

Use a known row from `observations.csv` to inspect the coordinate interpretation.

For example, the following values occur in the sample observation:

```text
ra    = 13.255836111111112
dec   = -5.825555555555555
tstart = 60984.176537959574
```

Run this command in PowerShell:

```powershell
python -c "from astropy.coordinates import Angle; from astropy import units as u; from astropy.time import Time; ra=Angle(13.255836111111112,unit=u.hourangle); dec=Angle(-5.825555555555555,unit=u.deg); print('RA:',ra.to_string(unit=u.hourangle,sep=':',precision=2)); print('RA in degrees:',ra.deg); print('Dec:',dec.to_string(unit=u.deg,sep=':',alwayssign=True,precision=0)); print('UTC:',Time(60984.176537959574,format='mjd',scale='utc').isot)"
```

If `ra` is in decimal hours, the approximate output should be:

```text
RA: 13:15:21.01
RA in degrees: 198.83754166666668
Dec: -5:49:32
UTC: 2025-11-05T04:14:12.880
```

The value of `ra` is multiplied by 15 to convert hours to degrees. The declination remains in angular degrees.

**This command demonstrates the assumed interpretation; it does not independently prove that the source CSV stores RA in hours.**

To investigate the range of the actual RA values, run:

```powershell
python -c "import pandas as pd; x=pd.read_csv('observations.csv',usecols=['ra'])['ra']; print('RA minimum:',x.min()); print('RA maximum:',x.max()); print('Values greater than 24:',int((x>24).sum()),'of',int(x.notna().sum()))"
```

If any RA values are greater than 24, the column cannot consistently be expressed in hours. If all values are below 24, that alone does not distinguish hours from degrees.

The final confirmation should come from the source data documentation or from a comparison with trusted astronomical coordinates at the same observation time.

## 5. Verify the Calculated Azimuth and Elevation

First, inspect a few rows of the generated CSV:

```powershell
python -c "import pandas as pd; d=pd.read_csv('observations_with_azimuth.csv',usecols=['ra','dec','tstart','target_azimuth_deg','target_elevation_deg']); print(d.head().to_string(index=False))"
```

Next, check for missing values and invalid angular ranges:

```powershell
python -c "import pandas as pd; d=pd.read_csv('observations_with_azimuth.csv',usecols=['target_azimuth_deg','target_elevation_deg']); print('Missing values:',d.isna().sum().to_dict()); print('Azimuth range:',d.target_azimuth_deg.min(),d.target_azimuth_deg.max()); print('Elevation range:',d.target_elevation_deg.min(),d.target_elevation_deg.max()); print('Invalid azimuths:',int(((d.target_azimuth_deg<0)|(d.target_azimuth_deg>=360)).sum())); print('Invalid elevations:',int(((d.target_elevation_deg<-90)|(d.target_elevation_deg>90)).sum()))"
```

Expected ranges are:

- Azimuth: 0° to less than 360°.
- Elevation: −90° to +90°.

These checks detect missing values and impossible numerical ranges. They do not prove that the angles are astronomically correct.

### Independent astronomical validation

For a stronger check, compare a sample row against a trusted ephemeris or pointing reference.

1. Confirm the RA unit, coordinate reference frame, timestamp convention and telescope location.
2. Use the same observation time and observer location in the independent reference.
3. Compare the resulting azimuth and elevation.
4. Account for differences in atmospheric refraction and coordinate conventions when comparing results.

JPL Horizons can provide an independent reference for a known astronomical target:

https://ssd.jpl.nasa.gov/horizons/app.html#/

Only use an object ephemeris if the RA/Dec values refer to that object. If the CSV coordinates describe the telescope pointing centre, use the corresponding observation metadata or pointing reference instead.

## 6. Generate the Synthetic Dataset

After calculating the labels, use `observations_with_azimuth.csv` as the generator input, rather than the original CSV:

```powershell
python synthetic_data_generatorV2.py observations_with_azimuth.csv --output-dir dataset_out --test-fraction 0.15 --validation-fraction 0.15 --augment-factor 3 --jitter-fraction 0.02 --seed 42
```

The intended split proportions are:

- Training: approximately 70%.
- Validation: approximately 15%.
- Test: approximately 15%.

The generator should split independent source groups before augmenting the training data. Where appropriate, `filename` should identify the source observation group so that related detections do not leak into different splits.

The `--augment-factor 3` option generates three additional variants for each eligible training row. Validation and test observations must remain unaugmented.

## 7. Verify the Generated Dataset

Run this command from the `src/dataset/dataset_out` directory:

```powershell
python -c "import csv; f=open('train_feature_origins.csv',encoding='utf-8-sig',newline=''); r=csv.DictReader(f); print('Columns:',r.fieldnames); row=next(r); print('target_azimuth_deg =',repr(row.get('target_azimuth_deg'))); print('augmentation_id =',repr(row.get('augmentation_id')))"
```

If `target_azimuth_deg` prints as `None`, the column may be missing or named differently. If it prints as an empty string, the field exists but its value is missing for that row.

If the target is missing in the original observations, the generator must not invent target labels and treat them as real measurements.

## 8. Important Training Considerations

The 17 input features and the target azimuth must be handled separately.

The target azimuth must not be copied into an input feature that gives the model the answer in advance. The input features must also contain meaningful information related to the target; filling missing features with arbitrary random values does not make them physically realistic.

Calculated target direction and measured antenna pointing are different quantities. The latter requires actual antenna position or encoder telemetry.

Before interpreting model accuracy as real-world performance, verify the coordinate assumptions, remove target leakage, ensure the feature definitions have consistent units, and evaluate the final model on independent, unseen observations.

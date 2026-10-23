# Dataset Synthetic Data Generator

## Data Collecting
to generate the synthetic data out of the existing data, you first have to fill your observations.csv file with data. This could be done by scraping content from existing CSV tables.

This index has the atlas_hits_2025_11.json.gz file and other even bigger files: https://bldata.berkeley.edu/ATLAS/MeerKAT/

## Data Conversion
to convert the downloaded atlas_hits_2025_11.json.gz from json/json.gz to csv, you have to execute this command:
```plain
python json_gz_to_csv.py atlas_hits_2025_11.json.gz -o observations.csv
```

## Generating synthetic data
Then you have to execute either this command (do not forget to fill the observations.csv file!):
```plain
python synthetic_data_generatorV2.py observations.csv \
  --output-dir dataset_out \
  --test-fraction 0.15 \
  --validation-fraction 0.15 \
  --augment-factor 3 \
  --jitter-fraction 0.02 \
  --seed 42
```
or this one as a one-liner-command:
```plain
python synthetic_data_generatorV2.py observations.csv --output-dir dataset_out --test-fraction 0.15 --validation-fraction 0.15 --augment-factor 3 --jitter-fraction 0.02 --seed 42
```

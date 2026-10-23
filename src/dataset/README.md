# Dataset Synthetic Data Generator

## Data Collecting
to generate the synthetic data out of the existing data, you first have to fill your observations.csv file with data. This could be done by scraping content from existing CSV tables.

## Generating synthetic data
Then you have to execute this command (do not forget to fill the observations.csv file!):
```plain
python synthetic_data_generator.py observations.csv \
  --output-dir dataset_out \
  --test-fraction 0.15 \
  --validation-fraction 0.15 \
  --augment-factor 3 \
  --jitter-fraction 0.02 \
  --seed 42
```

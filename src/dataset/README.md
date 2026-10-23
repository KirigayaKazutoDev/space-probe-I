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


## Überprüfung der Ergebnisse
Führe im Ordner dataset_out diesen Befehl aus, damit wir sicher wissen, ob die Felder tatsächlich korrekt geschrieben wurden:
```plain
python -c "import csv; f=open('train_feature_origins.csv', encoding='utf-8-sig', newline=''); r=csv.DictReader(f); print(r.fieldnames); row=next(r); print('target_azimuth_deg =', repr(row.get('target_azimuth_deg'))); print('augmentation_id =', repr(row.get('augmentation_id')))"
```

Wenn target_azimuth_deg = None erscheint, stimmt möglicherweise der Spaltenname nicht exakt. Wenn target_azimuth_deg = '' und augmentation_id = 'original' erscheinen, ist das Ergebnis wie erwartet.

## Calculate Azimuth
Führe dann diesen Befehl aus:
```plain
python derive_azimuth_labels.py observations.csv -o observations_with_azimuth.csv --ra-unit hours --time-point midpoint
```
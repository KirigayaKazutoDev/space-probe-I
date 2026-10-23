    else:
        warnings.warn("No observation/source grouping column found; splitting individual rows can leak correlated observations.", RuntimeWarning)
        groups = pd.Series([f"row_{i}" for i in range(len(raw))], index=raw.index)
    source_ids = groups.astype(str).to_numpy()

    split_indices = group_split(groups, args.test_fraction, args.validation_fraction, rng)
    split_raw = {name: raw.iloc[idx].copy() for name, idx in split_indices.items()}
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
        frame_raw = split_raw[split_name]
        ref_features = canonical_by_split["train"][FEATURE_COLUMNS] if split_name != "train" else None
        canon, origins, notes = make_canonical_table(
            frame_raw, found, group_col, rng, args.synthetic_target_for_demo,
            reference_features=ref_features
        )
        canon.insert(0, "source_id", groups.iloc[split_indices[split_name]].astype(str).to_numpy())
        canon["_row_index"] = frame_raw.index.to_numpy()
        canonical_by_split[split_name] = canon
        origins_by_split[split_name] = origins
        notes_by_split[split_name] = notes

    # Correct leakage guard: target cannot be essentially copied from input azimuth.
    for split_name, canon in canonical_by_split.items():
        if canon["target_azimuth_deg"].notna().any():
            both = canon["target_azimuth_deg"].notna() & canon["azimuth_deg"].notna()
            if both.any() and ((canon.loc[both, "azimuth_deg"] - canon.loc[both, "target_azimuth_deg"]).abs() < 1e-9).mean() > 0.95:
                raise ValueError("Target leakage: azimuth_deg input equals target_azimuth_deg on >95% of rows. Fix the feature/label definition.")

    # Fit model-input scaling from training rows only.
    norm_params = fit_normalizer(canonical_by_split["train"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "input_csv": str(args.input_csv),
        "seed": args.seed,
        "source_group_column": group_col,
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
            source_copy = canon["source_id"].to_numpy(dtype=str)
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
        csv_out["source_id"] = canon["source_id"].astype(str).to_numpy()
        csv_out["augmentation_id"] = aug_ids.astype(str)
        csv_out.to_csv(args.output_dir / f"{split_name}.csv", index=False)

        npz_fields: dict[str, Any] = {
            "X": X,
            "source_id": canon["source_id"].astype(str).to_numpy(dtype=str),
            "augmentation_id": aug_ids.astype(str),
            "feature_names": np.asarray(FEATURE_COLUMNS, dtype=str),
        }
        if canon["target_azimuth_deg"].notna().all():
            npz_fields["y"] = np.rint(canon["target_azimuth_deg"].to_numpy(dtype=float) * 32.0).astype(np.int64) % NUM_POSITIONS
            npz_fields["y_reg"] = canon["target_azimuth_deg"].to_numpy(dtype=np.float32) / 360.0
        np.savez_compressed(args.output_dir / f"{split_name}.npz", **npz_fields)

        raw_export = canon[FEATURE_COLUMNS + ["target_azimuth_deg"]].copy()
        raw_export.insert(0, "source_id", canon["source_id"].astype(str).to_numpy())
        raw_export["augmentation_id"] = aug_ids.astype(str)
        raw_export.to_csv(args.output_dir / f"{split_name}_feature_origins.csv", index=False)
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

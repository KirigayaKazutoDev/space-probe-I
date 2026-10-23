#!/usr/bin/env python3
"""Convert .json.gz or .json data to CSV and write a schema report.

Supports JSON arrays of records, common wrapper keys (hits/events/data/results/rows/items),
single JSON objects, equally-sized column arrays, and JSON Lines. Nested dictionaries are
flattened using dotted names; lists inside a record are preserved as JSON strings.
This converts formats only; it does not synthesize missing model features.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path
from typing import Any

RECORD_KEYS = (
    "hits", "events", "data", "results", "rows", "items", "records",
    "detections", "candidates",
)


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dictionaries into dotted column names; serialize lists as JSON."""
    out: dict[str, Any] = {}

    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)

            if isinstance(child, dict):
                out.update(flatten(child, name))
            elif isinstance(child, list):
                out[name] = json.dumps(
                    child, ensure_ascii=False, separators=(",", ":")
                )
            else:
                out[name] = child
    else:
        out[prefix or "value"] = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, list)
            else value
        )

    return out


def is_record_list(value: Any) -> bool:
    """True for lists that can represent a sequence of record objects."""
    return isinstance(value, list) and (
        not value or all(isinstance(item, dict) for item in value)
    )


def records_from_obj(obj: Any) -> tuple[list[dict[str, Any]], str]:
    """Convert a parsed JSON value to rows and describe the detected structure."""

    if isinstance(obj, list):
        if all(isinstance(item, dict) for item in obj):
            return [flatten(item) for item in obj], "top-level list of objects"

        return [
            {
                "value": (
                    json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(item, (list, dict))
                    else item
                )
            }
            for item in obj
        ], "top-level list of values"

    if isinstance(obj, dict):
        # Common structures such as {"hits": [{...}, {...}]}.
        for key in RECORD_KEYS:
            value = obj.get(key)
            if is_record_list(value):
                return (
                    [flatten(item) for item in value],
                    f"records found under top-level key '{key}'",
                )

        # Column-oriented JSON: {"snr": [10, 12], "frequency": [100, 101]}.
        arrays = {
            key: value
            for key, value in obj.items()
            if isinstance(value, list)
        }

        if (
            arrays
            and len(arrays) == len(obj)
            and len({len(values) for values in arrays.values()}) == 1
        ):
            n_rows = len(next(iter(arrays.values())))
            rows: list[dict[str, Any]] = []

            for index in range(n_rows):
                row: dict[str, Any] = {}

                for key, values in arrays.items():
                    value = values[index]

                    if isinstance(value, dict):
                        row.update(flatten(value, str(key)))
                    else:
                        row[str(key)] = (
                            json.dumps(
                                value,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            if isinstance(value, list)
                            else value
                        )

                rows.append(row)

            return rows, "column-oriented object of equally-sized arrays"

        # One additional wrapper level, e.g. {"payload": {"hits": [...]}}.
        for key, value in obj.items():
            if isinstance(value, dict):
                for inner_key in RECORD_KEYS:
                    inner = value.get(inner_key)

                    if is_record_list(inner):
                        rows = [
                            {
                                f"{key}.{column}": cell
                                for column, cell in flatten(record).items()
                            }
                            for record in inner
                        ]
                        return rows, f"records found under '{key}.{inner_key}'"

        return [flatten(obj)], "single top-level object (no record list detected)"

    return [{"value": obj}], "single JSON scalar"


def load_json_or_jsonl(text: str) -> tuple[Any, str]:
    """Parse a JSON document, falling back to JSON Lines / NDJSON."""

    try:
        return json.loads(text), "JSON document"

    except json.JSONDecodeError as first_error:
        rows = []

        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Not valid JSON or JSONL. Error on line {line_no}: "
                    f"{exc.msg}; first JSON error: {first_error.msg}"
                ) from exc

        if not rows:
            raise ValueError("Input is empty or contains no readable JSON.")

        return rows, "JSON Lines / NDJSON"


def read_input(path: Path) -> str:
    """Read a .json or .json.gz file as UTF-8 text."""

    if path.name.casefold().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig") as file:
            return file.read()

    with path.open("r", encoding="utf-8-sig") as file:
        return file.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "input",
        type=Path,
        help="Input .json.gz, .gz, or .json file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output CSV (default: input filename with .csv extension)",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV delimiter (default: comma)",
    )

    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file not found or is not a file: {args.input}")

    if len(args.delimiter) != 1:
        parser.error("--delimiter must be exactly one character")

    try:
        # 1. Read and parse the source file.
        text = read_input(args.input)
        obj, input_format = load_json_or_jsonl(text)
        rows, detected_structure = records_from_obj(obj)

        if not rows:
            raise ValueError(
                "No records were found in the input. Check the JSON wrapper/key "
                "structure; an empty CSV will not be written."
            )

        # 2. Determine the output path.
        if args.output is not None:
            output_path = args.output
        else:
            input_name = args.input.name

            if input_name.casefold().endswith(".gz"):
                input_name = input_name[:-3]

            output_path = args.input.with_name(
                Path(input_name).stem + ".csv"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Collect all column names, preserving their first-seen order.
        fieldnames = list(
            dict.fromkeys(
                key
                for row in rows
                for key in row.keys()
            )
        )

        if not fieldnames:
            raise ValueError(
                "The JSON was parsed, but no columns could be identified. "
                "Inspect the source structure before converting it."
            )

        # 4. Write CSV.
        with output_path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
                delimiter=args.delimiter,
                extrasaction="ignore",
            )

            writer.writeheader()
            writer.writerows(rows)

        # 5. Build a schema report with column names and example values.
        schema_path = output_path.with_name(
            f"{output_path.stem}_schema.json"
        )

        columns = []

        for column in fieldnames:
            samples = [
                row[column]
                for row in rows
                if row.get(column) is not None
                and row.get(column) != ""
            ]

            columns.append({
                "name": column,
                "non_empty_count": len(samples),
                "example": samples[0] if samples else None,
            })

        schema = {
            "input_file": str(args.input),
            "output_file": str(output_path),
            "input_format": input_format,
            "detected_structure": detected_structure,
            "row_count": len(rows),
            "column_count": len(fieldnames),
            "columns": columns,
            "notes": [
                "Conversion only: no model features or labels were synthesized.",
                "Lists inside records are serialized as JSON strings in their CSV cells.",
                "Numeric-looking values are written as represented in the source; "
                "this script does not infer physical units.",
            ],
        }

        with schema_path.open("w", encoding="utf-8") as file:
            json.dump(schema, file, indent=2, ensure_ascii=False)
            file.write("\n")

        # 6. Report the result.
        print(f"Detected format: {input_format}")
        print(f"Detected structure: {detected_structure}")
        print(f"Rows written: {len(rows)}")
        print(f"Columns written: {len(fieldnames)}")
        print(f"CSV saved to: {output_path}")
        print(f"Schema saved to: {schema_path}")

        return 0

    except (
        OSError,
        EOFError,
        gzip.BadGzipFile,
        UnicodeError,
        ValueError,
        csv.Error,
    ) as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# example:
# python json_gz_to_csv.py atlas_hits_2025_11.json.gz -o observations.csv
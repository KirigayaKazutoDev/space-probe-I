#!/usr/bin/env python3
"""Convert .json.gz or .json data to CSV and write a schema report.

Supports JSON arrays of records, common wrapper keys (hits/events/data/results/rows/items),
single JSON objects, equally-sized column arrays, and JSON Lines. Nested dictionaries are
flattened using dotted names; lists inside a record are preserved as JSON strings.
This converts formats only; it does not synthesize missing model features.
"""
from __future__ import annotations
import argparse, csv, gzip, json, sys
from pathlib import Path
from typing import Any

RECORD_KEYS = ("hits", "events", "data", "results", "rows", "items", "records", "detections", "candidates")


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, dict):
                out.update(flatten(child, name))
            elif isinstance(child, list):
                out[name] = json.dumps(child, ensure_ascii=False, separators=(",", ":"))
            else:
                out[name] = child
    else:
        out[prefix or "value"] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, list) else value
    return out


def is_record_list(value: Any) -> bool:
    return isinstance(value, list) and (not value or all(isinstance(x, dict) for x in value))


def records_from_obj(obj: Any) -> tuple[list[dict[str, Any]], str]:
    if isinstance(obj, list):
        if all(isinstance(x, dict) for x in obj):
            return [flatten(x) for x in obj], "top-level list of objects"
        return [{"value": json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else x} for x in obj], "top-level list of values"
    if isinstance(obj, dict):
        for key in RECORD_KEYS:
            value = obj.get(key)
            if is_record_list(value):
                return [flatten(x) for x in value], f"records found under top-level key '{key}'"
        arrays = {k: v for k, v in obj.items() if isinstance(v, list)}
        if arrays and len(arrays) == len(obj) and len({len(v) for v in arrays.values()}) == 1:
            n = len(next(iter(arrays.values())))
            rows = []
            for i in range(n):
                row: dict[str, Any] = {}
                for key, values in arrays.items():
                    val = values[i]
                    row.update(flatten(val, str(key)) if isinstance(val, dict) else {
                        str(key): json.dumps(val, ensure_ascii=False, separators=(",", ":")) if isinstance(val, list) else val
                    })
                rows.append(row)
            return rows, "column-oriented object of equally-sized arrays"
        for key, value in obj.items():
            if isinstance(value, dict):
                for inner_key in RECORD_KEYS:
                    inner = value.get(inner_key)
                    if is_record_list(inner):
                        return [{f"{key}.{k}": v for k, v in flatten(rec).items()} for rec in inner], f"records found under '{key}.{inner_key}'"
        return [flatten(obj)], "single top-level object (no record list detected)"
    return [{"value": obj}], "single JSON scalar"


def load_json_or_jsonl(text: str) -> tuple[Any, str]:
    try:
        return json.loads(text), "JSON document"
    except json.JSONDecodeError as first:
        rows = []
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Not valid JSON or JSONL. Error on line {line_no}: {exc.msg}; first JSON error: {first.msg}") from exc
        if not rows:
            raise ValueError("Input is empty or contains no readable JSON.")
        return rows, "JSON Lines / NDJSON"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="Input .json.gz or .json file")
    p.add_argument("-o", "--output", type=Path, help="Output CSV (default: same base name with .csv)")
    p.add_argument("--delimiter", default=",", help="CSV delimiter (default: comma)")
    args = p.parse_args()
    if not args.input.exists():
        p.error(f"Input file not found: {args.input}")
    if len(args.delimiter) != 1:
        p.error("--delimiter must be exactly one character")

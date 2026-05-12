"""Compare two evaluation result CSVs side-by-side.

Typical workflow
----------------
    # 1. Produce v1 results
    cd v1 && python evaluate.py --engine lingua

    # 2. Produce v2 results
    cd v2/src && python evaluate.py

    # 3. Compare
    cd ../..
    python compare.py v1/results/eval_v1_lingua_*.csv v2/results/eval_*.csv

Inputs
------
Two CSVs in the schema produced by v1/evaluate.py and v2/src/evaluate.py.
Both must contain `detected_language`, `verify_result`, and either
`VA_SAMPLE`/equivalent input column plus `GT_language`/equivalent.

Rows are joined by **position (row index)** — both CSVs are expected to come
from the same input dataset in the same order.

Output
------
A comparison CSV with columns:
    input, gt,
    v1_label, v1_confidence, v1_result,
    v2_label, v2_confidence, v2_rule, v2_result,
    agreement     — "agree" | "disagree"
    correct_only  — "both" | "v1_only" | "v2_only" | "neither"

Summary printed to stdout:
    - overall accuracy of each side
    - agreement rate
    - disagreement breakdown (v1_label × v2_label, with which side was right)
    - cases v2 fixed (v1 wrong, v2 right) and cases v2 regressed
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

INPUT_COL_ALIASES = (
    "VA_SAMPLE", "input", "text", "sentence", "query", "utterance",
)
GT_COL_ALIASES = (
    "GT_language", "ground_truth", "gt", "label", "expected",
)


def _normalize(name: str) -> str:
    return name.lstrip("﻿").strip().lower()


def _find_column(fieldnames, aliases):
    norm = {_normalize(n): n for n in fieldnames}
    for alias in aliases:
        if alias.lower() in norm:
            return norm[alias.lower()]
    return None


def _read(path: Path):
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    return fields, rows


def compare(v1_path: Path, v2_path: Path, output_path: Path) -> None:
    v1_fields, v1_rows = _read(v1_path)
    v2_fields, v2_rows = _read(v2_path)

    if len(v1_rows) != len(v2_rows):
        sys.exit(f"Row count mismatch: v1={len(v1_rows)} v2={len(v2_rows)}")

    input_col = _find_column(v1_fields, INPUT_COL_ALIASES) \
        or _find_column(v2_fields, INPUT_COL_ALIASES)
    gt_col = _find_column(v1_fields, GT_COL_ALIASES) \
        or _find_column(v2_fields, GT_COL_ALIASES)
    if input_col is None or gt_col is None:
        sys.exit(f"Could not locate input/GT columns. v1={v1_fields} v2={v2_fields}")

    print(f"v1: {v1_path}  ({len(v1_rows)} rows)")
    print(f"v2: {v2_path}  ({len(v2_rows)} rows)")
    print(f"Output: {output_path}\n")

    out_fields = [
        "row", "input", "gt",
        "v1_label", "v1_confidence", "v1_result",
        "v2_label", "v2_confidence", "v2_rule", "v2_result",
        "agreement", "correct_only",
    ]
    out_rows = []

    agree = disagree = 0
    v1_correct = v2_correct = 0
    both_correct = 0
    fixed = regressed = both_wrong = 0
    disagreement_matrix: dict[tuple[str, str], int] = Counter()
    fixed_samples: dict[tuple[str, str], list] = defaultdict(list)
    regressed_samples: dict[tuple[str, str], list] = defaultdict(list)
    both_wrong_samples: dict[tuple[str, str], list] = defaultdict(list)

    skipped = 0
    for i, (r1, r2) in enumerate(zip(v1_rows, v2_rows), 1):
        # Skip rows where either side skipped (empty input, etc.)
        v1_result = r1.get("verify_result", "")
        v2_result = r2.get("verify_result", "")
        if v1_result == "SKIP" or v2_result == "SKIP":
            skipped += 1
            continue

        text = (r1.get(input_col) or r2.get(input_col) or "").strip()
        gt = _normalize(r1.get(gt_col) or r2.get(gt_col) or "")
        v1_label = (r1.get("detected_language") or "").strip()
        v2_label = (r2.get("detected_language") or "").strip()

        agreement = "agree" if v1_label == v2_label else "disagree"
        if agreement == "agree":
            agree += 1
        else:
            disagree += 1
            disagreement_matrix[(v1_label, v2_label)] += 1

        v1_ok = (v1_label == gt)
        v2_ok = (v2_label == gt)
        if v1_ok:
            v1_correct += 1
        if v2_ok:
            v2_correct += 1
        if v1_ok and v2_ok:
            both_correct += 1
            correct_only = "both"
        elif v2_ok and not v1_ok:
            fixed += 1
            correct_only = "v2_only"
            fixed_samples[(v1_label, gt)].append((i, text))
        elif v1_ok and not v2_ok:
            regressed += 1
            correct_only = "v1_only"
            regressed_samples[(v2_label, gt)].append((i, text))
        else:
            both_wrong += 1
            correct_only = "neither"
            both_wrong_samples[(v1_label, v2_label)].append((i, gt, text))

        out_rows.append({
            "row": i,
            "input": text,
            "gt": gt,
            "v1_label": v1_label,
            "v1_confidence": r1.get("confidence", ""),
            "v1_result": v1_result,
            "v2_label": v2_label,
            "v2_confidence": r2.get("confidence", ""),
            "v2_rule": r2.get("rule", ""),
            "v2_result": v2_result,
            "agreement": agreement,
            "correct_only": correct_only,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"Wrote {len(out_rows)} comparison rows → {output_path}\n")

    n = len(out_rows)
    if n == 0:
        print("No rows compared.")
        return

    def _hr(title):
        print("\n" + "=" * 72)
        print(f"  {title}")
        print("=" * 72)

    _hr("HEAD-TO-HEAD ACCURACY")
    print(f"  Compared rows:   {n}  (skipped {skipped})")
    print(f"  v1 correct:      {v1_correct:>6}  ({v1_correct/n*100:6.2f}%)")
    print(f"  v2 correct:      {v2_correct:>6}  ({v2_correct/n*100:6.2f}%)")
    print(f"  Both correct:    {both_correct:>6}  ({both_correct/n*100:6.2f}%)")
    print(f"  v2 fixed v1:     {fixed:>6}  ({fixed/n*100:6.2f}%)")
    print(f"  v2 regressed:    {regressed:>6}  ({regressed/n*100:6.2f}%)")
    print(f"  Both wrong:      {both_wrong:>6}  ({both_wrong/n*100:6.2f}%)")

    _hr("AGREEMENT")
    print(f"  Agree:    {agree:>6}  ({agree/n*100:6.2f}%)")
    print(f"  Disagree: {disagree:>6}  ({disagree/n*100:6.2f}%)")

    if disagreement_matrix:
        _hr("DISAGREEMENT MATRIX  (v1_label → v2_label : count)")
        for (a, b), count in disagreement_matrix.most_common():
            print(f"  {a:<12} → {b:<12} {count:>5}")

    if fixed_samples:
        _hr("CASES v2 FIXED  (v1_wrong → gt, 3 samples each)")
        for (v1_label, gt), samples in sorted(fixed_samples.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"\n  v1={v1_label}  gt={gt}   ({len(samples)} cases)")
            for idx, text in samples[:3]:
                preview = text if len(text) <= 75 else text[:72] + "..."
                print(f"    [row {idx}] {preview}")

    if regressed_samples:
        _hr("CASES v2 REGRESSED  (v2_wrong → gt, 3 samples each)")
        for (v2_label, gt), samples in sorted(regressed_samples.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"\n  v2={v2_label}  gt={gt}   ({len(samples)} cases)")
            for idx, text in samples[:3]:
                preview = text if len(text) <= 75 else text[:72] + "..."
                print(f"    [row {idx}] {preview}")

    if both_wrong_samples:
        _hr("CASES BOTH WRONG  (v1, v2, gt, 3 samples each)")
        for (v1_label, v2_label), samples in sorted(both_wrong_samples.items(), key=lambda kv: -len(kv[1]))[:6]:
            print(f"\n  v1={v1_label}  v2={v2_label}   ({len(samples)} cases)")
            for idx, gt, text in samples[:3]:
                preview = text if len(text) <= 75 else text[:72] + "..."
                print(f"    [row {idx}] gt={gt}  {preview}")


if __name__ == "__main__":
    HERE = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("v1_csv", type=Path, help="v1 evaluation results CSV")
    p.add_argument("v2_csv", type=Path, help="v2 evaluation results CSV")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output comparison CSV (default: ./results/compare_<ts>.csv)")
    args = p.parse_args()

    for path in (args.v1_csv, args.v2_csv):
        if not path.exists():
            sys.exit(f"CSV not found: {path}")

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = HERE / "results" / f"compare_{ts}.csv"

    compare(args.v1_csv, args.v2_csv, args.output)

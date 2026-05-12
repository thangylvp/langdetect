"""Evaluate the rule-based detector on a labeled CSV dataset.

Usage
-----
    python evaluate.py [INPUT_CSV] [-o OUTPUT_CSV]

Defaults
--------
INPUT_CSV   ../../Result_LIB_language_20260428_122621(user_inputs).csv
            (i.e. the CSV at the langdetect top level)
OUTPUT_CSV  ../results/eval_<input-stem>_<timestamp>.csv

The script auto-detects the *input column* and *ground-truth column* by name
(see INPUT_COL_ALIASES / GT_COL_ALIASES below) — so to test on a new dataset,
you just drop a CSV with a recognisable column header and run.

CSV output schema
-----------------
All original columns are preserved; these are added/overwritten:
    detected_language     — our model's prediction
    confidence            — our model's confidence (0-1)
    rule                  — which rule fired (e.g. "rule_2_step_1")
    evidence              — JSON: which tokens triggered the rule
    processing_time_ms    — per-row inference time
    verify_result         — PASS / FAIL / ERROR / SKIP
    verify_note           — human-readable mismatch description
    error_message         — exception text if the model raised

A summary (confusion matrix + per-label accuracy + rule histogram +
top failure patterns) is printed to stdout at the end.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from rule_detector import detect


# ---------------------------------------------------------------------------
# Column auto-detection
# ---------------------------------------------------------------------------

# First match wins; comparison is case-insensitive and BOM-stripped.
INPUT_COL_ALIASES = (
    "VA_SAMPLE", "input", "text", "sentence", "query", "utterance",
)
GT_COL_ALIASES = (
    "GT_language", "ground_truth", "gt", "label", "expected",
)

# Columns the script writes/overwrites in the output CSV (added if missing).
OUTPUT_COLS = (
    "detected_language", "confidence", "rule", "evidence",
    "processing_time_ms", "verify_result", "verify_note", "error_message",
)


def _normalize(name: str) -> str:
    return name.lstrip("﻿").strip().lower()


def find_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    """Return the original column name that matches any alias, else None."""
    norm = {_normalize(n): n for n in fieldnames}
    for alias in aliases:
        if alias.lower() in norm:
            return norm[alias.lower()]
    return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(
    input_path: Path,
    output_path: Path,
    progress_every: int = 500,
) -> dict:
    with input_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    input_col = find_column(fieldnames, INPUT_COL_ALIASES)
    gt_col = find_column(fieldnames, GT_COL_ALIASES)
    if input_col is None:
        sys.exit(
            f"No input column matched. Tried {INPUT_COL_ALIASES}.\n"
            f"Found columns: {fieldnames}"
        )
    if gt_col is None:
        sys.exit(
            f"No ground-truth column matched. Tried {GT_COL_ALIASES}.\n"
            f"Found columns: {fieldnames}"
        )

    print(f"Input:  {input_path}")
    print(f"        rows={len(rows)}  input_col={input_col!r}  gt_col={gt_col!r}")
    print(f"Output: {output_path}\n")

    out_fields = list(fieldnames)
    for col in OUTPUT_COLS:
        if col not in out_fields:
            out_fields.append(col)

    stats = Counter()
    confusion: dict[str, Counter] = defaultdict(Counter)   # gt → detected → count
    rule_counts: Counter = Counter()
    failures: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    out_rows: list[dict] = []

    t_start = time.perf_counter()
    for i, row in enumerate(rows, 1):
        text = (row.get(input_col) or "").strip()
        gt = _normalize(row.get(gt_col) or "")

        new_row = dict(row)
        if not text:
            new_row.update({c: "" for c in OUTPUT_COLS})
            new_row["verify_result"] = "SKIP"
            new_row["verify_note"] = "empty input"
            out_rows.append(new_row)
            continue

        stats["total"] += 1
        t0 = time.perf_counter()
        try:
            r = detect(text)
            ms = (time.perf_counter() - t0) * 1000.0
            detected = r.label.value
            confidence = r.confidence
            rule = r.rule
            evidence = json.dumps(r.evidence, ensure_ascii=False)
            err = ""
        except Exception as e:                      # pragma: no cover
            ms = (time.perf_counter() - t0) * 1000.0
            detected, confidence, rule, evidence, err = "error", 0.0, "error", "", str(e)
            stats["error"] += 1

        rule_counts[rule] += 1
        confusion[gt][detected] += 1

        if err:
            verify, note = "ERROR", err
        elif detected == gt:
            verify, note = "PASS", ""
            stats["pass"] += 1
        else:
            verify, note = "FAIL", f"GT={gt}, detected={detected}"
            stats["fail"] += 1
            sample_id = row.get(fieldnames[0]) or str(i)
            failures[(gt, detected)].append((sample_id, text))

        new_row.update({
            "detected_language": detected,
            "confidence": f"{confidence:.6f}",
            "rule": rule,
            "evidence": evidence,
            "processing_time_ms": f"{ms:.3f}",
            "verify_result": verify,
            "verify_note": note,
            "error_message": err,
        })
        out_rows.append(new_row)

        if progress_every and i % progress_every == 0:
            elapsed = time.perf_counter() - t_start
            rate = i / elapsed if elapsed else 0.0
            eta = (len(rows) - i) / rate if rate else 0.0
            print(f"  ... {i}/{len(rows)}  ({rate:.0f} rows/s, ETA {eta:.0f}s)",
                  flush=True)

    total_elapsed = time.perf_counter() - t_start
    print(f"\nDone in {total_elapsed:.1f}s "
          f"({stats['total'] / total_elapsed:.0f} rows/s)\n")

    # ----- Write output -----
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"Wrote {len(out_rows)} rows → {output_path}")

    print_summary(stats, confusion, rule_counts, failures)
    return {
        "stats": dict(stats),
        "confusion": {gt: dict(c) for gt, c in confusion.items()},
        "rule_counts": dict(rule_counts),
    }


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------

def print_summary(stats, confusion, rule_counts, failures) -> None:
    n = stats["total"]
    if n == 0:
        print("No rows processed.")
        return

    def _hr(title: str) -> None:
        print("\n" + "=" * 72)
        print(f"  {title}")
        print("=" * 72)

    _hr("SUMMARY")
    print(f"  Total:  {n}")
    print(f"  PASS :  {stats['pass']:>6}  ({stats['pass']/n*100:6.2f}%)")
    print(f"  FAIL :  {stats['fail']:>6}  ({stats['fail']/n*100:6.2f}%)")
    print(f"  ERROR:  {stats['error']:>6}  ({stats['error']/n*100:6.2f}%)")

    labels = sorted(set(list(confusion.keys())
                        + [d for v in confusion.values() for d in v]))
    if labels:
        _hr("CONFUSION MATRIX (rows = GT, cols = detected)")
        col_w = max(12, max(len(l) for l in labels) + 2)
        gt_w = max(20, max(len(l) for l in labels) + 4)
        gt_label = "GT \\ detected"
        header = f"  {gt_label:<{gt_w}}"
        for d in labels:
            header += f"{d:>{col_w}}"
        header += f"{'total':>{col_w}}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for gt in labels:
            row_total = sum(confusion[gt].values())
            if row_total == 0:
                continue
            line = f"  {gt:<{gt_w}}"
            for d in labels:
                line += f"{confusion[gt].get(d, 0):>{col_w}}"
            line += f"{row_total:>{col_w}}"
            print(line)

    _hr("PER-LABEL ACCURACY")
    for gt in labels:
        row_total = sum(confusion[gt].values())
        if row_total == 0:
            continue
        correct = confusion[gt].get(gt, 0)
        print(f"  {gt:<22} {correct:>5} / {row_total:<5}  "
              f"= {correct/row_total*100:6.2f}%")

    _hr("RULE FIRE COUNTS")
    for rule, count in rule_counts.most_common():
        print(f"  {rule:<28} {count:>6}  ({count/n*100:5.2f}%)")

    if failures:
        _hr("TOP FAILURE PATTERNS (with 3 sample inputs each)")
        for (gt, detected), samples in sorted(
            failures.items(), key=lambda kv: -len(kv[1])
        )[:8]:
            print(f"\n  {gt}  →  {detected}   ({len(samples)} cases)")
            for sid, text in samples[:3]:
                preview = text if len(text) <= 75 else text[:72] + "..."
                print(f"    [{sid}] {preview}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    HERE = Path(__file__).resolve().parent             # v2/src
    DEFAULT_INPUT = (HERE.parent.parent
                     / "Result_LIB_language_20260428_122621(user_inputs).csv")
    DEFAULT_RESULTS = HERE.parent / "results"          # v2/results

    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT,
                   help="Path to a labeled CSV. (default: the user-inputs CSV "
                        "at the langdetect top level)")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Output CSV path. (default: "
                        "../results/eval_<input-stem>_<timestamp>.csv)")
    p.add_argument("--progress", type=int, default=500,
                   help="Print progress every N rows. 0 disables. (default 500)")
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"Input CSV not found: {args.input}")

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = DEFAULT_RESULTS / f"eval_{args.input.stem}_{ts}.csv"

    evaluate(args.input, args.output, progress_every=args.progress)

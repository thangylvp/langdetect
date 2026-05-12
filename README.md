# langdetect

Vietnamese / English language detector for the conversational-AI gateway.
Four parallel implementations live in the repo. Detailed per-version
results, head-to-head deltas, and design rationale are in
[PROGRESS.md](PROGRESS.md). Architecture and conventions for working
inside the repo are in [CLAUDE.md](CLAUDE.md).

| Folder | Approach | Accuracy | Mean latency | Notes |
|---|---|---|---|---|
| [`v1/`](v1/) | Lingua / FastText wrappers, single-confidence threshold | 99.13 % | 0.03 ms | Production-shipped via FastAPI |
| [`v2/src/`](v2/src/) | Rule-based pipeline using `underthesea` POS + NER | 99.18 % | 2.05 ms | Implements the old 4-step Rule 2 |
| [`v3/src/`](v3/src/) | v2 + Vingroup brand gazetteer + INTERJECTIONS trim | **99.34 %** | 2.30 ms | Highest accuracy on this dataset |
| [`v4/src/`](v4/src/) | Lingua-centric + 3 spec-mandated overrides (translation-Q, exception list, entity-only) | 99.03 % | **0.10 ms** | Implements the **new May 2026 spec**; ~24× faster than v3 |

## v4 — current spec-aligned focus

```
v4/
├── phuluc.md              ← Phụ lục A: Bảng 1–4 (carried from v2)
├── task_requirement.md    ← spec: Quy tắc 1–4 (updated May 2026)
└── src/
    ├── rule_detector.py        ← main pipeline (Lingua + 3 overrides)
    ├── lingua_classifier.py    ← binary + multilang Lingua wrappers
    ├── translation_question.py ← Rule 2 Step 1 (strip X, recurse)
    ├── entities.py             ← cultural terms + Vingroup brands + 5-entry exception list + metalinguistic verbs
    ├── test_rule_detector.py
    └── evaluate.py             ← CSV-driven evaluation harness
```

### Setup

```bash
pip install -r requirements.txt
```

### Run unit tests

```bash
cd v4/src && python -m pytest test_rule_detector.py -v

# Single test by substring:
cd v4/src && python -m pytest test_rule_detector.py -k "translation_q" -v
```

### Evaluate against a labelled CSV

```bash
cd v4/src
python evaluate.py [INPUT_CSV] [-o OUTPUT_CSV]
```

- Default input: `../../Result_LIB_language_*.csv` at the repo root
- Default output: `../results/eval_<input-stem>_<timestamp>.csv`
- Auto-detects the input column (`VA_SAMPLE` / `input` / `text` / …)
  and the ground-truth column (`GT_language` / `ground_truth` / `label` / …)

### Head-to-head between two versions

```bash
python compare.py <v_a>/results/eval_*.csv <v_b>/results/eval_*.csv
```

Outputs `results/compare_*.csv` plus a stdout summary
(agreement, fixed, regressed, both-wrong).

## Sentence-purity accuracy (v4)

| Bucket | Count | Accuracy |
|---|---:|---:|
| Pure VN with diacritic | 1177 | **100.00 %** |
| Pure EN (ASCII only) | 106 | **100.00 %** |
| VN typed without diacritic | 28 | 25.00 % |
| Mixed | 6605 | 99.17 % |

Both pure single-language buckets are perfect. The typed-without-diacritic
case is the realistic typo scenario — v4 is 3.5× better here than v3
(25 % vs 7 %), because Lingua's character n-gram model recognises VN
orthographic patterns even without tone marks.

For per-row failures: see [v4/results/v4_failures.csv](v4/results/v4_failures.csv).

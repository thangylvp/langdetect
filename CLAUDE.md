# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`langdetect` detects whether input text is English (`EN`), Vietnamese (`VI`), `UNKNOWN`, or `UNSUPPORTED`. It has three independent implementations:

- **[v1/](v1/)** — Thin wrappers around `lingua-language-detector` and FastText; intended for production use as a FastAPI router mounted at `/api/v2/langdetect`. 99.13% accuracy.
- **[v2/src/](v2/src/)** — Rule-based pipeline using POS + NER tagging via `underthesea`. 99.18% accuracy.
- **[v3/src/](v3/src/)** — v2 + Vingroup brand gazetteer + INTERJECTIONS trim. **99.34% accuracy** — zero-regression upgrade over v2. Current best.

For per-version results, fixes, regressions, and planned next steps, see [PROGRESS.md](PROGRESS.md).

## Running tests

```bash
cd v2/src && python -m pytest test_rule_detector.py -v   # v2 — 64 tests
cd v3/src && python -m pytest test_rule_detector.py -v   # v3 — 83 tests (adds brand + INTERJECTIONS cases)
```

No tests exist for v1.

## Running evaluation + comparison

```bash
cd v1 && python evaluate.py                      # v1 lingua  → v1/results/eval_v1_*.csv
cd v2/src && python evaluate.py                  # v2         → v2/results/eval_*.csv
cd v3/src && python evaluate.py                  # v3         → v3/results/eval_*.csv

# Head-to-head between any two result CSVs (joins by row index):
python compare.py <v_a>.csv <v_b>.csv            # → results/compare_*.csv + summary
```

## Architecture

### v1 — Library wrappers

Four-layer design, all files under [v1/](v1/):

- **[detector.py](v1/detector.py)** — `Language` enum (`EN`, `VI`, `UNKNOWN`), abstract `LanguageDetector`, and two concrete classes:
  - `LinguaDetector`: filters to EN/VI, returns `VI` when confidence < 0.5
  - `FastTextDetector`: loads `lid.176.ftz`, patches NumPy 2.x at import time
- **[service.py](v1/service.py)** — `@lru_cache` singletons; `detect(text, engine)` returns `(Language, float)`
- **[schemas.py](v1/schemas.py)** — Pydantic `DetectRequest` / `DetectResponse`, `DetectorEngine` enum
- **[router.py](v1/router.py)** — `POST /langdetect/detect`; parent app mounts with `/api/v2` prefix

FastText binary model: [models/lid.176.ftz](models/lid.176.ftz) — only loaded when `engine=fasttext`.

### v2 — Rule-based pipeline

All logic lives in [v2/src/rule_detector.py](v2/src/rule_detector.py). Rules fire in order; first match wins:

| Rule | Trigger | Label |
|---|---|---|
| **Rule 4** | Non-Latin script dominates (>30% non-Latin alpha chars) | `UNSUPPORTED` |
| **Rule 3** | Only interjections, numbers, or empty | `UNKNOWN` |
| **Rule 1** | No VN tokens → EN; no EN tokens → VI | `EN` / `VI` |
| **Rule 2 Step 1** | Any VN closed-class POS token (pronouns, particles, prepositions...) | `VI` |
| **Rule 2 Step 2** | Text starts with an English grammar anchor | `EN` |
| **Rule 2 Step 4.1** | All VN tokens are named entities | `EN` |
| **Rule 2 Step 4.2** | Any VN open-class token | `VI` |

A token is considered "Vietnamese" only if it contains VN diacritics OR is in `CULTURAL_TERMS`. This diacritic gate prevents `underthesea` from hallucinating on plain ASCII text.

Rule 2 Step 1 fires on **closed-class POS only** (`E`, `T`, `C`, `Cb`, `Cc`, `P`, `L`) — open-class POS (verbs, adjectives) are excluded because `underthesea` frequently mis-tags English/foreign words.

Supporting data files:
- [v2/src/cultural_terms.py](v2/src/cultural_terms.py) — ~35 Vietnamese cultural terms (e.g. phở, áo dài, tết) that `underthesea` tags as common nouns but should be treated as named entities in English context
- [v2/src/en_anchors.py](v2/src/en_anchors.py) — ~150 English grammar anchors sorted longest-first for greedy prefix matching

### Result output schema (v2)

```python
DetectionResult(label, confidence, rule, evidence)
# rule examples: "rule_1_pure_vi", "rule_2_step_1", "rule_2_step_4_2"
# evidence: dict with token lists and match metadata for explainability
```

## Running the service (v1)

No standalone entrypoint — runs as part of the gateway:

```bash
cd packages/gateway
uvicorn backend.main:app --reload
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `FASTTEXT_MODEL_PATH` | Only for v1 FastText engine | Path to `lid.176.ftz` |

## Dependencies

- `lingua-language-detector>=2.0.2` — v1 default engine
- `fasttext-langdetect>=1.0.5` — v1 optional FastText engine
- `underthesea` — v2 POS + NER tagging
- `pytest` — v2 test runner

## Known failure patterns (v2, 65/7917 rows = 0.82%)

- **45 vi→en**: No-diacritic VN words (dyno, sao, xa) pass the diacritic gate and are invisible to the rule engine
- **9 vi→unknown**: Ambiguous short inputs ("hello", "alo") are in `INTERJECTIONS`
- **8 en→vi**: A stray VN function word overrides Rule 2 Step 1 (e.g. "hey dyno đi")
- **3 en→unknown**: Common greetings in `INTERJECTIONS` list

## Key reference documents

- [DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md) — Design decisions, rejected approaches, and next improvement targets
- [v2/task_requirement.md](v2/task_requirement.md) — Full spec (in Vietnamese) with rule definitions and consequence table
- [phuluc.md](phuluc.md) — Reference tables: VN cultural terms, common nouns, function words, EN grammar anchors

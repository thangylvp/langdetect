# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`langdetect` detects whether input text is English (`EN`), Vietnamese (`VI`), `UNKNOWN`, or `UNSUPPORTED`. It has four independent implementations:

- **[v1/](v1/)** — Thin wrappers around `lingua-language-detector` and FastText; intended for production use as a FastAPI router mounted at `/api/v2/langdetect`. 99.13% accuracy.
- **[v2/src/](v2/src/)** — Rule-based pipeline using POS + NER tagging via `underthesea`. 99.18% accuracy.
- **[v3/src/](v3/src/)** — v2 + Vingroup brand gazetteer + INTERJECTIONS trim. **99.34% accuracy** — highest on this dataset.
- **[v4/src/](v4/src/)** — Structural rewrite for the May 2026 spec: Lingua-centric pipeline with 3 spec-mandated overrides (translation-question / exception list / entity-only). 99.03% accuracy, **~100× faster** than v3, implements the new 3-step Rule 2.

For per-version results, fixes, regressions, and planned next steps, see [PROGRESS.md](PROGRESS.md).

## Running tests

```bash
cd v2/src && python -m pytest test_rule_detector.py -v   # v2 — 64 tests
cd v3/src && python -m pytest test_rule_detector.py -v   # v3 — 83 tests (adds brand + INTERJECTIONS cases)
cd v4/src && python -m pytest test_rule_detector.py -v   # v4 — 74 tests (Lingua-centric, new spec)

# Run a single test by name substring:
cd v4/src && python -m pytest test_rule_detector.py -k "exception" -v
```

No tests exist for v1.

## Running evaluation + comparison

```bash
cd v1 && python evaluate.py                      # v1 lingua  → v1/results/eval_v1_*.csv
cd v2/src && python evaluate.py                  # v2         → v2/results/eval_*.csv
cd v3/src && python evaluate.py                  # v3         → v3/results/eval_*.csv
cd v4/src && python evaluate.py                  # v4         → v4/results/eval_*.csv

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

### Result output schema (v2 / v3)

```python
DetectionResult(label, confidence, rule, evidence)
# rule examples: "rule_1_pure_vi", "rule_2_step_1", "rule_2_step_4_2"
# evidence: dict with token lists and match metadata for explainability
```

### v4 — Lingua-centric pipeline (new May 2026 spec)

A structural rewrite implementing the updated 3-step Rule 2 from the spec.
Lingua's binary EN/VI sentence verdict is the primary classifier
(decides 97.26 % of rows); three deterministic overrides handle the
spec's special cases.

| Rule / step | Trigger | Label |
|---|---|---|
| **Rule 4a** | Non-Latin script dominates | `UNSUPPORTED` |
| **Rule 3** | Only interjections / numbers / empty (VN diacritic exempts) | `UNKNOWN` |
| **Rule 2 Step 1** | Translation question — closed-class metalinguistic verb + minority-language token → strip X, recurse | (recurse) |
| **Lingua baseline** | Binary EN/VI sentence-level Lingua verdict | `EN` / `VI` |
| **Override A** | Spec exception list (`em`, `anh`, `nha`, `cho anh`, `cho em`) with word boundary → flip Lingua-EN to `VI` | `VI` |
| **Override B** | All VN-bearing tokens are entities (cultural / brand / title-cased mid-sentence) → flip Lingua-VI to `EN` | `EN` |
| **Rule 4b** | Wider Lingua picks es/fr/de/it/nl with conf > 0.6 AND wider-VI < 0.05, on ≥3-word text without VN-unique characters | `UNSUPPORTED` |
| **Rule 3'** | Lingua confidence < 0.55 | `UNKNOWN` |

Title-case entity heuristic **skips the first word** of the sentence —
sentence-start capitalization is forced by convention, not by proper-noun
marking (`"Năm 2000"` → first word `Năm` is NOT an entity).

Supporting files:
- [v4/src/lingua_classifier.py](v4/src/lingua_classifier.py) — binary EN/VI + multilang detectors, cached singletons
- [v4/src/translation_question.py](v4/src/translation_question.py) — closed-class verb + minority-language token detector
- [v4/src/entities.py](v4/src/entities.py) — `CULTURAL_TERMS` (36) + `VINGROUP_BRANDS` (57, expanded from v3's 29) + spec exception list (5, frozen) + `METALINGUISTIC_VERBS` (19)

What v4 deletes vs v3: `EN_ANCHORS` (164 entries), `underthesea` dependency, the POS-based Step 1. Total enumerated entries 263 → 149 (−43 %).

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

- `lingua-language-detector>=2.0.2` — v1 default engine + v4 primary classifier
- `fasttext-langdetect>=1.0.5` — v1 optional FastText engine
- `underthesea` — v2 / v3 POS + NER tagging
- `pytest` — test runner

v4 has no `underthesea` dependency; v2 / v3 have no `lingua-language-detector` dependency at runtime.

## Known failure patterns

### v3 (52 / 7917 = 0.66 %)

- **40 vi→en**: No-diacritic VN words slip the diacritic gate
- **8 en→vi**: A stray VN function word over-fires Step 1 on EN-structured input
- **4 vi→unknown**: Short ambiguous inputs (`alo alo 1`, `123`, `ok`)

### v4 (77 / 7917 = 0.97 %)

- **37 vi→en**: No-diacritic VN like `dyno`, `xa`, `safari` — per **new spec** these are correctly `en`; GT-side context-dependent label
- **23 en→vi**: Multi-word VN proper-noun phrases (`Khỉ sóc tai đen`, `Linh dương nước`) — v4 has no NER fallback, only the title-case heuristic
- **13 vi→unknown**: Lingua confidence < 0.55 on short / ambiguous inputs
- **4 en→unknown**: Same — Lingua undecided

Per-row v4 failures dumped to [v4/results/v4_failures.csv](v4/results/v4_failures.csv) (3-column: `sentence, gt, pred`).

## Key reference documents

- [DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md) — Design decisions, rejected approaches, and next improvement targets
- [v2/task_requirement.md](v2/task_requirement.md) — Full spec (in Vietnamese) with rule definitions and consequence table
- [phuluc.md](phuluc.md) — Reference tables: VN cultural terms, common nouns, function words, EN grammar anchors

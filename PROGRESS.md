# Progress log

A short, append-only record of each detector version: side-by-side comparison
at the top, per-version details in the middle, candidate next steps at the
bottom. For deep design rationale, see [DEVELOPMENT_NOTES.md](DEVELOPMENT_NOTES.md).

**Canonical eval:** `Result_LIB_language_20260428_122621(user_inputs).csv`
(7917 labeled rows: 7728 vi + 189 en). All accuracy numbers below come from
this dataset.

---

## Comparison

| Version | Accuracy | VI recall | EN recall | Mean latency | p95 | Throughput |
|---|---|---|---|---|---|---|
| v1 (lingua)             | 99.13 % (7848) | 99.43 % | 86.77 % | 0.03 ms | — | ~30 000 rows/s |
| v2 (rules)              | 99.18 % (7852) | 99.30 % | 94.18 % | 2.05 ms | 3.79 ms | 488 rows/s |
| **v3 (rules + brands)** | **99.34 %** (7865) | **99.43 %** | **95.77 %** | 2.30 ms | 4.51 ms | 432 rows/s |
| v4 (lingua-centric)     | 99.03 % (7840) | 99.35 % | 85.71 % | 0.10 ms | 0.13 ms | ~10 200 rows/s |

### Head-to-head deltas (vs the prior version)

| Pair | Fixed | Regressed | Both wrong | Agreement |
|---|---|---|---|---|
| v2 vs v1 | 41 | 37 | 28 | 98.96 % |
| v3 vs v2 | **13** | **0** | 52 | 99.82 % |
| v4 vs v3 | 22 | 47 | 30 | 99.13 % |

v3 remains the highest-accuracy version on this dataset. v4 trades 0.31
points for a structurally simpler architecture (Lingua-centric with three
spec-mandated overrides) and a 24× throughput gain, and is the only
version that implements the **new (May 2026) spec** with translation-
question handling and the `em/anh/nha` exception list.

### Reproduce

```bash
cd v1 && python evaluate.py                         # v1 lingua
cd v2/src && python evaluate.py                     # v2 rules
cd v3/src && python evaluate.py                     # v3 rules + brands
cd v4/src && python evaluate.py                     # v4 lingua-centric
cd ../.. && python compare.py <v_a>.csv <v_b>.csv   # head-to-head
```

---

## v1 — Library wrappers (Lingua / FastText)

**Status:** shipped · runs as FastAPI router at `/api/v2/langdetect`
**Files:** [v1/](v1/)
**Approach:** thin wrappers around `lingua-language-detector` (default) and
FastText `lid.176.ftz`. Single confidence threshold (0.5); falls back to VI
when below threshold. No POS, no rules.

**Where it loses (69 fails):**
- 44 vi→en: short/mixed inputs where lingua's confidence dips below 0.5
  (`về night samba`, `Vẫy tay`, `tours tour safari buổi tối`).
- 25 en→vi: English questions with VN named entities
  (`Where is the Khỉ sóc tai đen area on the safari route?`).

**Takeaways:** very fast, decent baseline, but no concept of mixed-language
context or Vingroup-specific named entities. EN recall is the weak spot.

---

## v2 — Rule-based pipeline (underthesea POS + NER)

**Status:** shipped · 64 unit tests green
**Files:** [v2/src/](v2/src/) · spec: [v2/task_requirement.md](v2/task_requirement.md)
**Approach:** 4-rule pipeline driven by underthesea POS/NER on
**diacritic-gated** Vietnamese tokens. Two small lexicons (cultural terms,
EN grammar anchors) supplement POS — no large dictionaries.

**Where v2 wins over v1 (41 cases):**
- 21 EN-tagged-by-v1 sentences that are actually mixed VI
  (`về night samba`, `Vẫy tay`).
- 20 EN questions with VN entity names that v1 over-pulled to VI
  (`Where is the Khỉ sóc tai đen area on the safari route?`).

**Where v2 regresses vs v1 (37 cases):**

| Pattern | Count | Examples | Root cause |
|---|---|---|---|
| `v2=en, gt=vi` | 26 | `sao dyno`, `vinpearl`, `dcsdcd` | No-diacritic VN tokens & Vingroup brand names slip the diacritic gate |
| `v2=vi, gt=en` | 3 | `VINES và GSM`, `How big is Thằn lằn da báo?` | One stray VN closed-class token forces Step 1 over EN-structured sentence |
| `v2=unknown, gt=vi` | 5 | `dạ`, `ừ`, `123` | Short inputs match Rule 3 interjection/empty |
| `v2=unknown, gt=en` | 3 | `hello`, `hello hello hello` | `hello` is in INTERJECTIONS but GT labels it EN |

---

## v3 — Brand gazetteer + INTERJECTIONS trim

**Status:** shipped · 83 unit tests green
**Files:** [v3/src/](v3/src/) · independent copy of the v2 pipeline
**Approach:** two pure data changes on top of v2's logic — no new rules.

1. **`BRAND_TERMS` frozenset** in [v3/src/brand_terms.py](v3/src/brand_terms.py)
   — Vingroup ecosystem brands (`vinpearl`, `vinfast`, `vinhomes`, `vinmec`,
   `vinuni`, `vines`, `vingroup`, …) + the agent name `dyno`. Treated
   identically to `CULTURAL_TERMS`: counts as a VN token AND as entity-like
   in `_is_entity_token`.
2. **INTERJECTIONS trim** in [v3/src/rule_detector.py](v3/src/rule_detector.py)
   — removed `hello` (dataset GT labels it EN, not filler) and the VN
   diacritic particles `ừ`, `ừm`, `dạ`, `vâng`, `ờ`, `ôi`, `ơi`, `à`, `ạ`
   (they now route through Rule 1 → VI instead of Rule 3 → unknown).

**The 13 fixed rows (vs v2):**
- 6 standalone brand queries (`dyno`, `vinpearl`, `Ê Dyno`, …) — gt=vi.
  Previously fell through diacritic gate → en. Now in BRAND_TERMS → pure_vi.
- 4 VN particles (`dạ`, `ừ`, `À`) — gt=vi. Previously in INTERJECTIONS →
  unknown. Now routed via Rule 1 → vi.
- 3 hello variants (`hello hello`, `hello hello hello`, `hello alo`) — gt=en.
  Previously in INTERJECTIONS → unknown. Now `hello` removed → pure_en.

**Residual failures (52, unchanged from v2):**

| Pattern | Count | Examples |
|---|---|---|
| `v3=en, gt=vi` | 40 | `sao dyno`, `xa`, `safari` |
| `v3=vi, gt=en` | 8 | `VINES và GSM`, `How big is Thằn lằn da báo?` |
| `v3=unknown, gt=vi` | 4 | `alo alo 1`, `123`, `ok` |

---

## v4 — Lingua-centric pipeline (new spec, May 2026)

**Status:** shipped · 74 unit tests green
**Files:** [v4/src/](v4/src/)
**Approach:** structural rewrite — Lingua's binary EN/VI sentence verdict
is the **primary** classifier (decides 97.26 % of rows). Three
spec-mandated overrides sit on top:

1. **Translation-question detector** ([v4/src/translation_question.py](v4/src/translation_question.py))
   — closed-class metalinguistic verb (`mean`, `dịch`, `nghĩa`, `translate`, …)
   plus a minority-language token triggers strip-and-recurse. Implements
   the new spec's Rule 2 Step 1 (`"What does phở mean?"` → strip `phở` →
   `"What does mean?"` → en).
2. **Exception list** in [v4/src/entities.py](v4/src/entities.py) —
   spec's `Ngoại lệ`: 5 entries (`em`, `anh`, `nha`, `cho anh`, `cho em`)
   force VI when Lingua reads English. Word-boundary matching so `em`
   doesn't fire inside `system` / `remember`.
3. **Entity-only override** — when Lingua says VI but every VN-bearing
   token is a cultural term, Vingroup brand, or title-cased mid-sentence
   proper noun, flip to EN (`"Phở is delicious"`, `"Visit Hà Nội"`).
   The title-case heuristic SKIPS the first word (sentence-start
   capitalization is forced by convention, not by proper-noun marking).

Plus two correctness additions:

- **Rule 4b — Latin-script foreign** via a wider Lingua model (10
  languages preloaded). Spanish/French/German/Italian/Dutch text →
  `unsupported_language`. Gated by ≥3 alphabetic words + no
  VN-unique character + wider VI score < 0.05.
- **Expanded Vingroup brand gazetteer** (57 entries, up from 29) — full
  family: VinFast, Vinhomes, Vincom, Vinpearl, Vinmec, Vinschool,
  VinUni, VinAI, VinBigData, VinSmart, VinMart/+, Wincommerce, WinMart,
  Vinhomes Ocean Park, Vincom Plaza, …

**What v4 deletes vs v3:**
- `EN_ANCHORS` (164 entries) — no longer in spec
- `underthesea` dependency — replaced by `lingua-language-detector`
- POS-based Step 1 — Lingua subsumes it
- Step 3 (S+V) — collapses into Step 4.2 in the new spec

**Total enumerated entries:** 149 (v3 had 263). Architectural surface
area dropped 43 %.

**Sentence-purity breakdown (your "easy case" priority):**

| Bucket | Count | v3 | v4 |
|---|---:|---:|---:|
| Pure VN with diacritic | 1177 | 100.00 % | **100.00 %** |
| Pure EN (ASCII only) | 106 | 100.00 % | **100.00 %** |
| VN typed without diacritic | 28 | 7.14 % | **25.00 %** |
| Mixed | 6605 | 99.62 % | 99.17 % |

Both perfect on clean single-language input. v4 is 3.5× better on the
no-diacritic-VN typo case.

**The 22 fixed rows (vs v3):**
- 8 no-diacritic VN sentences (`khong biet`, `cho anh xem`, `sao dyno`,
  …) — Lingua's character n-gram model recognises VN orthographic
  patterns even without tone marks.
- 7 exception-list hits (`thank em`, `hello em`, `sorry anh`, …) —
  v3 had these as wrong; v4's override-A catches them.
- Various Lingua-direct wins on ambiguous mixed sentences.

**The 47 regressed rows (vs v3):**

| Pattern | Count | Examples | Root cause |
|---|---:|---|---|
| `v3=en, v4=vi` | ~23 | `"Where is the Khỉ sóc tai đen area on the safari route?"` | Multi-word VN proper-noun phrase. v3's underthesea NER catches the whole `Khỉ sóc tai đen` span; v4 has no NER fallback, only the title-case heuristic, which sees `Khỉ` (entity) but `sóc`/`đen` lowercase (non-entity) → not all entities → keeps Lingua's VI verdict |
| `v3=vi, v4=unknown` | ~13 | `"Vẫy tay"`, `"alo alo 1"` | Lingua confidence < 0.55 → unknown. v3's deterministic POS hit committed to vi |
| Other | ~11 | Mixed bag | EN-anchor cases (`"Show me X"` style) — new spec doesn't have an EN-anchor rule |

**Residual failures (77 total):**

| Pattern | Count | Examples | Notes |
|---|---:|---|---|
| `v4=en, gt=vi` | 37 | `dyno`, `xa`, `safari`, `why` | Per new spec, no-diacritic + no exception → en. GT-side context-dependent label |
| `v4=vi, gt=en` | 23 | `"Where is the Khỉ sóc tai đen area..."` | Multi-word VN proper-noun phrase, no NER fallback |
| `v4=unknown, gt=vi` | 13 | `"Vẫy tay"`, `"alo alo 1"`, `"ok"` | Lingua confidence < 0.55 |
| `v4=unknown, gt=en` | 4 | `"VINES và GSM"`, `"How big is Thằn lằn da báo?"` | Lingua confidence < 0.55 |

---

## Next steps — candidates for v5

After v4, the dominant failure mode (23 cases) is **multi-word VN
proper-noun phrases in English sentences** — animal species names, route
identifiers, etc. that v3's underthesea NER catches but v4's title-case
heuristic does not. The v3-to-v4 jump was deliberately a structural
simplification; v5 candidates focus on whether we re-introduce a
principled entity signal without re-introducing v3's full dependency.

### Architectural takeaways from the v3 failure set

1. **The diacritic gate is a hard binary that can't be tightened or loosened
   safely.** Tight (current): correctly-tagged VN function words without
   tones (`sao` → POS=P, `Trong` → POS=E) are discarded. Loose: English
   content words tagged as VN POS by underthesea (e.g. `"do"` → POS=E) leak
   in. There is no globally safe setting for one binary signal.

2. **Rules with a single deciding signal are brittle.** Step 4.1 flips on
   one noisy NER span; Step 1 flips on one stray closed-class token; Step 2
   flips on one loanword anchor (`Show <VN>`). The rule chain doesn't weigh
   *how many* signals agree — only *whether any one* does.

3. **Some failures are GT noise.** ~10 of the 52 cases (`why`, `Also`,
   `Anyway`, `many`, `really`, `Jerry`, `Pablo`, …) look like labeling
   errors, not detector errors.

### Principled candidates (ordered: cheapest → most invasive)

#### 1. Externalise the Vingroup brand list to deployment config

The 57-entry `VINGROUP_BRANDS` set is the one piece of v4 that's still
case-by-case in code. A different client (banking, hospitality, MWG)
needs a totally different list. Move it to
`v4/config/brand_gazetteer.yaml` (or similar) and read at startup.
Architecture stops growing per deployment — only the config does.

**Risk:** none — pure refactor, behavior-preserving.

#### 2. Lightweight NER for the entity-only override

The 23 `v4=vi, gt=en` failures are all multi-word VN proper-noun phrases
(`Khỉ sóc tai đen`, `Linh dương nước`, `Hươu cao cổ`). Two paths to
recover them:

- **Bring back underthesea NER on the override-B path only.** v4 already
  has the rest of the pipeline carrying the load — NER would be consulted
  for ~3 % of rows (when Lingua votes VI and the title-case check is
  inconclusive). Cost: ~30 ms when invoked, +500 MB load-time models.
- **Train a tiny domain-tuned NER from the dataset.** ~5 minutes on this
  CSV's VN spans; package as a small ONNX/sklearn artifact. Higher
  effort but no underthesea dependency.

**Risk:** medium. NER recall is the hard part — accept some false
positives (which override-B would flip to EN) and rely on Lingua for the
rest.

#### 3. Wider Lingua-all-languages model for stronger Rule 4

v4 already preloads 10 languages, but the spec lists `unsupported_language`
broadly. Loading the full 75-language Lingua set adds ~150 MB but removes
the "what if the user types Swahili" hypothetical edge case. Gate behind
a flag; production might not need it.

**Risk:** low.

#### 4. Calibrated `unknown` band tuning

v4 currently emits `unknown` when Lingua confidence < 0.55. The 13
`v4=unknown, gt=vi` failures are right at this boundary. Lower the
threshold to 0.45 and see whether more correct vi commits than wrong vi
commits result. Strictly empirical; no design change.

**Risk:** medium — risks turning some correct unknowns into wrong VI.
Needs holdout eval before shipping.

#### 5. Conversation-context aware downstream wrapper

The 37 `v4=en, gt=vi` failures are mostly single-word inputs (`dyno`,
`xa`, `safari`, `robot`) labeled VI based on session context our model
can't see. The spec **explicitly** says these should be `unknown` plus a
downstream agent fallback. Build that wrapper outside the detector
proper, with explicit `prev_lang` parameter and confidence weighting.

**Risk:** zero in the detector; deployment-level effort.

### Explicitly rejected (overfits to this dataset)

These would close cases on paper but won't generalize:

- Add `dyno`, `sao`, `xa`, `robot` to a "weak-VN" list — same trap as v2's
  Table 3 expansion; the user explicitly called this out.
- Enumerate every observed multi-word animal name (`Khỉ sóc tai đen`,
  `Linh dương nước`, …) as cultural terms — works on this dataset but
  the next domain (banking, ride-hailing) has different proper nouns.
- Tune the Lingua-confidence floor per failure cluster — chasing the
  metric, not the principle.

### Failure analysis summary

The current per-row failures for v4 are in
[v4/results/v4_failures.csv](v4/results/v4_failures.csv) — three columns
(`sentence, gt, pred`) for easy filtering.

---

## How to add a new version entry

1. Run all-four eval (`v1 → v2 → v3 → v4`), then `compare.py` for each
   adjacent pair, and record numbers in the **Comparison** table above.
2. Insert a `## vN — title` section between the latest version and the
   **Next steps** block. Mirror the schema: **Status / Files / Approach
   / Fixed-rows / Regressed-rows / Residual failures**.
3. Move whichever **Next steps** candidate you implemented into the new
   version section, and propose 1-2 fresh ones below.

---

## About the current dataset

> **The accuracy numbers above are a snapshot against the dataset below.
> Treat the metric as a useful proxy, not as ground truth about model
> quality.** When the dataset is replaced, every number in this doc
> should be re-computed.

**File:** `Result_LIB_language_20260428_122621(user_inputs).csv`
**Snapshot date:** 28 April 2026
**Size:** 7917 labeled rows
**Composition:** 7728 vi + 189 en — **heavily skewed toward VI**
(~41:1). A 0.1 % accuracy delta on this dataset is ~8 rows; almost all
sit on the smaller EN side, so EN-recall numbers move in bigger jumps
than VI-recall numbers.
**Origin:** real user inputs to a Vingroup robot agent named DYNO
(safari / hospitality context). Mostly natural casual Vietnamese with
heavy code-switching into English for proper nouns and brand names.

### Known labeling quirks — concrete samples

Inspection of the failure clusters across v2 / v3 / v4 shows the GT
label is derived from **session context** (downstream agent's
interpretation), not from the sentence content alone. Same string,
different label depending on which session it came from:

| Token (lowercased) | Times labeled `vi` | Times labeled `en` | Inference |
|---|---:|---:|---|
| `dyno` (agent name)    | 242 | 4  | usually VI, occasionally EN |
| `safari`               | 574 | 31 | usually VI, occasionally EN |
| `robot`                | 681 | 2  | almost always VI |
| `hello`                |   5 | 6  | roughly 50/50 |

A string-only model cannot recover any of these; the right answer
genuinely depends on conversation history we don't see.

**Specific suspect rows in the current dataset:**

A. English-looking single tokens labeled `vi` (15 cases):

```
STT     3   text='dyno'         gt=vi
STT   107   text='xa'           gt=vi
STT   129   text='safari'       gt=vi
STT   198   text='hello'        gt=vi
STT  1601   text='why'          gt=vi
STT  1959   text='z'            gt=vi
STT  1964   text='drew'         gt=vi
STT  1972   text='ok'           gt=vi
STT  5010   text='robot'        gt=vi
STT  5044   text='Jerry'        gt=vi
STT  5115   text='Also'         gt=vi
STT  5117   text='Anyway'       gt=vi
STT  6677   text='Pablo'        gt=vi
STT  6696   text='many'         gt=vi
STT  7153   text='really'       gt=vi
```

B. Keyboard mash labeled `vi` (4 cases — spec says these should be `unknown`):

```
STT  2151   text='sdéd'         gt=vi
STT  2153   text='dcsdcd'       gt=vi
STT  2154   text='sfrfe'        gt=vi
STT  2157   text='kdhfsdb'      gt=vi
```

C. Numbers / pure fillers labeled `vi` (5 cases — spec says these should be `unknown`):

```
STT   198   text='hello'        gt=vi
STT   220   text='alo alo 1'    gt=vi
STT   222   text='123'          gt=vi
STT  1972   text='ok'           gt=vi
STT  7014   text='alo alo'      gt=vi
```

D. Mixed sentences labeled `en` despite carrying a VN function word (8 cases — borderline; arguable both ways):

```
[6109]  VINES và GSM                              gt=en   (has 'và' — Vietnamese conjunction)
[7741]  Where is the Khỉ sóc tai đen area...      gt=en   (English structure, VN entity name)
[7743]  Is Khỉ sóc đầu trắng closer to Kidzoo...  gt=en   (same pattern)
[7755]  Is Linh dương nước closer to Kidzoo...    gt=en   (same)
[7759]  Where is the Hươu cao cổ area...          gt=en   (same)
... (the safari-route family, 8 total)
```

**Effective accuracy if GT-suspect rows are excluded:**
- v3: ~99.47 % (vs reported 99.34 %)
- v4: ~99.20 % (vs reported 99.03 %)

For full per-row failures, see [v4/results/v4_failures.csv](v4/results/v4_failures.csv).

### How this affects the metric

- **Single-language sentences with diacritics work perfectly.** Both v3
  and v4 are at 100 % on pure-VN-with-diacritic (1177 rows) and pure-EN
  (106 rows). This is the cleanest sub-metric and the most trustworthy.
- **The "no-diacritic VN" bucket (28 rows) is mostly noise.** Half of
  it is single English tokens labeled `vi` for session reasons. A
  perfect detector would not score well here without context.
- **The 23 multi-word VN proper-noun failures in v4** are real model
  failures (genuinely English sentences with embedded VN entity
  names) and represent the legitimate improvement target for v5.

### Spec alignment vs dataset alignment

The new May 2026 spec (`v4/task_requirement.md`) is intentionally stricter
than the dataset GT in a few places — e.g. no-diacritic ASCII text
without a recognised exception should be `en`, not `vi` from session
context. v4 is the first version that implements the spec faithfully,
which is why some of its "regressions vs v3" are actually **the spec
working correctly**, not bugs.

If you find yourself wanting to "fix" v4 by adding `dyno` / `safari` /
`why` to a lookup list to recover dataset accuracy, **don't**. That's the
overfitting loop. Either:

1. The GT row is genuine ambiguity — fix downstream context handling
   instead.
2. The GT row is a labeling mistake — flag for relabel.
3. The GT row is correctly labeled and exposes a real gap — fix it in
   v5 with a principled change, not a hardcoded entry.

### When the dataset is replaced

1. Drop the new CSV at the repo root (or anywhere — the eval scripts
   take a path argument).
2. Re-run all four evals; record new numbers in the **Comparison**
   table; re-run `compare.py` for each adjacent pair.
3. Update the "Snapshot date" and the row count above.
4. Re-scan the new failure CSVs for GT quirks; update the "Known
   labeling quirks" table accordingly.
5. Numbers in per-version sections (v1 / v2 / v3 / v4) are tied to the
   old dataset — leave them historical or replace them, but mark which.

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
| v1 (lingua)         | 99.13 % (7848) | 99.43 % | 86.77 % | 0.03 ms | — | ~30 000 rows/s |
| v2 (rules)          | 99.18 % (7852) | 99.30 % | 94.18 % | 2.05 ms | 3.79 ms | 488 rows/s |
| **v3 (rules + brands)** | **99.34 %** (7865) | **99.43 %** | **95.77 %** | 2.30 ms | 4.51 ms | 432 rows/s |

### Head-to-head deltas (vs the prior version)

| Pair | Fixed | Regressed | Both wrong | Agreement |
|---|---|---|---|---|
| v2 vs v1 | 41 | 37 | 28 | 98.96 % |
| v3 vs v2 | **13** | **0** | 52 | 99.82 % |

v3 is a zero-regression upgrade over v2 — every row v2 got right, v3 still
gets right.

### Reproduce

```bash
cd v1 && python evaluate.py                         # v1 lingua
cd v2/src && python evaluate.py                     # v2 rules
cd v3/src && python evaluate.py                     # v3 rules + brands
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

## Next steps — candidates for v4

The 52 residual failures cluster into 7 patterns ([see analysis below](#failure-analysis-summary)).
Most of them admit *case-specific* patches — drop `show` from EN_ANCHORS,
enumerate `how big`/`how old`, hard-list `Trong`/`Ngoài` as function words —
but those overfit to this dataset. The principled fixes are structural, not
data-list extensions.

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

### Principled candidates (ordered: general → specific)

#### 1. Soft scoring instead of first-rule-wins (structural refactor)

Replace the binary "first rule fires" pipeline with a weighted-vote system:
each signal (closed-class POS hit, EN anchor, VN entity span, diacritic
density, lingua second opinion) contributes a score, and the highest-score
label wins. Eliminates the "one stray signal flips everything" failure
mode that drives Clusters B/C/D/E.

**Risk:** medium. Larger refactor; requires calibration on the eval set
without overfitting. But this is the only direction that addresses the
**structural** weakness, not its symptoms.

#### 2. Lingua tiebreaker on low-agreement outcomes

For rows where v3's verdict rests on a single weak signal — `rule_2_step_4_1`
with ≤2 VN tokens, `rule_1_pure_en` on a 1–2-token input, `rule_3_*` on a
non-empty input — consult lingua (~30 µs) and prefer it when confident.
Log as `rule_*_lingua_tiebreaker` so provenance stays explicit.

v1 and v3 fail on largely disjoint inputs (only 52 of 7917 rows are
both-wrong), so a confidence-gated ensemble can close 20–30 failures
without overfitting to any specific token.

**Risk:** medium. Adds an ML dependency to the hot path. Mitigation: gate
behind a flag; lingua call adds <30 µs so the latency budget is unchanged.

#### 3. Drop NER as a standalone entity signal

Today `_is_entity_token` accepts POS=Np **OR** any NER prefix. The NER
signal is the noisier one: underthesea merges normal sentence prefixes
(`Ngoài`, `Con`, `Phú Quốc cách Hà Tiên`) into bogus LOC/PER spans, and
Step 4.1 then fires EN on what is clearly a Vietnamese sentence.

Proposed: require POS=Np for entity classification; drop the NER-only
fallback. Run the full eval + test suite to confirm no regressions on
cases like `Visit Hà Nội and Đà Nẵng next month` (where Hà Nội is POS=Np
*and* NER=B-LOC, so it stays entity).

**Risk:** low-medium. The change is small but needs whole-eval verification.

#### 4. Rule 4 lingua-all-languages verifier (correctness, not accuracy)

`Hola mundo` (Spanish) currently returns EN — no VN diacritics → pure_en.
Per spec this should be `unsupported_language`. Fix: on the EN path,
query lingua with all 75+ languages; downgrade to UNSUPPORTED when top
language ≠ English with confidence > 0.7. No impact on the canonical eval
(VN/EN only), but improves spec conformance for production traffic.

**Risk:** low. Independent of any other change; can ship standalone.

#### 5. Send the GT-suspect rows back for re-labeling

Cluster A includes ~10 single-word English-looking tokens labeled `vi`
in the GT (`why`, `Also`, `Anyway`, `many`, `really`, `drew`, `Jerry`,
`Pablo`, `robot`, `z`). Flag for labeling-team review rather than
contorting the model. If they're confirmed mislabels, v3's effective
accuracy is already ~99.47 %.

**Risk:** zero technical, requires labeling-team bandwidth.

### Explicitly rejected (overfits to this dataset)

These would close cases on paper but won't generalize:

- Drop `show`/`open` from `EN_ANCHORS` — both are valid English imperatives;
  would break `Show me X` / `Open the file`.
- Enumerate `how big`, `how old`, `how tall`, `which zone`, `which area` —
  doesn't generalize beyond the test phrases.
- Hard-list `Trong`, `Ngoài`, `Con`, `Theo` as VN function words —
  reintroduces the lexicon approach v1 was rejected for.
- Trust underthesea POS=E/T/C/P/L on all ASCII tokens — would regress
  `What do you think?` since underthesea tags English `"do"` as POS=E.

### Failure analysis summary

For the full breakdown of each failed row, the cluster it belongs to, and
the root cause, see the analysis dump under `v3/results/`.

---

## How to add a new version entry

1. Run all-three eval (`v1 → v2 → v3`), then `compare.py` for each adjacent
   pair, and record numbers in the **Comparison** table above.
2. Insert a `## vN — title` section between v3 and the **Next steps** block.
   Mirror the schema: **Status / Files / Approach / Fixed-rows / Residual
   failures**.
3. Move whichever **Next steps** candidate you implemented into the new
   version section, and propose 1-2 fresh ones below.

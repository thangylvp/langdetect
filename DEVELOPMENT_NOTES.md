# Development notes — picking up where we left off

> Audience: future-me on a different machine (or another Claude session)
> reading this cold. Everything you need to keep iterating on the v2
> rule-based detector is captured below. Read top-to-bottom once before
> touching code.

---

## 1. What this repo is

A Vietnamese / English language detector for a conversational-AI gateway
("DYNO" / robot agent). Lives in two parallel implementations:

- **v1** — top-level `detector.py`, `service.py`, `router.py`, `schemas.py`.
  Wraps `lingua-language-detector` and FastText (`lid.176.ftz`) with a single
  confidence threshold. The original production code; still importable.

- **v2** — `v2/src/`. Rule-based pipeline implementing the 4 quy tắc from
  `v2/task_requirement.md`. Uses `underthesea` (Vietnamese NLP toolkit) for
  POS + NER on the *content* tokens, not as a black-box classifier.

Everything below is about v2.

---

## 2. The spec, in one paragraph

A sentence is one of `vi`, `en`, `unknown`, or `unsupported_language`.
The decision pipeline (in order, first match wins):

1. **Rule 4** — script-based: if the sentence is dominantly non-Latin
   (Korean, Han, Arabic, Cyrillic, …) → `unsupported_language`.
2. **Rule 3** — interjection / number / filler only (`ok`, `wow`, `alo`,
   `123`, empty) → `unknown` with confidence < 0.6.
3. **Rule 1** — pure language: zero VN tokens → `en`; zero EN tokens → `vi`.
4. **Rule 2** — mixed sentence, 4 sub-steps **in strict order**:
   - **Step 1** — any Vietnamese function word (giới từ / trợ từ / hư từ /
     đại từ / động-trạng từ thuần Việt) → `vi`.
   - **Step 2** — sentence STARTS with an English grammar anchor
     (Wh-question / auxiliary / imperative — Phụ lục A Bảng 4) → `en`.
   - **Step 3** — Vietnamese Subject + Vietnamese Verb structure → `vi`.
   - **Step 4.1** — every Vietnamese token is a proper noun / cultural term
     (Phụ lục A Bảng 1) → `en`.
   - **Step 4.2** — at least one Vietnamese token is a common noun /
     verb / adjective / adverb → `vi`.

Reference tables are in `v2/phuluc.md`. The full spec — including examples,
downstream-fallback advice for `unknown`, and the consequence table — is in
`v2/task_requirement.md`.

---

## 3. Key implementation decisions (the ones that took the most thinking)

These choices are NOT obvious from the code. If you forget the rationale you
will be tempted to "fix" them and regress accuracy. Read carefully.

### 3.1 No big VN lexicon

The first design used a hand-transcribed Table 3 (~150 entries) + Table 2
(open-ended common nouns) as a lookup. The user rejected this:

> "I think we can't find every word like this. He will definitely miss a word.
> Is there any solution that avoid using a fix dictionary like this?"

The pivot was to use **`underthesea`** as the Vietnamese POS/NER engine
because the spec is literally written in POS categories
(*giới từ* = preposition, *động từ* = verb, *danh từ phổ thông* = common
noun, etc.). POS tagging is the right primitive.

What's still a lexicon:
- `en_anchors.py` — Phụ lục A Bảng 4. Bounded by English grammar (Wh-,
  auxiliaries, imperatives, polite openers). ~150 entries. **Stable.**
- `cultural_terms.py` — ~35 VN cultural common-nouns underthesea mis-tags
  as `POS=N` instead of `Np` (Phở, Áo Dài, Tết, …). Bounded by reality —
  there are only so many famous Vietnamese foods/garments. **Stable.**

No other lexicons. Tables 2 and 3 are derived dynamically from POS tags.

### 3.2 The diacritic gate

`underthesea` cannot tell English from Vietnamese on its own — it assumes
its input is Vietnamese. Probing it on `"What do you think?"` returned
`('do', 'E')` — tagging the English auxiliary as a Vietnamese preposition.
On `"안녕하세요"` it returned `('안녕하세요', 'M')` — a Korean greeting as a
"numeral". So we cannot trust underthesea on tokens it shouldn't be looking
at.

**Fix**: a token is considered "Vietnamese" only when:

- It contains a Vietnamese diacritical character (`ă â đ ê ô ơ ư` + tone
  marks), OR
- It appears in our `CULTURAL_TERMS` list.

Otherwise it's English (ASCII alphabetic) or "other" (numbers, punctuation,
non-Latin). **POS tags are only consulted on VN-diacritic tokens.** This
fully sidesteps underthesea's hallucinations on mixed-language input.

### 3.3 Step 1 only fires on CLOSED-CLASS POS

The spec's Step 1 includes "động từ / trạng từ thuần Việt" (native VN verbs
and adverbs). The temptation is to fire Step 1 on POS=V/R. **Don't.**

Probing `"Is Voi châu Á dangerous?"` (which the spec wants → `en` via
Step 2), underthesea tokenizes and tags it as:
```
[('Is', 'Np'), ('Voi', 'Np'), ('châu Á', 'V'), ('dangerous', 'N')]
```
"châu Á" (the continent Asia) is wrongly POS-tagged as a verb. If Step 1
fires on V, we get → `vi`. Wrong.

**Fix**: Step 1 fires only when a VN-diacritic token has POS in
`{E, T, C, Cb, Cc, P, L}` — the **closed-class** function-word tags
(preposition, particle, conjunction, modal, coord/subord conjunction,
pronoun, determiner). These are short, stable categories with few false
positives.

Open-class VN content words (verbs, adjectives, adverbs, common nouns)
are routed to **Step 4.2** instead. The spec outcomes are identical
(Step 1 → vi, Step 4.2 → vi), but the failure mode is much friendlier:
a misclassified verb just falls through one more step rather than
incorrectly firing Step 1.

### 3.4 Step 3 collapsed into Step 4.2

The spec separates "VN Subject + VN Verb structure" (Step 3) from "any VN
common noun present" (Step 4.2). In every input that satisfies Step 3,
Step 4.2 also fires (the subject IS a non-entity VN word). The outcomes
are identical. Implementing Step 3 explicitly would require a Vietnamese
dependency parser — overkill and brittle. So we collapsed them.

### 3.5 Spec ordering: Step 2 wins over Step 4

The consequence table row 4 says "VN common noun with English equivalent
→ vi". But the step ordering says Step 2 (English anchor at start) is
checked **before** Step 4 (noun analysis). When both could fire, Step 2
wins.

Example: `"Update thông tin user"`:
- Step 1: no function word, skip.
- Step 2: `"Update"` is an imperative anchor in Table 4 → `en`.
- (Step 4.2 would have fired on `"thông tin"` if Step 2 hadn't.)

This is **intentional** per spec ordering and covered by the test
`test_step_2_beats_step_4_by_ordering` in `test_rule_detector.py`. If you
change it, document why.

---

## 4. File map

```
langdetect/
├── README.md                        ← project overview
├── DEVELOPMENT_NOTES.md             ← (this file)
├── CLAUDE.md                        ← v1 architecture brief
├── .gitignore
├── Result_LIB_language_*.csv        ← labelled eval dataset (7917 rows)
│
├── detector.py                      ← v1: Lingua + FastText wrappers
├── service.py                       ← v1: lru_cache singletons
├── schemas.py                       ← v1: Pydantic models
├── router.py                        ← v1: FastAPI endpoint
├── __init__.py                      ← v1 package marker
├── models/lid.176.ftz               ← FastText 176-language model
│
├── v1/                              ← (empty placeholder for future move)
└── v2/
    ├── phuluc.md                    ← Phụ lục A: Bảng 1–4 reference
    ├── task_requirement.md          ← spec: Quy tắc 1–4 + consequence table
    ├── src/
    │   ├── __init__.py
    │   ├── rule_detector.py         ← main pipeline (~250 lines)
    │   ├── cultural_terms.py        ← ~35 VN cultural common nouns
    │   ├── en_anchors.py            ← Table 4 (~150 stable entries)
    │   ├── test_rule_detector.py    ← 64 cases, all green
    │   └── evaluate.py              ← CSV-driven harness
    └── results/                     ← eval output CSVs (timestamped)
```

---

## 5. How to run things

```bash
# Setup (Python 3.11, conda env named "langdetect")
pip install underthesea pytest

# Unit tests — should all pass
cd v2/src
python -m pytest test_rule_detector.py -v          # 64 tests

# Full evaluation against labelled CSV
python evaluate.py                                  # default input + output
python evaluate.py path/to/my_test.csv              # custom input
python evaluate.py my_test.csv -o my_results.csv    # custom output

# Quick sanity check
python -c "from rule_detector import detect; print(detect('Show me status của project Vision'))"
```

The eval script auto-detects column names. Input column can be any of:
`VA_SAMPLE / input / text / sentence / query / utterance`. Ground truth can be:
`GT_language / ground_truth / gt / label / expected`. Output CSV preserves all
input columns and adds: `detected_language, confidence, rule, evidence,
processing_time_ms, verify_result, verify_note, error_message`.

---

## 6. Current accuracy (most recent eval)

7917 rows from `Result_LIB_language_*.csv`:

| Metric | Value |
|---|---|
| Overall accuracy | **99.18 %** (7852 PASS) |
| VI recall | 99.30 % (7674 / 7728) |
| EN recall | 94.18 % (178 / 189) |
| Wall clock | 13 s (607 rows/s) |

### Rule fire distribution

```
rule_2_step_1          60.3 %   (function word match)
rule_1_pure_vi         23.7 %   (no EN tokens detected)
rule_2_step_4_2        13.0 %   (VN common noun)
rule_1_pure_en          1.6 %   (no VN tokens detected)
rule_2_step_2           1.1 %   (EN anchor at start)
rule_2_step_4_1         0.2 %   (all VN tokens entity)
rule_3_interjection     0.1 %   (only fillers)
rule_3_empty            0.0 %
```

### 65 failures — clusters and next steps

| Pattern | Count | Example | Cause | Suggested fix |
|---|---|---|---|---|
| `vi → en` | 45 | `"dyno"`, `"sao dyno"`, `"xa"` | No-diacritic VN words slip past the diacritic gate | Lookup a VN vocab (underthesea has one) for short single/two-word inputs; or use Lingua per-token language scoring as a fallback |
| `vi → unknown` | 9 | `"hello"`, `"alo alo 1"`, `"123"` | Genuine ambiguity; GT probably came from session context | Acceptable — spec Rule 3 explicitly says downstream should use conversation context |
| `en → vi` | 8 | `"hey dyno đi"`, `"VINES và GSM"`, `"How big is Thằn lằn da báo?"` | One stray VN function word flips Step 1; or Step 2 doesn't beat a wrongly-fired Step 1 | Add a "strong VN context" precondition to Step 1 (e.g. require ≥ 2 VN content tokens OR a multi-word phrase, not just one stray particle) |
| `en → unknown` | 3 | `"hello"`, `"hello hello"` | `hello` is in our interjection list | Remove `hello` from `INTERJECTIONS` if GT consistently labels it `en` |

These are the natural targets for the next iteration.

---

## 7. Spec-level open questions worth re-checking with the user

1. **Latin-script foreign languages** — `"Hola mundo"` (Spanish) currently
   returns `en` (no VN diacritics → Rule 1 → en) but should be
   `unsupported_language` per Rule 4. Needs a Lingua-all-languages verifier
   on the EN path. **Not yet implemented.**
2. **Step 1 strength** — should one stray VN particle (e.g. `"đi"` in
   `"hey dyno đi"`) really flip the whole sentence to `vi`? Spec literally
   says "ít nhất một" (at least one), but real data suggests this is
   over-aggressive on EN-structured sentences with a single VN token.
3. **`"hello"` and similar greetings** — should they be `unknown` (current),
   `en`, or context-dependent? The labelled CSV has them as `en` (GT).

---

## 8. Conversation history highlights (what was tried and rejected)

For each major design choice, what we tried first, why it failed, and what
we landed on.

### Lexicon approach (REJECTED)
First attempt: transcribe Phụ lục A Bảng 3 fully (~150 function words +
verbs + adverbs) into `lexicons.py`. User rejected because Table 2 is
explicitly open-ended ("every common Vietnamese noun with an English
equivalent") and Table 3 would inevitably miss words. Pivoted to
underthesea.

### LLM-classifier approach (NOT CHOSEN)
Considered sending each sentence to Claude Haiku with the rules in the
system prompt. Highest theoretical accuracy but ~500 ms/call and API
dependency. Tabled in favor of underthesea (~2 ms/call) given the latency
budget of a robot agent.

### Lingua per-token approach (NOT CHOSEN)
Considered scoring each token's language individually with Lingua. Loses
POS information — can't tell verb from common noun, so Step 4.1 vs 4.2
becomes guesswork. Tabled.

### Naive POS-on-everything approach (TRIED, BROKEN)
First underthesea attempt fed the raw sentence to `pos_tag()`. Underthesea
applied VN POS to English/foreign tokens (`"do" → E`, `"안녕하세요" → M`).
**Lesson** — always filter to "definitely VN" tokens (diacritic gate)
before consulting POS.

### Diacritic + closed-class POS approach (LANDED)
Current implementation. Get all four spec examples right with no false
positives across 7917 real rows. See `rule_detector.py`.

---

## 9. What I'd do next if I had another hour

1. **Add a Vietnamese vocab fallback for the diacritic gate.** Pull
   underthesea's word list (or a minimal stopword/function-word subset)
   so `"sao"`, `"xa"`, `"dyno"` get classified as VN when they actually
   are. Carefully — must not start firing on `"do"` in `"What do you mean"`.

2. **Implement the Rule 4 Lingua verifier.** When Rule 1 says EN, run the
   text through a Lingua instance with all languages loaded. If top
   language is not EN with confidence > 0.7, downgrade to
   `unsupported_language`. This catches `"Hola mundo"`.

3. **Strengthen Step 1 precondition.** Either:
   - require ≥ 2 VN content tokens, OR
   - require a multi-word VN phrase, OR
   - exclude single-token sentences where the VN word is at the end
     (interjection-like position, e.g. `"hey dyno đi"`).

   Validate against the 8 `en → vi` failures in the latest eval.

4. **Tighten `INTERJECTIONS`.** Check the labelled CSV — if GT consistently
   labels `"hello"` etc. as `en`, remove them from the interjection list.

5. **Track regressions.** Save the latest eval CSV as a baseline; future
   PRs should diff PASS/FAIL counts against it.

Have fun.

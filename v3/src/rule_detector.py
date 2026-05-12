"""Rule-based EN/VI language detector — v3.

Diff vs v2:

  • New: `brand_terms.BRAND_TERMS` — Vingroup ecosystem brands ("vinpearl",
    "vinfast", "dyno", …) are treated like cultural terms: they count as
    Vietnamese tokens *and* as entity-like in Rule 2 / Step 4.1.
    Fixes the regression where standalone brand queries ("vinpearl") labeled
    EN despite dataset GT = VI.

  • Tightened INTERJECTIONS: removed "hello" (dataset GT consistently labels
    it EN, not unknown) and the diacritic Vietnamese particles "ừ", "ừm",
    "dạ", "vâng", "ờ", "ôi", "ơi", "à", "ạ" (they now route through Rule 1
    pure_vi instead of Rule 3 unknown).

Everything else is identical to v2. See v2's docstring + DEVELOPMENT_NOTES.md
for the full pipeline rationale.

The 4-rule pipeline (unchanged from v2):

    Rule 4  (script)       — non-Latin dominant       → unsupported_language
    Rule 3  (filler)       — empty / interjection     → unknown
    Rule 1  (pure)         — only-VN or only-EN       → vi / en
    Rule 2  (mixed)        — code-switched sentence:
        Step 1  any VN token is a closed-class function word (POS ∈ E,T,C,P,L)
                                                       → vi
        Step 2  sentence starts with English anchor    → en
        Step 4.1  all VN tokens are entity-like        → en
        Step 4.2  any VN token is an open-class word   → vi
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from underthesea import ner

from brand_terms import BRAND_TERMS
from cultural_terms import CULTURAL_TERMS
from en_anchors import EN_ANCHORS


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------

class Label(str, Enum):
    EN = "en"
    VI = "vi"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported_language"


@dataclass(frozen=True)
class DetectionResult:
    label: Label
    confidence: float
    rule: str               # e.g. "rule_2_step_1"
    evidence: dict          # explainability — which tokens fired the rule

    def __repr__(self) -> str:
        return (f"DetectionResult(label={self.label.value!r}, "
                f"confidence={self.confidence:.2f}, rule={self.rule!r}, "
                f"evidence={self.evidence!r})")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLOSED_CLASS_VN_POS = frozenset({"E", "T", "C", "Cb", "Cc", "P", "L"})

VI_DIACRITICS = frozenset(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)

# Tokens that carry no language signal and trigger Rule 3 (unknown).
# Trimmed from v2:
#   - removed "hello" (dataset GT labels it EN, not filler)
#   - removed VN diacritic particles ("ừ", "dạ", "vâng", "ờ", "ôi", "ơi",
#     "à", "ạ", "ừm") so they route through Rule 1 → VI instead of unknown.
INTERJECTIONS = frozenset({
    "ok", "okay", "okie", "k", "kk", "okk",
    "oh", "ah", "uh", "um", "umm", "mm", "hmm", "hm", "huh",
    "wow", "woah", "whoa",
    "alo", "hi", "hey", "bye",
    "ukm", "uhm",
    "haha", "hehe", "lol", "lmao", "rofl",
    "yes", "no", "yep", "nope", "yeah", "ya",
})

NER_ENTITY_PREFIXES = ("B-PER", "I-PER", "B-LOC", "I-LOC",
                       "B-ORG", "I-ORG", "B-MISC", "I-MISC")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_vn_diacritics(token: str) -> bool:
    return any(c in VI_DIACRITICS for c in token)


def detect_script(text: str) -> str:
    counts: dict[str, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        cp = ord(ch)
        if (0x0000 <= cp <= 0x024F) or (0x1E00 <= cp <= 0x1EFF):
            key = "latin"
        elif 0xAC00 <= cp <= 0xD7AF:
            key = "hangul"
        elif (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF):
            key = "han"
        elif 0x3040 <= cp <= 0x30FF:
            key = "kana"
        elif (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F):
            key = "arabic"
        elif 0x0400 <= cp <= 0x04FF:
            key = "cyrillic"
        elif 0x0900 <= cp <= 0x097F:
            key = "devanagari"
        elif 0x0E00 <= cp <= 0x0E7F:
            key = "thai"
        else:
            key = "other"
        counts[key] = counts.get(key, 0) + 1

    total = sum(counts.values())
    if total == 0:
        return "empty"
    non_latin = total - counts.get("latin", 0)
    if non_latin / total > 0.3:
        non_latin_counts = {k: v for k, v in counts.items() if k != "latin"}
        return max(non_latin_counts, key=non_latin_counts.get)
    return "latin"


def starts_with_en_anchor(text: str) -> Optional[str]:
    norm = text.strip().lower()
    for anchor in EN_ANCHORS:
        if norm.startswith(anchor):
            after = norm[len(anchor):]
            if not after or not (after[0].isalpha() or after[0] in "'"):
                return anchor
    return None


_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+", flags=re.UNICODE)


def is_interjection_only(text: str) -> bool:
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return True
    for t in tokens:
        if t.isdigit():
            continue
        if t.lower() in INTERJECTIONS:
            continue
        return False
    return True


def _is_entity_token(token: str, pos: str, ner_tag: str) -> bool:
    """A VN token counts as 'entity-like' (Step 4.1) if any of:
      - underthesea POS tagged it as Np (proper noun)
      - underthesea NER marked it as part of a PER/LOC/ORG/MISC span
      - it appears in CULTURAL_TERMS or BRAND_TERMS
    """
    if pos == "Np":
        return True
    if any(ner_tag.startswith(p) for p in NER_ENTITY_PREFIXES):
        return True
    tok_lower = token.lower()
    if tok_lower in CULTURAL_TERMS or tok_lower in BRAND_TERMS:
        return True
    return False


def _is_vn_token(token: str) -> bool:
    """v3 VN-ness gate: diacritic OR cultural term OR Vingroup brand."""
    if has_vn_diacritics(token):
        return True
    tok_lower = token.lower()
    return tok_lower in CULTURAL_TERMS or tok_lower in BRAND_TERMS


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

class RuleBasedDetector:
    """Stateless rule-based EN/VI detector. Construct once, call `detect()`."""

    def detect(self, text: str) -> DetectionResult:
        text = text or ""

        # ----- Rule 4: unsupported language by Unicode script -----
        script = detect_script(text)
        if script == "empty":
            return DetectionResult(
                Label.UNKNOWN, 0.0, "rule_3_empty",
                {"reason": "empty input"},
            )
        if script != "latin":
            return DetectionResult(
                Label.UNSUPPORTED, 0.95, "rule_4_script",
                {"detected_script": script},
            )

        # ----- Rule 3: only interjections / fillers / numbers -----
        if is_interjection_only(text):
            return DetectionResult(
                Label.UNKNOWN, 0.3, "rule_3_interjection",
                {"reason": "only interjections, numbers, or filler"},
            )

        # ----- POS + NER tagging (single underthesea call) -----
        try:
            tagged = ner(text)
        except Exception as e:                          # pragma: no cover
            return DetectionResult(
                Label.UNKNOWN, 0.0, "error",
                {"reason": f"tagger failed: {e}"},
            )

        if not tagged:
            return DetectionResult(
                Label.UNKNOWN, 0.0, "rule_3_no_tokens",
                {"reason": "no tokens after tagging"},
            )

        # ----- Classify each token as VN / EN / Other -----
        vn_tokens: list[tuple[str, str, str]] = []   # (token, pos, ner_tag)
        en_tokens: list[tuple[str, str, str]] = []
        for tok, pos, _chunk, ner_tag in tagged:
            if pos == "CH":                          # punctuation
                continue
            if _is_vn_token(tok):
                vn_tokens.append((tok, pos, ner_tag))
            elif tok.isascii() and any(c.isalpha() for c in tok):
                en_tokens.append((tok, pos, ner_tag))
            # else: numbers / abbreviations / symbols — uncounted

        # ----- Rule 1: pure language -----
        if vn_tokens and not en_tokens:
            return DetectionResult(
                Label.VI, 0.98, "rule_1_pure_vi",
                {"vn_tokens": [t[0] for t in vn_tokens]},
            )
        if en_tokens and not vn_tokens:
            return DetectionResult(
                Label.EN, 0.98, "rule_1_pure_en",
                {"en_tokens": [t[0] for t in en_tokens]},
            )
        if not vn_tokens and not en_tokens:
            return DetectionResult(
                Label.UNKNOWN, 0.0, "rule_3_no_signal",
                {"reason": "no VN and no EN content tokens"},
            )

        # ----- Rule 2 / Step 1: VN closed-class function word -----
        for tok, pos, _ner_tag in vn_tokens:
            if pos in CLOSED_CLASS_VN_POS:
                return DetectionResult(
                    Label.VI, 0.92, "rule_2_step_1",
                    {"vn_function_word": tok, "pos": pos},
                )

        # ----- Rule 2 / Step 2: English sentence-initial anchor -----
        anchor = starts_with_en_anchor(text)
        if anchor:
            return DetectionResult(
                Label.EN, 0.85, "rule_2_step_2",
                {"en_anchor": anchor},
            )

        # ----- Rule 2 / Step 4.1: all VN tokens are entity-like -----
        if all(_is_entity_token(t, p, n) for t, p, n in vn_tokens):
            return DetectionResult(
                Label.EN, 0.80, "rule_2_step_4_1",
                {"vn_entities": [t[0] for t in vn_tokens]},
            )

        # ----- Rule 2 / Step 4.2: at least one VN open-class word -----
        non_entity = [
            t for t, p, n in vn_tokens if not _is_entity_token(t, p, n)
        ]
        return DetectionResult(
            Label.VI, 0.80, "rule_2_step_4_2",
            {"vn_content_words": non_entity},
        )


_default = RuleBasedDetector()


def detect(text: str) -> DetectionResult:
    """Module-level convenience: detect using the singleton detector."""
    return _default.detect(text)

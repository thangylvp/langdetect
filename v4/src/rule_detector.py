"""v4 rule-based EN/VI detector — Lingua-centric with three deterministic
overrides (translation question, spec exception list, entity-only sentence).

Pipeline (rules fire top-down; first match wins):

    Rule 4   non-Latin Unicode script dominates              → unsupported_language
    Rule 4'  Latin script but Lingua's wider model picks a   → unsupported_language
             non-vi/en language with high confidence
    Rule 3   only interjections / numbers / empty            → unknown
    Rule 2 / Step 1  metalinguistic translation question     → strip X, recurse
    Rule 1   Lingua sentence-level verdict is the BASELINE.
             Then we apply two deterministic overrides:
                 Override A  exception list hit ('em' / 'anh' / 'nha' /
                              'cho anh' / 'cho em')           → force vi
                 Override B  Lingua says vi BUT every VN-looking token
                              is an entity / cultural / brand → force en
                              (catches "Visit Hà Nội", "Phở is delicious",
                               "Tôi học ở Vinschool" → en when appropriate)

Architectural deltas vs v3
---------------------------
  ✗ DROPPED: diacritic gate (Lingua handles no-diacritic VN)
  ✗ DROPPED: closed-class POS check for Step 1 (Lingua subsumes it)
  ✗ DROPPED: EN-anchor list (`en_anchors.py`) — not in new spec
  ✓ ADDED:   translation-question detector (spec Rule 2 Step 1)
  ✓ ADDED:   spec exception list (5 entries, frozen)
  ✓ ADDED:   Lingua wider-model verifier for Rule 4 Latin-script foreign
  ✓ EXPANDED: Vingroup brand gazetteer (vinbigdata, vinschool, vinmec, ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from entities import (
    CULTURAL_TERMS,
    VINGROUP_BRANDS,
    EXCEPTION_VN_TOKENS,
    EXCEPTION_VN_PHRASES,
)
from lingua_classifier import (
    binary_score,
    multilang_top,
    multilang_scores,
    LINGUA_CONFIDENCE_FLOOR,
)
from translation_question import (
    VI_DIACRITICS,
    detect_translation_question,
)


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
    rule: str
    evidence: dict

    def __repr__(self) -> str:
        return (f"DetectionResult(label={self.label.value!r}, "
                f"confidence={self.confidence:.2f}, rule={self.rule!r}, "
                f"evidence={self.evidence!r})")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTERJECTIONS: frozenset[str] = frozenset({
    "ok", "okay", "okie", "k", "kk", "okk",
    "oh", "ah", "uh", "um", "umm", "mm", "hmm", "hm", "huh",
    "wow", "woah", "whoa",
    "alo",
    "ukm", "uhm",
    "haha", "hehe", "lol", "lmao", "rofl",
    "yep", "nope", "ya",
    "ừ", "ừm", "ờ",
})

_WORD_RE = re.compile(r"[^\W\d_]+|\d+", flags=re.UNICODE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def has_vn_diacritics(token: str) -> bool:
    return any(c in VI_DIACRITICS for c in token)


# Characters that ONLY appear in Vietnamese — neither Spanish, French, German
# nor other Romance/Germanic Latin orthographies use them. Presence of any of
# these is strong proof the text is Vietnamese, used to short-circuit the
# Latin-foreign override (Rule 4b).
VN_UNIQUE_CHARS = frozenset(
    "đĐ"
    "ăâêôơưĂÂÊÔƠƯ"                                    # vowel modifiers used in VN
    "ằẳẵặắẰẲẴẶẮ"                                       # ă with tones
    "ầẩẫậấẦẨẪẬẤ"                                       # â with tones
    "ềểễệếỀỂỄỆẾ"                                       # ê with tones
    "ồổỗộốỒỔỖỘỐ"                                       # ô with tones
    "ờởỡợớỜỞỠỢỚ"                                       # ơ with tones
    "ừửữựứỪỬỮỰỨ"                                       # ư with tones
    "ỳỷỹỵỲỶỸỴ"                                         # y with tones
)


def _has_vn_unique_char(text: str) -> bool:
    return any(c in VN_UNIQUE_CHARS for c in text)


def detect_script(text: str) -> str:
    """Classify dominant Unicode script. Returns 'latin', 'empty', or a
    non-Latin script name when non-Latin alpha exceeds 30% of alpha chars."""
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


def is_interjection_only(text: str) -> bool:
    """True if text consists entirely of fillers, numbers, or whitespace.

    Tokens with VN diacritics do NOT count as interjections — they're a
    definite Vietnamese signal ("ừ", "ờ", "à" should classify as vi, not
    unknown, even though they're sometimes lumped with fillers).
    """
    tokens = _WORD_RE.findall(text)
    if not tokens:
        return True
    for t in tokens:
        if t.isdigit():
            continue
        if has_vn_diacritics(t):
            return False               # any VN-diacritic token → not filler
        if t.lower() in INTERJECTIONS:
            continue
        return False
    return True


def _has_exception_match(text: str) -> Optional[str]:
    """Spec 'Ngoại lệ': force vi if `text` contains any of the five entries.
    Word-boundary match so 'em' doesn't fire on 'system' / 'them' / 'remember'.
    """
    norm = text.lower()
    # Multi-word phrases first (longer match wins)
    for phrase in EXCEPTION_VN_PHRASES:
        if re.search(rf"\b{re.escape(phrase)}\b", norm):
            return phrase
    for tok in EXCEPTION_VN_TOKENS:
        if re.search(rf"\b{re.escape(tok)}\b", norm):
            return tok
    return None


def _vn_tokens(text: str) -> list[str]:
    """Pull tokens that look Vietnamese-bearing — used by the entity override.
    A token qualifies if it has a Vietnamese diacritic OR is in CULTURAL_TERMS
    (case-insensitive)."""
    out: list[str] = []
    for tok in _WORD_RE.findall(text):
        if has_vn_diacritics(tok) or tok.lower() in CULTURAL_TERMS:
            out.append(tok)
    return out


def _is_entity(token: str, text_lower: str, is_first_word: bool = False) -> bool:
    """Treat `token` as a 'danh từ riêng / cultural term' when:
      - it's in CULTURAL_TERMS, OR
      - it (or a phrase containing it) is in VINGROUP_BRANDS, OR
      - it's title-cased mid-sentence (heuristic for proper nouns we don't
        have a list for — VN names, places).

    The title-case heuristic is SKIPPED for the first word of the sentence,
    where capitalization is forced by convention and doesn't signal a
    proper noun ("Năm 2000", "Ủa", "Ngoài Phạm Nhật Vượng" → first word
    is NOT an entity).
    """
    t = token.lower()
    if t in CULTURAL_TERMS:
        return True
    if t in VINGROUP_BRANDS:
        return True
    # multi-word brand match (e.g. "Vinhomes Ocean Park")
    for brand in VINGROUP_BRANDS:
        if " " in brand and brand in text_lower:
            if t in brand.split():
                return True
    # title-cased proper-noun heuristic — skip on sentence-start tokens
    if is_first_word:
        return False
    if token[0].isupper() and not token.isupper() and len(token) > 1:
        return True
    return False


def _all_vn_tokens_are_entities(text: str) -> tuple[bool, list[str]]:
    """Returns (all_entities, vn_tokens). When VN tokens list is empty,
    `all_entities` is False — we shouldn't override an EN sentence to EN."""
    tokens = _vn_tokens(text)
    if not tokens:
        return False, []
    text_lower = text.lower()
    # Identify the first whitespace-token of the input so we can tell
    # `_is_entity` to skip its title-case heuristic.
    first_word = text.split()[0].strip(".,!?;:'\"()[]{}") if text.split() else ""
    results = [
        _is_entity(t, text_lower, is_first_word=(t == first_word))
        for t in tokens
    ]
    return all(results), tokens


def _count_alpha_words(text: str) -> int:
    return sum(1 for t in text.split() if any(c.isalpha() for c in t))


# ---------------------------------------------------------------------------
# Main detect
# ---------------------------------------------------------------------------

# A simple "is this Latin-script-foreign" check uses the multi-language Lingua
# verifier. We only consult it when the binary detector AND the script check
# both agree the input looks like Latin English — that's where Spanish/French
# slip through.
UNSUPPORTED_LATIN_LANGS = {"es", "fr", "de", "pt", "it", "nl", "id", "tl"}


def detect(text: str, _recursion_depth: int = 0) -> DetectionResult:
    text = text or ""

    # ----- Rule 4a: non-Latin script -----
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

    # ----- Rule 3: filler-only -----
    if is_interjection_only(text):
        return DetectionResult(
            Label.UNKNOWN, 0.3, "rule_3_interjection",
            {"reason": "only fillers / numbers / empty"},
        )

    # ----- Rule 2 / Step 1: translation question? -----
    # Bounded recursion: a translation question can ask about another
    # translation question, but we cap at 2 layers to avoid pathological loops.
    if _recursion_depth < 2:
        m = detect_translation_question(text)
        if m is not None:
            x, remainder = m
            inner = detect(remainder, _recursion_depth + 1)
            return DetectionResult(
                inner.label,
                inner.confidence * 0.9,  # slight discount for indirection
                f"rule_2_step_1_translation_q→{inner.rule}",
                {"stripped_X": x, "remainder": remainder,
                 "inner_evidence": inner.evidence},
            )

    # ----- Lingua sentence-level verdict (the baseline) -----
    lingua_label, lingua_conf = binary_score(text)

    # ----- Override A: spec exception list forces vi -----
    exception_hit = _has_exception_match(text)
    if exception_hit and lingua_label == "en":
        # Only override when Lingua disagrees — otherwise no-op.
        return DetectionResult(
            Label.VI, 0.70, "rule_2_exception_override",
            {"exception_match": exception_hit,
             "lingua_label": lingua_label,
             "lingua_confidence": round(lingua_conf, 3)},
        )

    # ----- Override B: entity-only override (vi → en) -----
    # If Lingua thinks the sentence is VN but every VN-looking token is a
    # known entity / cultural term / brand, the sentence is structurally
    # English with VN proper-nouns in it. ("Visit Hà Nội", "Phở is delicious")
    if lingua_label == "vi":
        all_ent, vn_toks = _all_vn_tokens_are_entities(text)
        if all_ent and vn_toks:
            return DetectionResult(
                Label.EN, 0.75, "rule_2_step_3_entity_only",
                {"vn_tokens": vn_toks,
                 "lingua_label": lingua_label,
                 "lingua_confidence": round(lingua_conf, 3)},
            )

    # ----- Rule 4b: Latin-script-but-foreign check -----
    # Spanish, French, German etc. share acute accents (á, é, ó) with Vietnamese,
    # so we can't gate on `has_vn_diacritics`. Instead, consult the wider Lingua
    # model and return unsupported only when its top language is non-EN/VI with
    # high confidence — and only when there is NO Vietnamese-UNIQUE character
    # (đ, ơ, ư, ă, ê, ô + tone-stacked vowels) in the text. Those characters
    # are essentially proof of VN.
    if not _has_vn_unique_char(text) and _count_alpha_words(text) >= 3:
        # Two gates already passed: no VN-unique character, ≥ 3 alphabetic
        # words. Now consult the wider Lingua model.
        #
        # The tricky case is text like "Predator là gì?" — VN diacritics
        # à/ì are SHARED with Italian/French, so the wider model puts
        # Italian on top (~0.77). But it ALSO keeps a non-trivial VI score
        # (~0.20). On true foreign text ("Hola mundo"), the VI score
        # collapses to near zero (~0.001). Use that as the discriminator.
        scores = multilang_scores(text)
        wider_lang, wider_conf = (
            max(scores.items(), key=lambda kv: kv[1]) if scores
            else ("en", 0.0)
        )
        wider_vi = scores.get("vi", 0.0)
        if (wider_lang in UNSUPPORTED_LATIN_LANGS
                and wider_conf > 0.6
                and wider_vi < 0.05):
            return DetectionResult(
                Label.UNSUPPORTED, wider_conf, "rule_4_latin_foreign",
                {"detected_language": wider_lang,
                 "wider_vi_score": round(wider_vi, 4),
                 "binary_label": lingua_label,
                 "binary_confidence": round(lingua_conf, 3)},
            )

    # ----- Default: Lingua's verdict, with confidence calibrated -----
    if lingua_conf < LINGUA_CONFIDENCE_FLOOR:
        # Lingua is unsure — emit unknown with sub-0.6 confidence per spec.
        return DetectionResult(
            Label.UNKNOWN, lingua_conf, "rule_3_low_confidence",
            {"lingua_label": lingua_label,
             "lingua_confidence": round(lingua_conf, 3)},
        )

    final = Label.VI if lingua_label == "vi" else Label.EN
    return DetectionResult(
        final, lingua_conf, "rule_1_or_2_lingua_baseline",
        {"lingua_label": lingua_label,
         "lingua_confidence": round(lingua_conf, 3)},
    )


# Module-level singleton convenience.
def _default_detect(text: str) -> DetectionResult:
    return detect(text)


# Backward-compat name matching v2/v3.
__all__ = ["Label", "DetectionResult", "detect"]

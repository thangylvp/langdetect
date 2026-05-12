"""Translation-/meaning-question detection (Rule 2 Step 1).

The spec adds a new Step 1: if the sentence is asking about a word's
meaning ("what does phở mean?", "dịch resilience", "X là gì"), strip the
word being asked about (X) and classify the rest.

Design principle: **closed-class verb + token-language disagreement**,
NOT a regex catalog of every possible phrasing. This keeps the
implementation small and resistant to paraphrase overfitting.

How it works
------------
A sentence is a translation/meaning question iff:

  1. It contains a token from the metalinguistic closed list
     (`mean`, `dịch`, `nghĩa`, `translate`, `define`, ...), AND
  2. There exists at least one token whose surface-language disagrees
     with the rest of the sentence's surface-language.

When both hold, the disagreeing token is "X" — the term being asked
about. We remove it and return `(X, remainder)` for the caller to
recurse on `remainder`.

Surface-language test per token (deliberately rough — Lingua does the
heavy lifting at sentence level later):

  * token contains VN diacritic  → "vi"
  * token is in EXCEPTION_VN     → "vi"
  * token is ASCII alphabetic    → "en"
  * else                         → "ambiguous"

Sentences with no metalinguistic verb OR no disagreeing token return
`None` and fall through to the rest of the pipeline.
"""

from __future__ import annotations

import re
from typing import Optional

from entities import (
    METALINGUISTIC_VERBS_EN,
    METALINGUISTIC_VERBS_VN,
    EXCEPTION_VN_TOKENS,
)

VI_DIACRITICS = frozenset(
    "ăâđêôơưĂÂĐÊÔƠƯ"
    "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    "ÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ"
)

_TOKEN_RE = re.compile(r"[^\s\W]+", flags=re.UNICODE)


def _surface_lang(token: str) -> str:
    """Cheap surface-language test for one token.

    Returns one of: 'vi' (has diacritic OR in spec exception list),
    'en' (ASCII alpha only), 'ambiguous' (everything else: numerals,
    foreign-script, symbols)."""
    if any(c in VI_DIACRITICS for c in token):
        return "vi"
    if token.lower() in EXCEPTION_VN_TOKENS:
        return "vi"
    if token.isascii() and any(c.isalpha() for c in token):
        return "en"
    return "ambiguous"


def _has_metalinguistic_verb(tokens_lower: list[str]) -> Optional[str]:
    """Return the matched metalinguistic verb / phrase, else None.

    Checks single tokens against the EN + VN sets, plus the two-word VN
    phrases that the spec lists ('giải thích', 'gọi là', 'có nghĩa').
    """
    # single-token
    for t in tokens_lower:
        if t in METALINGUISTIC_VERBS_EN or t in METALINGUISTIC_VERBS_VN:
            return t
    # multi-word VN phrases
    joined = " ".join(tokens_lower)
    for phrase in ("giải thích", "gọi là", "có nghĩa"):
        if phrase in joined:
            return phrase
    return None


def detect_translation_question(text: str) -> Optional[tuple[str, str]]:
    """If `text` is a translation/meaning question, return (X, remainder).

    `X`         — the term being asked about (verbatim substring of `text`).
    `remainder` — `text` with X removed, whitespace tidied. The caller
                  should re-classify this with the full pipeline.

    Returns None if `text` is not a translation/meaning question.
    """
    if not text or not text.strip():
        return None

    raw_tokens = _TOKEN_RE.findall(text)
    if len(raw_tokens) < 2:
        return None

    lower = [t.lower() for t in raw_tokens]

    verb = _has_metalinguistic_verb(lower)
    if verb is None:
        return None

    # Classify each non-verb, non-stopword token by surface language
    surface = [_surface_lang(t) for t in raw_tokens]

    # Count majority side, ignoring 'ambiguous'
    vi_n = surface.count("vi")
    en_n = surface.count("en")

    if vi_n == 0 and en_n == 0:
        return None
    if vi_n > 0 and en_n == 0:
        return None  # pure VN — Rule 1 will handle
    if en_n > 0 and vi_n == 0:
        return None  # pure EN — Rule 1 will handle

    # Mixed. Pick the MINORITY side — that's where X lives.
    if vi_n < en_n:
        target_surface = "vi"
    elif en_n < vi_n:
        target_surface = "en"
    else:
        return None  # 50/50 — ambiguous, let downstream rules decide

    # X candidates: tokens on the minority side that AREN'T metalinguistic
    # verbs themselves (so we don't strip "dịch" from "dịch resilience").
    candidates = [
        raw_tokens[i] for i, s in enumerate(surface)
        if s == target_surface
        and lower[i] not in METALINGUISTIC_VERBS_EN
        and lower[i] not in METALINGUISTIC_VERBS_VN
    ]
    if not candidates:
        return None

    # Strip every candidate from the text (handles multi-word X like
    # "bún bò huế" when the spec example "What does bún bò huế mean?" runs).
    remainder = text
    x_strings: list[str] = []
    for cand in candidates:
        # word-boundary replacement; preserve case-insensitivity
        pat = re.compile(rf"\b{re.escape(cand)}\b", flags=re.IGNORECASE)
        if pat.search(remainder):
            remainder = pat.sub("", remainder, count=1)
            x_strings.append(cand)

    remainder = re.sub(r"\s+", " ", remainder).strip()
    remainder = remainder.strip(" ?.!,;:'\"")

    if not remainder or not x_strings:
        return None

    return " ".join(x_strings), remainder

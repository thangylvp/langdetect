"""Sentence-level language classification via Lingua.

The v4 architecture treats Lingua's whole-sentence verdict as the *primary*
signal. Per-token scoring was considered but rejected after probing — Lingua
is fragile on isolated short tokens (e.g. `"em"` reads as English) but
robust on sentences (e.g. `"cho anh xem"` reads as Vietnamese 0.84).

The classifier returns a `(Language, confidence)` tuple. Callers decide
whether to trust the verdict or override it via the spec rules in
`rule_detector.py`.

Two model variants are exposed:

  `binary_detector()`     — preloads only EN + VI. Fast. Used for the
                            main vi/en verdict.

  `multilang_detector()`  — preloads a broader set so Rule 4 can detect
                            Spanish/French/etc. Latin-script foreign text
                            that the binary detector would force into vi/en.

Both are singletons — built once on first call.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from lingua import Language as L, LanguageDetectorBuilder


# Confidence below this is treated as "Lingua undecided" — we then let
# the rule overrides take precedence.
LINGUA_CONFIDENCE_FLOOR = 0.55


@lru_cache(maxsize=1)
def binary_detector():
    """EN-vs-VI detector. Cheap; preloaded models for low latency."""
    return (
        LanguageDetectorBuilder
        .from_languages(L.ENGLISH, L.VIETNAMESE)
        .with_preloaded_language_models()
        .build()
    )


@lru_cache(maxsize=1)
def multilang_detector():
    """Multi-language detector for Rule 4 unsupported-language verification.
    Loads a wider but bounded set so we can recognize Latin-script foreign
    text (Spanish/French/German/etc.) without all 75 Lingua languages."""
    return (
        LanguageDetectorBuilder
        .from_languages(
            L.ENGLISH, L.VIETNAMESE,
            L.SPANISH, L.FRENCH, L.GERMAN, L.PORTUGUESE,
            L.ITALIAN, L.DUTCH, L.INDONESIAN, L.TAGALOG,
        )
        .with_preloaded_language_models()
        .build()
    )


def binary_score(text: str) -> tuple[Literal["vi", "en"], float]:
    """Return ('vi'|'en', confidence in [0,1]) from the EN/VI detector.

    On extremely short or model-rejected input, returns ('en', 0.5) — a
    neutral fallback. Callers should treat confidence < LINGUA_CONFIDENCE_FLOOR
    as "consult the rule overrides".
    """
    if not text or not text.strip():
        return "en", 0.5
    confs = binary_detector().compute_language_confidence_values(text)
    if not confs:
        return "en", 0.5
    top = confs[0]
    label = "vi" if top.language == L.VIETNAMESE else "en"
    return label, top.value


def multilang_top(text: str) -> tuple[str, float]:
    """Return (ISO-639-1-ish code, confidence) from the wider detector.
    Codes returned: 'en', 'vi', 'es', 'fr', 'de', 'pt', 'it', 'nl', 'id', 'tl'.
    """
    if not text or not text.strip():
        return "en", 0.5
    confs = multilang_detector().compute_language_confidence_values(text)
    if not confs:
        return "en", 0.5
    top = confs[0]
    return _LANG_CODE[top.language], top.value


def multilang_scores(text: str) -> dict[str, float]:
    """Return the FULL score table from the wider detector, keyed by our
    short language codes. Used to distinguish "moderate-confidence foreign"
    (probably VN with non-unique diacritics like à, ì) from "true foreign"
    (where the wider VI score collapses to near zero)."""
    if not text or not text.strip():
        return {}
    confs = multilang_detector().compute_language_confidence_values(text)
    return {_LANG_CODE[c.language]: c.value for c in confs}


_LANG_CODE: dict[L, str] = {
    L.ENGLISH: "en", L.VIETNAMESE: "vi",
    L.SPANISH: "es", L.FRENCH: "fr",
    L.GERMAN: "de", L.PORTUGUESE: "pt",
    L.ITALIAN: "it", L.DUTCH: "nl",
    L.INDONESIAN: "id", L.TAGALOG: "tl",
}

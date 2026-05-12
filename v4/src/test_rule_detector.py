"""Behavioral tests for the v4 detector — Lingua baseline + 3 overrides.

Each block targets one rule/override and includes paraphrases we did NOT
read off the eval CSV — so passing the suite is some evidence of
generalization beyond the dataset.
"""

from __future__ import annotations

import pytest

from rule_detector import detect, Label


# ---------------------------------------------------------------------------
# Rule 1 — Pure language
# ---------------------------------------------------------------------------

PURE_EN_CASES = [
    "Hello world",
    "Generate a report for me",
    "The quick brown fox jumps over the lazy dog",
    "I love programming in Python",
    "Please update the documentation",
]

PURE_VI_CASES = [
    "Tôi đi học",
    "Hôm nay trời rất đẹp",
    "Cho tôi xem báo cáo nhé",
    "Xin chào các bạn",
    "Hãy giúp tôi cập nhật tài liệu",
]


@pytest.mark.parametrize("text", PURE_EN_CASES)
def test_pure_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


@pytest.mark.parametrize("text", PURE_VI_CASES)
def test_pure_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Rule 1 — No-diacritic VN must still classify (the v3 weakness)
# ---------------------------------------------------------------------------

NO_DIACRITIC_VN_LIKELY = [
    "cho anh xem",            # spec example
    "khong biet",             # full VN sentence, zero diacritics
    "ok anh",                 # short, exception-driven
]


@pytest.mark.parametrize("text", NO_DIACRITIC_VN_LIKELY)
def test_no_diacritic_vn_via_lingua_or_exception(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Spec exception list — must force vi when Lingua reads as en
# ---------------------------------------------------------------------------

EXCEPTION_CASES = [
    "thank em",
    "ok anh",
    "hello em",
    "sorry anh",
    "thank nha",
    "cho anh xem nhé",
    "cho em xin file",
]


@pytest.mark.parametrize("text", EXCEPTION_CASES)
def test_exception_list_forces_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# Word-boundary safety: 'em' embedded in English words must NOT match.
NEGATIVE_EXCEPTION_CASES = [
    "system",
    "Please remember the email",
    "Here's the problem and the item",
    "I told them about this",
    "Time to celebrate the moment",
]


@pytest.mark.parametrize("text", NEGATIVE_EXCEPTION_CASES)
def test_exception_word_boundary(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Rule 2 / Step 1 — Translation / meaning question
# ---------------------------------------------------------------------------

TRANSLATION_Q_EN_CASES = [
    "What does phở mean?",                 # spec example
    "What does áo dài mean?",
    "Translate resilience",                # rest stays en
    "Define phở",
    "What is the meaning of phở?",
    "Tell me what bánh mì means",
]


@pytest.mark.parametrize("text", TRANSLATION_Q_EN_CASES)
def test_translation_q_resolves_to_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


TRANSLATION_Q_VI_CASES = [
    "dịch resilience",                     # spec example
    "dịch resilience sang tiếng Anh",
    "resilience nghĩa là gì",
    "giải thích resilience",
]


@pytest.mark.parametrize("text", TRANSLATION_Q_VI_CASES)
def test_translation_q_resolves_to_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# False-positive guard: "What is wrong?" is NOT a translation question.
def test_what_is_wrong_is_pure_en():
    r = detect("What is wrong?")
    assert r.label == Label.EN
    assert "translation_q" not in r.rule


# ---------------------------------------------------------------------------
# Rule 2 / Step 3 — Entity-only override (VI Lingua → EN)
# ---------------------------------------------------------------------------

ENTITY_ONLY_EN_CASES = [
    "Visit Hà Nội next week",
    "Phở is delicious",
    "I love Áo Dài",
    "Welcome to Hội An",
    "Going to Đà Nẵng tomorrow",
]


@pytest.mark.parametrize("text", ENTITY_ONLY_EN_CASES)
def test_entity_only_overrides_to_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Vingroup brand recognition (expanded family)
# ---------------------------------------------------------------------------

BRAND_IN_VI_CONTEXT_VI = [
    "Tôi học ở Vinschool",                 # VN content + brand → vi
    "VinBigData làm AI rất tốt",           # VN content → vi
    "Tôi đi khám ở Vinmec",
    "Mua xe VinFast nhé",
]


@pytest.mark.parametrize("text", BRAND_IN_VI_CONTEXT_VI)
def test_brand_in_vi_context_stays_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


BRAND_IN_EN_CONTEXT_EN = [
    "Order something from Winmart",
    "Apply to Vinschool",
    "Test driving a VinFast",
    "VinAI published a new paper",
    "Vinhomes Ocean Park is huge",
]


@pytest.mark.parametrize("text", BRAND_IN_EN_CONTEXT_EN)
def test_brand_in_en_context_stays_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Rule 3 — Insufficient signal
# ---------------------------------------------------------------------------

RULE_3_CASES = ["ok", "okay", "wow", "alo", "ukm", "huh", "haha",
                "123", "456 789", "", "   "]


@pytest.mark.parametrize("text", RULE_3_CASES)
def test_rule_3_unknown(text):
    r = detect(text)
    assert r.label == Label.UNKNOWN, f"{text!r} → {r}"
    assert r.confidence < 0.6


# ---------------------------------------------------------------------------
# Rule 4 — Out-of-scope language
# ---------------------------------------------------------------------------

RULE_4_NON_LATIN_CASES = [
    "안녕하세요",            # Korean
    "你好世界",              # Chinese
    "こんにちは",             # Japanese
    "Привет мир",           # Russian
    "مرحبا بالعالم",         # Arabic
    "नमस्ते दुनिया",          # Hindi
    "สวัสดีชาวโลก",          # Thai
    "Hello 안녕하세요 mixed",
]


@pytest.mark.parametrize("text", RULE_4_NON_LATIN_CASES)
def test_rule_4_non_latin_unsupported(text):
    r = detect(text)
    assert r.label == Label.UNSUPPORTED, f"{text!r} → {r}"


# Latin-script foreign — Spanish, French, German, etc.
RULE_4_LATIN_FOREIGN_CASES = [
    "Hola mundo, ¿cómo estás?",      # Spanish
    "Je ne parle pas anglais",        # French
    "Ich heiße Klaus",                 # German
    "Buongiorno, come stai oggi?",    # Italian
    "Hallo wereld goedemorgen",      # Dutch
]


@pytest.mark.parametrize("text", RULE_4_LATIN_FOREIGN_CASES)
def test_rule_4_latin_foreign_unsupported(text):
    r = detect(text)
    assert r.label == Label.UNSUPPORTED, f"{text!r} → {r}"
    assert r.rule == "rule_4_latin_foreign"


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

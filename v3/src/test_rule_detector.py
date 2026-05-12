"""Accuracy tests for v3.

All v2 tests carry forward unchanged. New v3-specific blocks at the bottom:
  - Brand gazetteer (Vingroup ecosystem) — standalone & mixed contexts
  - INTERJECTIONS trim — "hello" → EN, VN diacritic particles → VI
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
    "Please update the documentation",
    "I love programming in Python",
]

PURE_VI_CASES = [
    "Tôi đi học",
    "Hôm nay trời rất đẹp",
    "Cho tôi xem báo cáo nhé",
    "Xin chào các bạn",
    "Hãy giúp tôi cập nhật tài liệu",
]


@pytest.mark.parametrize("text", PURE_EN_CASES)
def test_rule_1_pure_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"
    assert r.rule.startswith("rule_1"), f"expected rule_1, got {r.rule}"


@pytest.mark.parametrize("text", PURE_VI_CASES)
def test_rule_1_pure_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Rule 2 / Step 1 — VN function word in mixed sentence → vi
# ---------------------------------------------------------------------------

STEP_1_CASES = [
    "Show me status của project Vision",
    "Check hộ mình cái report",
    "Update report cho tôi nhé",
    "Tôi cần check file này",
    "Help mình tạo một file mới",
    "Send email với attachment",
    "Get data từ database",
    "Run analysis trong folder này",
]


@pytest.mark.parametrize("text", STEP_1_CASES)
def test_rule_2_step_1(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"
    assert "step_1" in r.rule, f"expected step_1, got {r.rule}"


# ---------------------------------------------------------------------------
# Rule 2 / Step 2 — Sentence starts with English anchor → en
# ---------------------------------------------------------------------------

STEP_2_CASES = [
    "Is Voi châu Á dangerous?",
    "What is Phở?",
    "Tell me about Hà Nội",
    "How many Áo Dài are there?",
    "Show Hồ Chí Minh weather",
    "Can you describe Bánh Mì?",
    "Where is Đà Nẵng located?",
    "Find me a restaurant in Hội An",
]


@pytest.mark.parametrize("text", STEP_2_CASES)
def test_rule_2_step_2(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"
    assert "step_2" in r.rule, f"expected step_2, got {r.rule}"


# ---------------------------------------------------------------------------
# Rule 2 / Step 4.1 — All VN tokens are entity / cultural → en
# ---------------------------------------------------------------------------

STEP_4_1_CASES = [
    "Admin delete Áo Dài",
    "Visit Hà Nội and Đà Nẵng next month",
    "I love Phở and Bánh Mì",
    "Welcome to Hội An",
    "Phở is delicious",
    "Tết Nguyên Đán is coming",
]


@pytest.mark.parametrize("text", STEP_4_1_CASES)
def test_rule_2_step_4_1(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"
    assert "step_4_1" in r.rule, f"expected step_4_1, got {r.rule}"


# ---------------------------------------------------------------------------
# Rule 2 / Step 4.2 — At least one VN common-class word → vi
# ---------------------------------------------------------------------------

STEP_4_2_CASES = [
    "Admin delete bài viết",
    "Nhân viên trực gate 1",
    "User submitted báo cáo lỗi",
    "Admin approved yêu cầu",
    "Submit báo cáo cuối tuần",
]


@pytest.mark.parametrize("text", STEP_4_2_CASES)
def test_rule_2_step_4_2(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# Rule 3 — Insufficient signal → unknown
# ---------------------------------------------------------------------------
# Note: in v3 we removed "hello" and VN-diacritic particles ("dạ", "ừ", …)
# from INTERJECTIONS, so they no longer land here — separate tests below.

RULE_3_CASES = [
    "ok",
    "okay",
    "wow",
    "alo",
    "ukm",
    "huh",
    "haha",
    "123",
    "456 789",
    "",
    "   ",
]


@pytest.mark.parametrize("text", RULE_3_CASES)
def test_rule_3_unknown(text):
    r = detect(text)
    assert r.label == Label.UNKNOWN, f"{text!r} → {r}"
    assert r.confidence < 0.6, f"confidence should be <0.6, got {r.confidence}"


# ---------------------------------------------------------------------------
# Rule 4 — Out-of-scope language → unsupported_language
# ---------------------------------------------------------------------------

RULE_4_CASES = [
    "안녕하세요",
    "你好世界",
    "こんにちは",
    "Привет мир",
    "مرحبا بالعالم",
    "नमस्ते दुनिया",
    "สวัสดีชาวโลก",
    "Hello 안녕하세요 mixed",
]


@pytest.mark.parametrize("text", RULE_4_CASES)
def test_rule_4_unsupported(text):
    r = detect(text)
    assert r.label == Label.UNSUPPORTED, f"{text!r} → {r}"
    assert r.rule == "rule_4_script", f"expected rule_4_script, got {r.rule}"


# ---------------------------------------------------------------------------
# Ambiguity / regression cases (carry-over from v2)
# ---------------------------------------------------------------------------

def test_what_do_you_think_is_english():
    r = detect("What do you think about this?")
    assert r.label == Label.EN, f"got {r}"


def test_can_i_sing_a_song_is_english():
    r = detect("Can I sing a song now?")
    assert r.label == Label.EN, f"got {r}"


def test_step_1_beats_step_2_when_both_match():
    r = detect("Show me status của project Vision")
    assert r.label == Label.VI
    assert r.rule == "rule_2_step_1"


def test_cultural_term_override():
    r = detect("Phở is delicious")
    assert r.label == Label.EN
    assert "step_4_1" in r.rule or "step_1" in r.rule


SPEC_ORDERING_EN_CASES = [
    "Update thông tin user",
    "Delete bài viết spam",
    "Is bài viết important?",
    "Generate báo cáo for me",
]


@pytest.mark.parametrize("text", SPEC_ORDERING_EN_CASES)
def test_step_2_beats_step_4_by_ordering(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"
    assert r.rule == "rule_2_step_2", f"expected step_2, got {r.rule}"


# ---------------------------------------------------------------------------
# v3 — Vingroup brand gazetteer
# ---------------------------------------------------------------------------
# Brands are treated like cultural terms: they count as VN tokens and as
# entity-like. A standalone brand query labels VI (per dataset GT convention);
# a brand inside an English sentence labels EN.

BRAND_STANDALONE_CASES = [
    "vinpearl",
    "Vinpearl",
    "VINPEARL",
    "vinfast",
    "vinhomes",
    "vinmec",
    "vinuni",
    "dyno",
]


@pytest.mark.parametrize("text", BRAND_STANDALONE_CASES)
def test_brand_standalone_is_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"
    assert r.rule == "rule_1_pure_vi", f"expected pure_vi, got {r.rule}"


BRAND_IN_EN_CONTEXT_CASES = [
    "Show me Vinpearl info",
    "Where is the Vinpearl resort located?",
    "Tell me about VinFast",
    "How can I book Vinpearl?",
]


@pytest.mark.parametrize("text", BRAND_IN_EN_CONTEXT_CASES)
def test_brand_in_en_context_is_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


# ---------------------------------------------------------------------------
# v3 — Trimmed INTERJECTIONS
# ---------------------------------------------------------------------------
# "hello" was filler in v2; dataset GT labels it EN.
HELLO_AS_EN_CASES = [
    "hello",
    "hello hello",
    "hello hello hello",
]


@pytest.mark.parametrize("text", HELLO_AS_EN_CASES)
def test_hello_is_en(text):
    r = detect(text)
    assert r.label == Label.EN, f"{text!r} → {r}"


# VN-diacritic particles were filler in v2; they're now pure VN tokens.
VN_PARTICLE_AS_VI_CASES = [
    "dạ",
    "ừ",
    "vâng",
    "ơi",
]


@pytest.mark.parametrize("text", VN_PARTICLE_AS_VI_CASES)
def test_vn_particle_is_vi(text):
    r = detect(text)
    assert r.label == Label.VI, f"{text!r} → {r}"


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))

"""Entity gazetteers + spec exceptions for v4.

Three bounded lists, all spec-justified:

  CULTURAL_TERMS    — VN cultural common-nouns (foods, garments, holidays)
                      that lexicographically look like "danh từ phổ thông"
                      but should be treated as "cultural term" entities per
                      Phụ lục A Bảng 1.

  VINGROUP_BRANDS   — Vingroup ecosystem brand family. Expanded from v3
                      (which had a small core list) to cover the full
                      family: VinFast / Vinhomes / Vincom / Vinpearl /
                      Vinmec / Vinschool / VinUni / VinAI / VinBigData /
                      VinSmart / VinPro / VinMart / WinMart / WinCommerce
                      and the major sub-projects.

  EXCEPTION_VN      — spec's "Ngoại lệ" list: tokens/phrases that override
                      a Lingua-EN verdict back to VI. Exactly the 5 entries
                      from the spec, no expansion. Word-boundary matching.

  METALINGUISTIC_VERBS — closed-class verbs that mark a "what does X mean /
                      translate X / X là gì" sentence. Used by Rule 2 Step 1.

All sets are lowercase. Matching upstream is case-insensitive.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Cultural terms (Phụ lục A Bảng 1 — món ăn, trang phục, ngày lễ, ...)
# Carried over from v3 unchanged.
# ---------------------------------------------------------------------------
CULTURAL_TERMS: frozenset[str] = frozenset({
    # Món ăn / đồ uống
    "phở", "bún bò huế", "bánh mì", "gỏi cuốn", "cơm tấm", "bún chả",
    "chả giò", "bánh xèo", "cà phê trứng", "bún riêu", "canh chua",
    "mì quảng", "cao lầu", "bánh cuốn", "nem chua", "chè", "bánh flan",
    "hủ tiếu",
    # Trang phục / vật phẩm văn hóa
    "áo dài", "áo bà ba", "nón lá", "áo tứ thân", "khăn đóng",
    # Ngày lễ / sự kiện
    "tết", "tết nguyên đán", "tết trung thu", "tết đoan ngọ",
    "giỗ tổ", "giỗ tổ hùng vương", "cúng rằm",
    # Loài / biểu tượng văn hóa
    "hoa sen", "hoa mai", "hoa đào", "sao la", "chim lạc",
    "voi châu á",
})


# ---------------------------------------------------------------------------
# Vingroup brand family — expanded.
# Bounded list: Vingroup has a finite, public set of brands. New entries
# only when a new official brand is launched; not when the dataset shows
# a miss.
# ---------------------------------------------------------------------------
VINGROUP_BRANDS: frozenset[str] = frozenset({
    # Parent
    "vingroup", "vin group",
    # Auto / mobility
    "vinfast", "vin fast",
    # Real estate / development
    "vinhomes", "vin homes",
    "vinhomes ocean park", "vinhomes times city", "vinhomes riverside",
    "vinhomes smart city", "vinhomes central park", "vinhomes grand park",
    "vinhomes royal city",
    "vincom", "vin com",
    "vincom plaza", "vincom mega mall", "vincom center", "vincom retail",
    "vincity",
    # Hospitality / tourism
    "vinpearl",
    "vinpearl land", "vinpearl safari", "vinpearl golf", "vinpearl resort",
    # Healthcare
    "vinmec", "vinmec international", "vinfa",
    # Education
    "vinschool",
    "vinuni", "vinuniversity", "vin university",
    # Tech / AI / data
    "vinai", "vin ai",
    "vinbigdata", "vin big data", "vbd",
    "vinsmart", "vin smart",
    "vinhms",
    # Retail (legacy Vin* + post-Masan acquisition Win*)
    "vinmart", "vinmart+", "vinmart plus",
    "winmart", "winmart+", "winmart plus",
    "wincommerce", "win commerce",
    "win+", "wineco", "win eco",
    # Other ventures
    "vinpro", "vineco", "vin eco", "vinda",
    "vinke", "vinds",
})


# ---------------------------------------------------------------------------
# Spec exception list — "Ngoại lệ" in task_requirement.
#
# These are no-diacritic Vietnamese tokens / phrases that the spec
# EXPLICITLY says should force a `vi` label even when Lingua sees the
# sentence as English (because they're tiny + appear in mostly-English
# casual chat: "thank em", "ok anh", "hello em", "sorry anh", "cho em xem").
#
# DO NOT expand this set when you see a dataset failure. It exists to
# match the spec's wording, not to overfit. If a dataset failure suggests
# expansion, it's a spec gap — flag it upstream.
# ---------------------------------------------------------------------------
EXCEPTION_VN_TOKENS: frozenset[str] = frozenset({
    "em", "anh", "nha",
})
EXCEPTION_VN_PHRASES: tuple[str, ...] = (
    "cho anh", "cho em",
)


# ---------------------------------------------------------------------------
# Metalinguistic verbs — Rule 2 Step 1 trigger.
# Closed list. The presence of one (+ a single alien token elsewhere)
# indicates the sentence is ASKING ABOUT a word, not USING it.
# ---------------------------------------------------------------------------
METALINGUISTIC_VERBS_EN: frozenset[str] = frozenset({
    "mean", "means", "meant", "meaning",
    "translate", "translation",
    "define", "defines", "defined", "definition",
    "explain", "explains", "explained",
    "say",     # narrow — qualified by phrasing in the matcher
})
METALINGUISTIC_VERBS_VN: frozenset[str] = frozenset({
    "nghĩa",
    "dịch",
    "giải thích",
    "gọi là",
    "có nghĩa",
})

"""Vietnamese cultural common-nouns that should behave like proper nouns.

underthesea's POS tagger labels these as POS=N (common noun) because they ARE
common nouns within Vietnamese — but in EN-context they behave like
untranslatable cultural entities (Step 4.1 of Rule 2 should treat them as
"danh từ riêng / cultural term").

Examples: "Phở is delicious"  → should be EN, not VI. Without this override,
underthesea would tag "Phở" as POS=N and Step 4.2 would force VI.

This list is bounded by reality — there's a finite set of well-known Vietnamese
foods/garments/cultural items that appear in English text. Extend as needed.
NER-recognized entities (Hà Nội, Vinamilk, Trần Hưng Đạo) DON'T need to be here
because underthesea NER catches them on its own.

Stored as lowercase; matching is case-insensitive on the underthesea token
form (which may join multi-word units like "Bánh Mì" into a single token).
"""

_CULTURAL_TERMS_RAW: tuple[str, ...] = (
    # Món ăn / đồ uống thuần Việt
    "phở",
    "bún bò huế",
    "bánh mì",
    "gỏi cuốn",
    "cơm tấm",
    "bún chả",
    "chả giò",
    "bánh xèo",
    "cà phê trứng",
    "bún riêu",
    "canh chua",
    "mì quảng",
    "cao lầu",
    "bánh cuốn",
    "nem chua",
    "chè",
    "bánh flan",
    "hủ tiếu",
    # Trang phục / vật phẩm văn hóa
    "áo dài",
    "áo bà ba",
    "nón lá",
    "áo tứ thân",
    "khăn đóng",
    # Ngày lễ / sự kiện văn hóa Việt
    "tết",
    "tết nguyên đán",
    "tết trung thu",
    "tết đoan ngọ",
    "giỗ tổ",
    "giỗ tổ hùng vương",
    "cúng rằm",
    # Loài / biểu tượng văn hóa
    "hoa sen",
    "hoa mai",
    "hoa đào",
    "sao la",
    "chim lạc",
)

CULTURAL_TERMS: frozenset[str] = frozenset(_CULTURAL_TERMS_RAW)

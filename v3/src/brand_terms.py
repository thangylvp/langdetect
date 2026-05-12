"""Vingroup ecosystem brand names + the conversational agent's own name.

This service runs inside Vingroup's conversational AI gateway, so brand names
like "Vinpearl" and "VinFast" appear frequently in user input. Without this
list they fall through the diacritic gate and get treated as English tokens.

Brands are tagged the same way as `cultural_terms.CULTURAL_TERMS`:

  1. They count as Vietnamese tokens (so a query that contains only brand
     names — e.g. just "vinpearl" — labels as VI per dataset GT convention).
  2. They count as entity-like in `_is_entity_token`, so a sentence like
     `"Show me Vinpearl info"` still routes through Rule 2 / Step 4.1 (or
     Step 2 via the EN anchor) and labels as EN.

Stored as lowercase, single-word stems. underthesea typically tokenizes
brand compounds (e.g. "Vinpearl Land") into separate tokens, so matching
the stem is enough. Matching is case-insensitive on `tok.lower()`.

Sources: Vingroup public subsidiary roster + product names that appear in
the eval dataset. Extend as new brands surface in production logs.
"""

_BRAND_TERMS_RAW: tuple[str, ...] = (
    # ----- Parent / corporate -----
    "vingroup",
    "vincom",
    "vincommerce",
    # ----- Hospitality / tourism -----
    "vinpearl",
    "vinwonders",
    "vinwonder",
    "vinoasis",
    "vinholidays",
    # ----- Real estate -----
    "vinhomes",
    "vincity",
    "vinroyal",
    "vinsmart",
    # ----- Automotive / transport -----
    "vinfast",
    "vinbus",
    "vines",            # Vingroup electric scooter line (also appears in eval CSV)
    # ----- Retail / commerce -----
    "vinmart",
    "vinpro",
    "vinid",
    # ----- Healthcare / pharma -----
    "vinmec",
    "vinfa",
    # ----- Education -----
    "vinuni",
    "vinschool",
    "vinser",
    # ----- Technology / R&D -----
    "vinai",
    "vinbigdata",
    "vinbase",
    "vinhms",
    "vinbrain",
    # ----- The conversational agent itself -----
    "dyno",
)

BRAND_TERMS: frozenset[str] = frozenset(_BRAND_TERMS_RAW)

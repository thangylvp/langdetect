"""English sentence-initial grammar anchors — Phụ lục A, Bảng 4.

Used by Rule 2 / Step 2: if Step 1 (Vietnamese function-word check via POS) did
not fire, and the sentence STARTS with one of these phrases, label = EN.

This list is intentionally hand-maintained because it is bounded by English
grammar (Wh-questions + auxiliaries + imperatives + polite phrasings). It does
not need to grow with vocabulary like noun lexicons do.

All entries stored lowercase; matching is case-insensitive and word-boundary
aware (so `"do"` matches `"Do you ..."` but not `"don't ..."`).
"""

# Sorted longest-first so the greedy matcher tries multi-word phrases before
# their single-word prefixes (e.g. "What is" before "What").
_ANCHORS_RAW: tuple[str, ...] = (
    # ----- Wh-questions, multi-word -----
    "what is", "what are", "what was", "what were",
    "what does", "what do", "what did",
    "what will", "what would", "what should", "what can", "what could",
    "what has", "what have",
    "where is", "where are", "where was", "where were",
    "where can", "where do", "where does",
    "when is", "when are", "when was", "when were",
    "when did", "when will", "when does",
    "who is", "who are", "who was", "who were",
    "who does", "who did", "who can",
    "why is", "why are", "why was",
    "why did", "why does", "why do",
    "why would", "why should",
    "which is", "which are", "which one", "which of",
    "how is", "how are", "how was",
    "how do", "how does", "how did",
    "how can", "how could", "how to",
    "how many", "how much", "how long", "how often", "how far",
    "whose is", "whose are",
    # ----- Contractions / inversions -----
    "what's", "where's", "who's", "how's", "when's",
    "that's", "it's", "there's", "here's",
    "tell me about", "tell me how", "tell me what",
    "tell me why", "tell me when",
    "do you know", "do you have", "do you think",
    "is there", "are there",
    "is it", "is this", "is that",
    "can i", "can we", "could i", "could we", "would it be",
    # ----- Imperatives (multi-word first) -----
    "show me", "tell me", "give me", "find me",
    "get me", "help me", "send me", "take me",
    # ----- Polite request openers -----
    "can you", "could you", "would you", "will you",
    # ----- Single-word imperatives (action verbs as sentence starters) -----
    "show", "tell", "find", "get", "list",
    "create", "generate", "write", "make", "build", "run",
    "check", "set", "add", "remove", "delete", "update", "fix",
    "open", "close", "start", "stop", "enable", "disable",
    "upload", "download", "deploy", "configure", "install",
    "search", "filter", "sort", "calculate", "convert",
    "translate", "summarize", "explain", "compare", "analyze",
    "review", "test",
    "please", "kindly",
    # ----- Single-word auxiliaries (Yes/No questions) -----
    "is", "are", "was", "were",
    "will", "would", "should", "could", "can",
    "may", "might", "must", "shall",
    "has", "have", "had",
    "does", "do", "did",
)

# Stored sorted longest-first for greedy prefix match.
EN_ANCHORS: tuple[str, ...] = tuple(
    sorted(set(_ANCHORS_RAW), key=lambda s: (-len(s.split()), -len(s)))
)

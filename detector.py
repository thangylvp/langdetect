from abc import ABC, abstractmethod
from enum import StrEnum

# FastText label prefix (e.g. "__label__vi")
_FT_LABEL_PREFIX = "__label__"
_FT_LANG_MAP: dict[str, "Language"] = {}


class Language(StrEnum):
    EN = "en"
    VI = "vi"
    UNKNOWN = "unknown"


_FT_LANG_MAP = {
    "en": Language.EN,
    "vi": Language.VI,
}


class LanguageDetector(ABC):
    @abstractmethod
    def detect(self, text: str) -> Language: ...

    @abstractmethod
    def detect_with_confidence(self, text: str) -> tuple[Language, float]: ...


class LinguaDetector(LanguageDetector):
    # Minimum confidence to accept a detected language. Below threshold -> fallback to VI
    MIN_CONFIDENCE = 0.5

    def __init__(self):
        from lingua import Language as L, LanguageDetectorBuilder

        self._detector = (
            LanguageDetectorBuilder.from_languages(L.ENGLISH, L.VIETNAMESE)
            .with_preloaded_language_models()
            .build()
        )

    def detect(self, text: str) -> Language:
        lang, _ = self.detect_with_confidence(text)
        return lang

    def detect_with_confidence(self, text: str) -> tuple[Language, float]:
        from lingua import Language as L

        result = self._detector.compute_language_confidence_values(text)
        if not result:
            return Language.VI, 0.0

        top = result[0]
        if top.value < self.MIN_CONFIDENCE:
            return Language.VI, top.value
        if top.language == L.ENGLISH:
            return Language.EN, top.value
        return Language.VI, top.value


class FastTextDetector(LanguageDetector):
    MIN_CONFIDENCE = 0.5

    def __init__(self, model_path: str):
        import fasttext
        import fasttext.FastText as _ft_module
        import numpy as np

        # Suppress "Warning : `load_model` does not return WordVectorModel"
        fasttext.FastText.eprint = lambda *args, **kwargs: None

        # NumPy 2.x removed the copy=False shorthand; patch fasttext's numpy reference
        # so that np.array(x, copy=False) becomes np.asarray(x).
        class _NpCompat:
            def __getattr__(self, name: str):  # type: ignore[override]
                return getattr(np, name)

            def array(self, obj, *args, copy=None, **kwargs):
                if copy is False:
                    return np.asarray(obj, *args, **kwargs)
                return np.array(obj, *args, copy=copy, **kwargs)

        _ft_module.np = _NpCompat()  # type: ignore[assignment]

        self._model = fasttext.load_model(model_path)

    def detect(self, text: str) -> Language:
        lang, _ = self.detect_with_confidence(text)
        return lang

    def detect_with_confidence(self, text: str) -> tuple[Language, float]:
        # fasttext chokes on newlines
        cleaned = text.replace("\n", " ").strip()
        if not cleaned:
            return Language.VI, 0.0

        labels, scores = self._model.predict(cleaned, k=-1, threshold=0.0)
        if not labels:
            return Language.VI, 0.0

        lang_scores: dict[str, float] = {}
        for label, score in zip(labels, scores):
            iso = label.removeprefix(_FT_LABEL_PREFIX)
            if iso in _FT_LANG_MAP:
                lang_scores[iso] = float(score)

        if not lang_scores:
            return Language.VI, 0.0

        best_iso = max(lang_scores, key=lang_scores.__getitem__)
        best_score = lang_scores[best_iso]

        return _FT_LANG_MAP[best_iso], best_score

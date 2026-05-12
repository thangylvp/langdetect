from functools import lru_cache

from .detector import FastTextDetector, Language, LanguageDetector, LinguaDetector
from .schemas import DetectorEngine


@lru_cache(maxsize=1)
def _lingua_detector() -> LanguageDetector:
    return LinguaDetector()


@lru_cache(maxsize=1)
def _fasttext_detector() -> LanguageDetector:
    from ... import env

    if not env.FASTTEXT_MODEL_PATH:
        raise RuntimeError(
            "FASTTEXT_MODEL_PATH env var is not set. "
            "Download a model from https://fasttext.cc/docs/en/language-identification.html "
            "and set the path."
        )
    return FastTextDetector(env.FASTTEXT_MODEL_PATH)


def get_detector(engine: DetectorEngine = DetectorEngine.LINGUA) -> LanguageDetector:
    if engine == DetectorEngine.FASTTEXT:
        return _fasttext_detector()
    return _lingua_detector()


def detect(text: str, engine: DetectorEngine = DetectorEngine.LINGUA) -> tuple[Language, float]:
    return get_detector(engine).detect_with_confidence(text)

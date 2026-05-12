from enum import StrEnum

from pydantic import BaseModel, Field

from .detector import Language


class DetectorEngine(StrEnum):
    LINGUA = "lingua"
    FASTTEXT = "fasttext"


class DetectRequest(BaseModel):
    text: str = Field(..., min_length=1)
    engine: DetectorEngine = DetectorEngine.LINGUA


class DetectResponse(BaseModel):
    language: Language
    confidence: float = Field(..., ge=0.0, le=1.0)
    engine: DetectorEngine

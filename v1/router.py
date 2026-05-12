from fastapi import APIRouter

from . import service
from .schemas import DetectRequest, DetectResponse

router = APIRouter(prefix="/langdetect", tags=["langdetect"])


@router.post("/detect", response_model=DetectResponse)
async def detect_language(body: DetectRequest) -> DetectResponse:
    language, confidence = service.detect(body.text, body.engine)
    return DetectResponse(language=language, confidence=confidence, engine=body.engine)

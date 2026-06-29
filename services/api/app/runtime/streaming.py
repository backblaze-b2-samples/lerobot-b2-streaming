import logging

from fastapi import APIRouter, HTTPException

from app.service.streaming import StreamError, run_stream
from app.types import StreamRunRequest, StreamRunStats

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/stream", response_model=StreamRunStats)
async def stream_run_endpoint(req: StreamRunRequest):
    """Stream a chosen episode or task split chunk-by-chunk from B2 and report
    bytes-fetched vs total, plus a mini training-loop loss."""
    if req.workers < 1 or req.workers > 8:
        raise HTTPException(status_code=400, detail="workers must be between 1 and 8")
    try:
        return run_stream(req)
    except StreamError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None

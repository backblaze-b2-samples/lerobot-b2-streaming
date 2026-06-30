import logging

from fastapi import APIRouter, HTTPException

from app.service import dataset_stats
from app.service.episodes import (
    EpisodeError,
    camera_video_url,
    create_episode,
    delete_episode,
    get_episode,
    inspect_source,
    list_episodes,
    relabel_episode,
)
from app.types import (
    DailyEpisodeCount,
    DatasetStats,
    Episode,
    EpisodeCreateRequest,
    EpisodeCreateResult,
    EpisodeFormOptions,
    EpisodeUpdateRequest,
    SourceInfo,
)
from app.types.episodes import (
    MAX_EPISODE_FRAMES,
    PRESET_SOURCES,
    PRESET_TASKS,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _handle(e: EpisodeError):
    raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/episodes/options", response_model=EpisodeFormOptions)
async def episode_options():
    """Task labels, the curated source shortlist, and the frames ceiling the
    create form renders. The recording shape itself is derived from the chosen
    source (see GET /episodes/source-info), not picked from knobs."""
    return EpisodeFormOptions(
        tasks=PRESET_TASKS,
        sources=PRESET_SOURCES,
        default_task=PRESET_TASKS[0],
        default_source=PRESET_SOURCES[0],
        max_frames=MAX_EPISODE_FRAMES,
    )


@router.get("/episodes/source-info", response_model=SourceInfo)
async def episode_source_info(repo_id: str | None = None):
    """Preview the real shape (cameras, fps, native resolution, state/action dims,
    episode length) an ingest from `repo_id` will reproduce — or a 400 if the
    source can't be loaded. Omit `repo_id` for the server default source."""
    try:
        return inspect_source(repo_id)
    except EpisodeError as e:
        _handle(e)


@router.get("/episodes/stats", response_model=DatasetStats)
async def episodes_stats():
    return dataset_stats.get_dataset_stats()


@router.get("/episodes/stats/activity", response_model=list[DailyEpisodeCount])
async def episodes_activity(days: int = 7):
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return dataset_stats.get_ingest_activity(days=days)


@router.get("/episodes", response_model=list[Episode])
async def list_episodes_endpoint(task: str | None = None):
    return list_episodes(task=task)


@router.post("/episodes", response_model=EpisodeCreateResult)
async def create_episode_endpoint(req: EpisodeCreateRequest):
    try:
        return create_episode(req)
    except EpisodeError as e:
        _handle(e)


@router.get("/episodes/{index}", response_model=Episode)
async def get_episode_endpoint(index: int):
    try:
        return get_episode(index)
    except EpisodeError as e:
        _handle(e)


@router.patch("/episodes/{index}", response_model=Episode)
async def relabel_episode_endpoint(index: int, req: EpisodeUpdateRequest):
    try:
        return relabel_episode(index, req.task)
    except EpisodeError as e:
        _handle(e)


@router.delete("/episodes/{index}")
async def delete_episode_endpoint(index: int):
    try:
        deleted = delete_episode(index)
    except EpisodeError as e:
        _handle(e)
    return {"deleted": True, "episode_index": index, "objects_removed": deleted}


@router.get("/episodes/{index}/video")
async def episode_video_endpoint(index: int, camera: str):
    try:
        return {"url": camera_video_url(index, camera)}
    except EpisodeError as e:
        _handle(e)

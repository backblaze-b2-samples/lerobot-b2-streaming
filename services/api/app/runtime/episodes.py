import logging

from fastapi import APIRouter, HTTPException

from app.service import dataset_stats
from app.service.episodes import (
    EpisodeError,
    camera_video_url,
    create_episode,
    delete_episode,
    get_episode,
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
)
from app.types.episodes import (
    ALLOWED_FPS,
    ALLOWED_NUM_CAMERAS,
    ALLOWED_NUM_FRAMES,
    ALLOWED_RESOLUTIONS,
    PRESET_TASKS,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _handle(e: EpisodeError):
    raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/episodes/options", response_model=EpisodeFormOptions)
async def episode_options():
    """Finite option sets + safe defaults the create/edit forms render."""
    return EpisodeFormOptions(
        tasks=PRESET_TASKS,
        num_cameras=ALLOWED_NUM_CAMERAS,
        num_frames=ALLOWED_NUM_FRAMES,
        fps=ALLOWED_FPS,
        resolutions=ALLOWED_RESOLUTIONS,
        default_task=PRESET_TASKS[0],
        default_num_cameras=2,
        default_num_frames=60,
        default_fps=30,
        default_resolution=256,
    )


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

"""Episode lifecycle orchestration (create/read/list/relabel/delete).

No boto3 / lerobot imports here — those stay in repo/. This layer wires the
LeRobot v3 build adapter to the B2 object store and returns Pydantic models.

B2 prefix layout (everything under settings.dataset_prefix):

    {prefix}episodes/ep_000000/   <- one v3 dataset tree per episode
        meta/info.json
        meta/episodes/chunk-000/file-000.parquet
        meta/tasks.parquet
        data/chunk-000/file-000.parquet
        videos/<cam>/chunk-000/file-000.mp4

Each episode owns its own prefix, so the delete verb is naturally scoped.
"""

import logging
import mimetypes
import shutil
from pathlib import Path

from app.config import settings
from app.repo import (
    delete_prefix,
    get_object_bytes,
    head_size,
    list_keys,
    presign_key,
    put_bytes,
    upload_path,
)
from app.repo import lerobot_dataset as ld
from app.service import episode_meta
from app.types import (
    Episode,
    EpisodeCreateRequest,
    EpisodeCreateResult,
)
from app.types.episodes import (
    ALLOWED_FPS,
    ALLOWED_NUM_CAMERAS,
    ALLOWED_NUM_FRAMES,
    ALLOWED_RESOLUTIONS,
    PRESET_TASKS,
)
from app.types.formatting import humanize_bytes

logger = logging.getLogger(__name__)


class EpisodeError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _cleanup_root(local_root: str) -> None:
    """Remove the throwaway temp dir. make_temp_root() returns a `root/`
    subpath, so we drop its parent to leave no temp directories behind."""
    shutil.rmtree(Path(local_root).parent, ignore_errors=True)


def _episode_prefix(index: int) -> str:
    return f"{settings.dataset_prefix}episodes/ep_{index:06d}/"


def _meta_prefix(index: int) -> str:
    return f"{_episode_prefix(index)}meta/"


def _next_episode_index() -> int:
    prefix = f"{settings.dataset_prefix}episodes/"
    seen = set()
    for obj in list_keys(prefix):
        rest = obj["key"][len(prefix):]
        seg = rest.split("/", 1)[0]  # ep_000000
        if seg.startswith("ep_"):
            try:
                seen.add(int(seg[3:]))
            except ValueError:
                continue
    return (max(seen) + 1) if seen else 0


def _validate_create(req: EpisodeCreateRequest) -> None:
    if req.task not in PRESET_TASKS:
        raise EpisodeError(f"Unknown task '{req.task}'")
    if req.num_cameras not in ALLOWED_NUM_CAMERAS:
        raise EpisodeError("num_cameras must be one of 1, 2, 3")
    if req.num_frames not in ALLOWED_NUM_FRAMES:
        raise EpisodeError("num_frames must be one of 30, 60, 120")
    if req.fps not in ALLOWED_FPS:
        raise EpisodeError("fps must be one of 10, 30")
    if req.resolution not in ALLOWED_RESOLUTIONS:
        raise EpisodeError("resolution must be one of 128, 256")


def _content_type(key: str) -> str:
    mime, _ = mimetypes.guess_type(key)
    return mime or "application/octet-stream"


def _upload_tree(local_root: str, index: int) -> tuple[int, int]:
    """Upload the built v3 tree under the episode's B2 prefix.

    Returns (bytes_uploaded, object_count).
    """
    root = Path(local_root)
    prefix = _episode_prefix(index)
    bytes_uploaded = 0
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        key = f"{prefix}{rel}"
        upload_path(str(path), key, _content_type(key))
        bytes_uploaded += path.stat().st_size
        count += 1
    return bytes_uploaded, count


def create_episode(req: EpisodeCreateRequest) -> EpisodeCreateResult:
    _validate_create(req)
    index = _next_episode_index()
    device = ld.select_device()
    local_root = ld.make_temp_root()
    try:
        # Rotate which real source episode supplies the footage so successive
        # recordings show different teleoperation clips (wraps in hf_source).
        robot_type = ld.build_episode(
            root=local_root,
            repo_id=f"local/ep_{index:06d}",
            task=req.task,
            num_cameras=req.num_cameras,
            num_frames=req.num_frames,
            fps=req.fps,
            resolution=req.resolution,
            device=device,
            source_episode=index,
        )
        bytes_uploaded, count = _upload_tree(local_root, index)
    finally:
        _cleanup_root(local_root)

    logger.info(
        "Episode created: index=%d task=%s frames=%d cameras=%d device=%s "
        "robot_type=%s bytes=%d",
        index, req.task, req.num_frames, req.num_cameras, device, robot_type, bytes_uploaded,
    )
    episode = get_episode(index)
    return EpisodeCreateResult(
        episode=episode,
        bytes_uploaded=bytes_uploaded,
        bytes_uploaded_human=humanize_bytes(bytes_uploaded),
        object_count=count,
        device=device,
    )


def _download_meta(index: int) -> str:
    """Download just the small meta/ files of an episode to a temp dir and
    return the local v3 root so the lerobot reader can parse them."""
    local_root = ld.make_temp_root()
    meta_prefix = _meta_prefix(index)
    for obj in list_keys(meta_prefix):
        rel = obj["key"][len(_episode_prefix(index)):]
        dest = Path(local_root) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(get_object_bytes(obj["key"]))
    return local_root


def get_episode(index: int) -> Episode:
    prefix = _episode_prefix(index)
    objs = list_keys(prefix)
    if not objs:
        raise EpisodeError(f"Episode {index} not found", status_code=404)

    local_root = _download_meta(index)
    try:
        info = ld.read_info(local_root)
        meta_rows = ld.read_episodes_meta(local_root)
    finally:
        _cleanup_root(local_root)

    return episode_meta.build_episode(index, prefix, objs, info, meta_rows)


def list_episodes(task: str | None = None) -> list[Episode]:
    prefix = f"{settings.dataset_prefix}episodes/"
    indices = set()
    for obj in list_keys(prefix):
        seg = obj["key"][len(prefix):].split("/", 1)[0]
        if seg.startswith("ep_"):
            try:
                indices.add(int(seg[3:]))
            except ValueError:
                continue
    episodes = [get_episode(i) for i in sorted(indices)]
    if task:
        episodes = [e for e in episodes if e.task == task]
    return episodes


def relabel_episode(index: int, task: str) -> Episode:
    """Re-tag the episode's task annotation in its v3 meta on B2.

    Frames are immutable; the task label is index metadata. We rewrite the
    meta/episodes parquet `tasks` column and meta/tasks table in place.
    """
    if task not in PRESET_TASKS:
        raise EpisodeError(f"Unknown task '{task}'")
    get_episode(index)  # 404s if missing

    local_root = _download_meta(index)
    try:
        episode_meta.rewrite_task(local_root, task)
        for path in sorted(Path(local_root).rglob("*")):
            if path.is_file():
                rel = path.relative_to(local_root).as_posix()
                key = f"{_episode_prefix(index)}{rel}"
                put_bytes(key, path.read_bytes(), _content_type(key))
    finally:
        _cleanup_root(local_root)
    logger.info("Episode relabeled: index=%d task=%s", index, task)
    return get_episode(index)


def delete_episode(index: int) -> int:
    """Delete the episode's shards/meta from B2 — scoped to its prefix only."""
    prefix = _episode_prefix(index)
    if not list_keys(prefix):
        raise EpisodeError(f"Episode {index} not found", status_code=404)
    deleted = delete_prefix(prefix)
    logger.info("Episode deleted: index=%d prefix=%s objects=%d", index, prefix, deleted)
    return deleted


def camera_video_url(index: int, camera: str) -> str:
    ep = get_episode(index)
    for v in ep.videos:
        if v.camera == camera:
            return presign_key(v.key)
    raise EpisodeError(f"Camera '{camera}' not found on episode {index}", status_code=404)


def head_episode_bytes(index: int) -> int:
    return sum(o["size"] for o in list_keys(_episode_prefix(index)))


def episode_meta_exists(index: int) -> bool:
    return head_size(f"{_meta_prefix(index)}info.json") is not None

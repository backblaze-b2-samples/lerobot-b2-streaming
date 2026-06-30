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
import re
import shutil
from pathlib import Path

from app.config import settings
from app.repo import (
    delete_prefix,
    get_object_bytes,
    head_size,
    hf_source,
    list_keys,
    presign_key,
    put_bytes,
    upload_path,
)
from app.repo import lerobot_dataset as ld
from app.repo.hf_source import SOURCE_REPO_ID as DEFAULT_SOURCE_REPO_ID
from app.repo.hf_source import RealSourceUnavailable
from app.service import episode_meta
from app.types import (
    Episode,
    EpisodeCreateRequest,
    EpisodeCreateResult,
    SourceInfo,
)
from app.types.episodes import (
    MAX_EPISODE_FRAMES,
    PRESET_TASKS,
    SOURCE_REPO_ID_PATTERN,
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


def _validate_source_repo_id(repo_id: str | None) -> None:
    if repo_id is not None and not re.match(SOURCE_REPO_ID_PATTERN, repo_id):
        raise EpisodeError(
            f"Invalid source dataset '{repo_id}' — expected a HuggingFace repo id "
            "like 'owner/name'"
        )


def _validate_create(req: EpisodeCreateRequest) -> None:
    if req.task not in PRESET_TASKS:
        raise EpisodeError(f"Unknown task '{req.task}'")
    _validate_source_repo_id(req.source_repo_id)
    if req.max_frames is not None and not (1 <= req.max_frames <= MAX_EPISODE_FRAMES):
        raise EpisodeError(f"max_frames must be between 1 and {MAX_EPISODE_FRAMES}")


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
    source = req.source_repo_id or DEFAULT_SOURCE_REPO_ID
    # The synthetic-frame fallback exists only so the DEFAULT source never crashes
    # the demo offline. A user-chosen source must fail loudly rather than silently
    # substituting synthetic frames the user didn't ask for.
    allow_synth_fallback = req.source_repo_id in (None, DEFAULT_SOURCE_REPO_ID)
    try:
        # The recorded shape (cameras/fps/resolution/dims/length) is derived from
        # the source itself inside build_episode. We only rotate which real source
        # episode supplies the footage so successive recordings differ, and pass an
        # optional frame cap.
        robot_type = ld.build_episode(
            root=local_root,
            repo_id=f"local/ep_{index:06d}",
            task=req.task,
            device=device,
            source_episode=index,
            source_repo_id=source,
            allow_synth_fallback=allow_synth_fallback,
            max_frames=req.max_frames,
        )
        bytes_uploaded, count = _upload_tree(local_root, index)
    except RealSourceUnavailable as e:
        raise EpisodeError(
            f"Couldn't load dataset '{source}'. It must be a public LeRobot v3 "
            f"dataset ({e}).",
            400,
        ) from e
    finally:
        _cleanup_root(local_root)

    episode = get_episode(index)
    logger.info(
        "Episode created: index=%d task=%s frames=%d cameras=%d device=%s "
        "source=%s robot_type=%s bytes=%d",
        index, req.task, episode.num_frames, episode.num_cameras, device, source,
        robot_type, bytes_uploaded,
    )
    return EpisodeCreateResult(
        episode=episode,
        bytes_uploaded=bytes_uploaded,
        bytes_uploaded_human=humanize_bytes(bytes_uploaded),
        object_count=count,
        device=device,
    )


def inspect_source(repo_id: str | None) -> SourceInfo:
    """Probe a source dataset and report the real shape an ingest will reproduce.

    Powers the create form's preview + early validation: a chosen source that
    can't load (private/gated/not-v3/offline) surfaces a 400 here, before any
    recording is attempted, so the user sees exactly what will be recorded.
    """
    _validate_source_repo_id(repo_id)
    source = repo_id or DEFAULT_SOURCE_REPO_ID
    try:
        info = hf_source.inspect_source(source)
    except RealSourceUnavailable as e:
        raise EpisodeError(
            f"Couldn't load dataset '{source}'. It must be a public LeRobot v3 "
            f"dataset ({e}).",
            400,
        ) from e
    return SourceInfo(**info)


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

"""Real-robot camera footage source for episode ingest.

This module is the REAL frame source that replaced the old synthetic moving
gradients. It lazily downloads a couple of episodes from a PUBLIC HuggingFace
LeRobot **v3** dataset and exposes real decoded camera frames — at the source's
**native shape** — in the form `lerobot_dataset.build_episode` expects.

The source is selectable per recording (`repo_id=`); a recording reproduces the
source's real cameras, fps, native resolution, state/action dims, and episode
length rather than imposing synthetic knobs. `inspect_source` reports that shape
so the UI can preview/validate an ingest before it runs.

Only a couple of episodes are pulled (via the SDK's partial-download path) and
cached per repo_id, so a multi-episode ingest never re-downloads and switching
sources never thrashes an already-loaded one. LeRobot / torch are imported
lazily so the FastAPI app still boots without the ML requirements installed.

This stays a separate `repo/` module (not folded into `lerobot_dataset.py`) so
neither file crosses the 300-line invariant.
"""

import logging
import os
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# The DEFAULT small, public real-robot v3 dataset and the episodes we pull from
# it. The source is selectable per recording (see `inspect_source` / `real_frame`
# `repo_id=`); these constants are only the fallback/default when the caller
# doesn't choose one.
SOURCE_REPO_ID = "lerobot/svla_so101_pickplace"
SOURCE_EPISODES = [0, 1]
# Used only when a loaded dataset doesn't report its own robot_type.
SOURCE_ROBOT_TYPE = "so100_follower"

# Isolate the Hub cache from the user's default LeRobot home and keep it OUTSIDE
# the repo tree (gitignored regardless) so the committed diff never grows.
_CACHE_DIR = os.environ.get("LEROBOT_REAL_CACHE", "/tmp/lerobot-b2-streaming-real")


class RealSourceUnavailable(RuntimeError):
    """Raised when a Hub dataset cannot be loaded (offline / Hub error / not a
    usable v3 dataset).

    For the DEFAULT source the caller treats this as the signal to fall back to
    synthetic frames so the live demo never hard-crashes offline. For a
    user-CHOSEN source it is surfaced as an error instead (no silent fallback).
    """


class _SourceCamera(NamedTuple):
    """One source camera stream: its full feature key + native frame size."""

    name: str  # e.g. "observation.images.up"
    height: int
    width: int


class _Source(NamedTuple):
    """One loaded source dataset plus the indices/metadata needed to sample it."""

    dataset: object  # a lerobot LeRobotDataset
    episode_rows: list[list[int]]  # absolute hf_dataset row indices per source episode
    cameras: list[_SourceCamera]  # the real cameras, in order, at native size
    fps: int
    robot_type: str
    state_dim: int
    action_dim: int
    task: str | None


# Per-repo cache, populated on first use and keyed by HF repo_id, so switching
# the source dataset never re-downloads or thrashes an already-loaded one.
_CACHE: dict[str, _Source] = {}


def _vec_dim(sample, key: str, default: int = 6) -> int:
    """Width of a 1-D vector feature in a decoded sample, else `default`."""
    val = sample.get(key) if hasattr(sample, "get") else None
    if val is None:
        return default
    import numpy as np

    return int(np.asarray(val).reshape(-1).shape[0]) or default


def _sample_task(sample) -> str | None:
    """The source's real task label on a decoded sample (for UI prefill)."""
    val = sample.get("task") if hasattr(sample, "get") else None
    return val if isinstance(val, str) and val else None


def _load_source(repo_id: str = SOURCE_REPO_ID, episodes: list[int] | None = None) -> _Source:
    """Load + cache one source dataset (and its per-episode row index) once per repo_id."""
    cached = _CACHE.get(repo_id)
    if cached is not None:
        return cached

    import numpy as np
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    Path(_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_LEROBOT_HOME", _CACHE_DIR)
    eps = episodes if episodes is not None else SOURCE_EPISODES
    try:
        ds = LeRobotDataset(repo_id, episodes=eps)
    except Exception as e:  # network / Hub / decode failure / not a v3 dataset
        raise RealSourceUnavailable(f"cannot load {repo_id}: {e}") from e

    cam_keys = list(ds.meta.camera_keys)
    if not cam_keys:
        raise RealSourceUnavailable(f"{repo_id} has no camera streams to record")

    ep_index = np.asarray(ds.hf_dataset["episode_index"])
    rows: list[list[int]] = []
    for ep in sorted(set(int(x) for x in ep_index.tolist())):
        rows.append([int(i) for i in np.where(ep_index == ep)[0].tolist()])

    # Decode the first frame once to read ground-truth shapes/dims — more robust
    # than parsing `meta.features` across SDK versions. Cached for the run.
    try:
        sample0 = ds[rows[0][0]]
    except Exception as e:  # decode backend / corrupt shard
        raise RealSourceUnavailable(f"cannot decode {repo_id}: {e}") from e

    cameras: list[_SourceCamera] = []
    for k in cam_keys:
        shp = tuple(int(x) for x in sample0[k].shape)  # (C, H, W)
        h, w = (shp[1], shp[2]) if len(shp) == 3 else (0, 0)
        cameras.append(_SourceCamera(name=k, height=h, width=w))

    src = _Source(
        dataset=ds,
        episode_rows=rows,
        cameras=cameras,
        fps=int(ds.fps),
        robot_type=(ds.meta.robot_type or SOURCE_ROBOT_TYPE),
        state_dim=_vec_dim(sample0, "observation.state"),
        action_dim=_vec_dim(sample0, "action"),
        task=_sample_task(sample0),
    )
    _CACHE[repo_id] = src
    logger.info(
        "Real source loaded: repo=%s episodes=%d cameras=%s fps=%s robot_type=%s "
        "state_dim=%d action_dim=%d",
        repo_id, len(rows), [(c.name, c.height, c.width) for c in cameras],
        src.fps, src.robot_type, src.state_dim, src.action_dim,
    )
    return src


def ensure_loaded(repo_id: str = SOURCE_REPO_ID) -> None:
    """Eagerly load a source (raising RealSourceUnavailable if it can't)."""
    _load_source(repo_id)


def source_fps(repo_id: str = SOURCE_REPO_ID) -> int | None:
    """Native fps of a loaded source dataset, else None if not yet loaded."""
    src = _CACHE.get(repo_id)
    return src.fps if src is not None else None


def num_source_episodes(repo_id: str = SOURCE_REPO_ID) -> int:
    """How many source episodes are cached for a repo (after a successful load)."""
    src = _CACHE.get(repo_id)
    return len(src.episode_rows) if src is not None else 0


def source_robot_type(repo_id: str = SOURCE_REPO_ID) -> str:
    """robot_type of a loaded source dataset (its real value), else the default."""
    src = _CACHE.get(repo_id)
    return src.robot_type if src is not None else SOURCE_ROBOT_TYPE


def num_source_episode_frames(source_episode: int = 0, repo_id: str = SOURCE_REPO_ID) -> int:
    """Frame count of one source episode (loads the source if needed)."""
    src = _load_source(repo_id)
    return len(src.episode_rows[source_episode % len(src.episode_rows)])


def inspect_source(repo_id: str = SOURCE_REPO_ID, source_episode: int = 0) -> dict:
    """Load (caching) a source and report the real shape an ingest will reproduce.

    Raises RealSourceUnavailable if it can't be loaded/decoded — the caller turns
    that into a clear error for a user-chosen source.
    """
    src = _load_source(repo_id)
    rows = src.episode_rows[source_episode % len(src.episode_rows)]
    return {
        "repo_id": repo_id,
        "robot_type": src.robot_type,
        "fps": src.fps,
        "cameras": [
            {
                "name": c.name.replace("observation.images.", ""),
                "height": c.height,
                "width": c.width,
            }
            for c in src.cameras
        ],
        "num_cameras": len(src.cameras),
        "episode_frames": len(rows),
        "state_dim": src.state_dim,
        "action_dim": src.action_dim,
        "task": src.task,
    }


def source_cameras(repo_id: str = SOURCE_REPO_ID) -> list[dict]:
    """Per-camera native shapes a build must declare in its v3 features."""
    src = _load_source(repo_id)
    return [{"height": c.height, "width": c.width} for c in src.cameras]


def source_state_action_dims(repo_id: str = SOURCE_REPO_ID) -> tuple[int, int]:
    src = _load_source(repo_id)
    return src.state_dim, src.action_dim


def _to_uint8_hwc(chw_float_tensor):
    """Convert a CHW float32 [0,1] torch tensor to a native HxWx3 uint8 image —
    NO resize, so the source's real resolution/aspect ratio is preserved."""
    import numpy as np

    arr = chw_float_tensor.detach().cpu().numpy()  # (3, H, W) in [0, 1]
    arr = np.transpose(arr, (1, 2, 0))  # (H, W, 3)
    return np.clip(arr * 255.0, 0, 255).astype(np.uint8)


def _vec_or_placeholder(sample, key: str, dim: int, t: int, total: int):
    """The source's real `key` vector verbatim (when it matches `dim`), else a
    smooth deterministic placeholder of width `dim` if the source lacks it."""
    import numpy as np

    val = sample.get(key) if hasattr(sample, "get") else None
    if val is not None:
        vec = np.asarray(val, dtype=np.float32).reshape(-1)
        if vec.shape[0] == dim:
            return vec
        out = np.zeros((dim,), dtype=np.float32)
        n = min(dim, vec.shape[0])
        out[:n] = vec[:n]
        return out
    phase = t / max(total - 1, 1)
    base = np.array(
        [
            np.sin(phase * np.pi * 2),
            np.cos(phase * np.pi * 2),
            phase,
            np.sin(phase * np.pi),
            np.cos(phase * np.pi),
            1.0 - phase,
        ],
        dtype=np.float32,
    )
    out = np.zeros((dim,), dtype=np.float32)
    out[: min(dim, 6)] = base[: min(dim, 6)]
    return out


def real_frame(t: int, total: int, source_episode: int = 0, repo_id: str = SOURCE_REPO_ID):
    """Return one frame dict of REAL robot footage at the source's native shape.

    - ``observation.images.cam_{i}``: native HxWx3 uint8 image from source camera
      ``i`` — **exactly** the source's cameras, in order (no cycling, no
      duplication, no forced square).
    - ``observation.state`` / ``action``: the source's real vectors verbatim
      (only a derived placeholder if the source lacks the stream).

    Frames index directly into ``source_episode`` (clamped to its last frame,
    never looped) so a recording is a faithful prefix of the real episode.
    """
    src = _load_source(repo_id)
    rows = src.episode_rows[source_episode % len(src.episode_rows)]
    row = rows[t] if t < len(rows) else rows[-1]
    sample = src.dataset[row]

    frame: dict = {}
    for i, cam in enumerate(src.cameras):
        frame[f"observation.images.cam_{i}"] = _to_uint8_hwc(sample[cam.name])
    frame["observation.state"] = _vec_or_placeholder(
        sample, "observation.state", src.state_dim, t, total
    )
    frame["action"] = _vec_or_placeholder(sample, "action", src.action_dim, t, total)
    return frame

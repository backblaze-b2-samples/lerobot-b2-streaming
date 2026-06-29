"""Real-robot camera footage source for episode ingest.

This module is the REAL frame source that replaces the old synthetic moving
gradients. It lazily downloads a couple of episodes from a small, PUBLIC
HuggingFace LeRobot dataset and exposes real decoded camera frames in the same
shape `lerobot_dataset.build_episode` expects.

Chosen dataset: ``lerobot/svla_so101_pickplace`` — a real teleoperated SO-101
arm (robot_type ``so100_follower``), genuine **LeRobotDataset v3.0** (no
conversion needed), ~86 MB total, 2 cameras (``observation.images.up`` /
``...side``, 480x640), 30 fps, and 6-DoF ``observation.state`` / ``action``
vectors that line up exactly with this app's 6-DoF schema.

Only episodes 0 and 1 are pulled (via the SDK's partial-download path) and they
are cached once at module level, so a multi-episode ingest never re-downloads.
LeRobot / torch / PIL are imported lazily so the FastAPI app still boots without
the ML requirements installed (the structural tests never import the heavy SDK).

This stays a separate ``repo/`` module (not folded into ``lerobot_dataset.py``)
so neither file crosses the 300-line invariant.
"""

import logging
import os
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# The DEFAULT small, public real-robot v3 dataset and the episodes we pull from
# it. The source is selectable per recording (see `real_frame(repo_id=…)`); these
# constants are only the fallback/default when the caller doesn't choose one.
SOURCE_REPO_ID = "lerobot/svla_so101_pickplace"
SOURCE_EPISODES = [0, 1]
# Reflected into the built episode's v3 metadata in place of "synthetic".
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


class _Source(NamedTuple):
    """One loaded source dataset plus the indices/metadata needed to sample it."""

    dataset: object  # a lerobot LeRobotDataset
    episode_rows: list[list[int]]  # absolute hf_dataset row indices per source episode
    cameras: list[str]  # e.g. ["observation.images.up", "observation.images.side"]
    fps: int
    robot_type: str


# Per-repo cache, populated on first use and keyed by HF repo_id, so switching
# the source dataset never re-downloads or thrashes an already-loaded one.
_CACHE: dict[str, _Source] = {}


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

    cameras = list(ds.meta.camera_keys)
    if not cameras:
        raise RealSourceUnavailable(f"{repo_id} has no camera streams to record")

    ep_index = np.asarray(ds.hf_dataset["episode_index"])
    rows: list[list[int]] = []
    for ep in sorted(set(int(x) for x in ep_index.tolist())):
        rows.append([int(i) for i in np.where(ep_index == ep)[0].tolist()])

    src = _Source(
        dataset=ds,
        episode_rows=rows,
        cameras=cameras,
        fps=int(ds.fps),
        robot_type=ds.meta.robot_type or SOURCE_ROBOT_TYPE,
    )
    _CACHE[repo_id] = src
    logger.info(
        "Real source loaded: repo=%s episodes=%d cameras=%s fps=%s robot_type=%s",
        repo_id, len(rows), src.cameras, src.fps, src.robot_type,
    )
    return src


def ensure_loaded(repo_id: str = SOURCE_REPO_ID) -> None:
    """Eagerly load a source (raising RealSourceUnavailable if it can't).

    Used by `lerobot_dataset.build_episode` to decide real-vs-fallback up front.
    """
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


def _resize_square(chw_float_tensor, resolution: int):
    """Convert a CHW float32 [0,1] torch tensor to a square HxWx3 uint8 image.

    Uses PIL (already a dependency) for the resize — no new packages.
    """
    import numpy as np
    from PIL import Image

    arr = chw_float_tensor.detach().cpu().numpy()  # (3, H, W) in [0, 1]
    arr = np.transpose(arr, (1, 2, 0))  # (H, W, 3)
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB").resize((resolution, resolution), Image.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


def real_frame(
    num_cameras: int,
    resolution: int,
    t: int,
    total: int,
    device: str,
    source_episode: int = 0,
    repo_id: str = SOURCE_REPO_ID,
):
    """Return one frame dict of REAL robot footage, shaped like ``_synth_frame``.

    - ``observation.images.cam_{c}``: square ``resolution`` HxWx3 uint8 images
      from the source dataset's cameras (cycled if the source has fewer cameras
      than requested).
    - ``observation.state`` / ``action``: the source's real 6-DoF vectors when
      present, otherwise a derived placeholder (the VIDEO is the real asset).

    ``repo_id`` selects which source dataset to draw from (defaults to the
    built-in one). Frames are indexed into the chosen ``source_episode``; if
    ``num_frames`` exceeds the source episode length we loop over it. ``device``
    is accepted for signature parity with ``_synth_frame`` but real frames are
    decoded on CPU by the SDK regardless (video decode never needs a GPU).
    """
    src = _load_source(repo_id)
    rows = src.episode_rows[source_episode % len(src.episode_rows)]
    row = rows[t % len(rows)]
    sample = src.dataset[row]

    frame: dict = {}
    for cam in range(num_cameras):
        src_key = src.cameras[cam % len(src.cameras)]
        frame[f"observation.images.cam_{cam}"] = _resize_square(sample[src_key], resolution)

    # 6-dim sources pass through verbatim; anything else (or a source missing the
    # stream entirely) is coerced/derived so the v3 6-DoF feature schema holds.
    frame["observation.state"] = _fit_6dof(_opt_vec(sample, "observation.state"), t, total)
    frame["action"] = _fit_6dof(_opt_vec(sample, "action"), t, total)
    return frame


def _opt_vec(sample, key: str):
    """A float32 vector for ``key`` in a decoded sample, or an empty array if the
    source lacks that stream (so ``_fit_6dof`` derives a placeholder)."""
    import numpy as np

    val = sample.get(key) if hasattr(sample, "get") else None
    if val is None:
        return np.zeros((0,), dtype=np.float32)
    return np.asarray(val, dtype=np.float32)


def _fit_6dof(vec, t: int, total: int):
    """Coerce a source vector to the app's float32 (6,) schema.

    If the source vector is already 6-dim we use it verbatim (the real signal).
    Otherwise derive a smooth, deterministic 6-DoF vector from the timestep so
    the v3 feature schema stays satisfied — the VIDEO is the asset that must be
    real, not this fallback vector.
    """
    import numpy as np

    if vec.shape == (6,):
        return vec.astype(np.float32)
    phase = t / max(total - 1, 1)
    return np.array(
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

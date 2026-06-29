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

logger = logging.getLogger(__name__)

# The small, public real-robot v3 dataset and the episodes we pull from it.
SOURCE_REPO_ID = "lerobot/svla_so101_pickplace"
SOURCE_EPISODES = [0, 1]
# Reflected into the built episode's v3 metadata in place of "synthetic".
SOURCE_ROBOT_TYPE = "so100_follower"

# Isolate the Hub cache from the user's default LeRobot home and keep it OUTSIDE
# the repo tree (gitignored regardless) so the committed diff never grows.
_CACHE_DIR = os.environ.get("LEROBOT_REAL_CACHE", "/tmp/lerobot-b2-streaming-real")

# Module-level singletons populated on first use.
_dataset = None  # the loaded LeRobotDataset (episodes 0,1)
_episode_rows: list[list[int]] = []  # absolute hf_dataset row indices per source episode
_source_cameras: list[str] = []  # e.g. ["observation.images.up", "observation.images.side"]


class RealSourceUnavailable(RuntimeError):
    """Raised when the Hub dataset cannot be loaded (offline / Hub error).

    The caller treats this as the signal to fall back to synthetic frames for a
    live interactive demo, so the app never hard-crashes offline.
    """


def _load_source():
    """Load + cache the source dataset and its per-episode row index once."""
    global _dataset, _episode_rows, _source_cameras
    if _dataset is not None:
        return _dataset

    import numpy as np
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    Path(_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_LEROBOT_HOME", _CACHE_DIR)
    try:
        ds = LeRobotDataset(SOURCE_REPO_ID, episodes=SOURCE_EPISODES)
    except Exception as e:  # network / Hub / decode failure
        raise RealSourceUnavailable(f"cannot load {SOURCE_REPO_ID}: {e}") from e

    ep_index = np.asarray(ds.hf_dataset["episode_index"])
    rows: list[list[int]] = []
    for ep in sorted(set(int(x) for x in ep_index.tolist())):
        rows.append([int(i) for i in np.where(ep_index == ep)[0].tolist()])

    _dataset = ds
    _episode_rows = rows
    _source_cameras = list(ds.meta.camera_keys)
    logger.info(
        "Real source loaded: repo=%s episodes=%d cameras=%s fps=%s robot_type=%s",
        SOURCE_REPO_ID, len(rows), _source_cameras, ds.fps, ds.meta.robot_type,
    )
    return ds


def ensure_loaded() -> None:
    """Eagerly load the source (raising RealSourceUnavailable if it can't).

    Used by `lerobot_dataset.build_episode` to decide real-vs-fallback up front.
    """
    _load_source()


def source_fps() -> int | None:
    """Native fps of the source dataset (after the source is loaded), else None."""
    return int(_dataset.fps) if _dataset is not None else None


def num_source_episodes() -> int:
    """How many source episodes are cached (after a successful load)."""
    return len(_episode_rows)


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
):
    """Return one frame dict of REAL robot footage, shaped like ``_synth_frame``.

    - ``observation.images.cam_{c}``: square ``resolution`` HxWx3 uint8 images
      from the source dataset's cameras (cycled if the source has fewer cameras
      than requested).
    - ``observation.state`` / ``action``: the source's real 6-DoF vectors.

    Frames are indexed into the chosen ``source_episode``; if ``num_frames``
    exceeds the source episode length we loop over it. ``device`` is accepted
    for signature parity with ``_synth_frame`` but real frames are decoded on
    CPU by the SDK regardless (video decode never needs a GPU).
    """
    import numpy as np

    ds = _load_source()
    rows = _episode_rows[source_episode % len(_episode_rows)]
    row = rows[t % len(rows)]
    sample = ds[row]

    frame: dict = {}
    for cam in range(num_cameras):
        src_key = _source_cameras[cam % len(_source_cameras)]
        frame[f"observation.images.cam_{cam}"] = _resize_square(sample[src_key], resolution)

    state = np.asarray(sample["observation.state"], dtype=np.float32)
    action = np.asarray(sample["action"], dtype=np.float32)
    # The source's state/action are already 6-dim here; guard anyway so a
    # differently-shaped source can't break the v3 6-DoF feature schema.
    frame["observation.state"] = _fit_6dof(state, t, total)
    frame["action"] = _fit_6dof(action, t, total)
    return frame


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

"""Adapter over the real HuggingFace LeRobot v3 dataset SDK.

This (with `hf_source.py`) is the only place LeRobot / torch are imported. It
builds a teleoperation episode on local disk with the genuine
`LeRobotDataset.create() -> add_frame -> save_episode -> finalize` v3 API, then
reads back the v3 metadata (info.json + meta/episodes/*.parquet).

The camera frames are REAL teleoperation footage: `hf_source.real_frame()`
pulls a couple of episodes from the small public `lerobot/svla_so101_pickplace`
dataset (a real SO-101 arm) and serves resized frames + the source's real 6-DoF
state/action vectors. `_synth_frame` (procedural moving gradients) remains ONLY
as a clearly-logged offline fallback so the live interactive demo never
hard-crashes when the Hub is unreachable — it is never the seeded demo data.

Heavy ML imports are lazy so the FastAPI app boots and the structural tests run
without torch/lerobot installed (they live in the separate requirements-ml.txt
step).
"""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from app.repo import hf_source
from app.types.episodes import MAX_EPISODE_FRAMES

logger = logging.getLogger(__name__)

# Shape of the synthetic offline fallback (default source only — it can't inspect
# a source it failed to load). Clearly logged; never seeded as demo data.
_FALLBACK_CAMERAS = 2
_FALLBACK_RESOLUTION = 256
_FALLBACK_FPS = 30
_FALLBACK_FRAMES = 60
_FALLBACK_DOF = 6


def select_device() -> str:
    """Auto-detect compute device: CUDA -> Apple MPS -> CPU (default CPU).

    Tensor ops follow the detected device; video encode/decode always runs on
    CPU via ffmpeg/torchcodec regardless. Never hard-requires a GPU.
    """
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _dof_names(dim: int) -> list[str]:
    """v3 requires one name per vector element. 6-DoF gets the readable pose
    names; any other width (e.g. a 14-DoF bimanual arm) gets generic motor names."""
    if dim == 6:
        return ["x", "y", "z", "roll", "pitch", "yaw"]
    return [f"motor_{i}" for i in range(dim)]


def _features(cameras: list[dict], state_dim: int, action_dim: int) -> dict:
    """v3 feature schema derived from the source: per-camera video at the source's
    native (non-square) size + state/action vectors at the source's real dims."""
    feats: dict = {
        "observation.state": {
            "dtype": "float32",
            "shape": (state_dim,),
            "names": _dof_names(state_dim),
        },
        "action": {
            "dtype": "float32",
            "shape": (action_dim,),
            "names": _dof_names(action_dim),
        },
    }
    for i, cam in enumerate(cameras):
        feats[f"observation.images.cam_{i}"] = {
            "dtype": "video",
            "shape": (cam["height"], cam["width"], 3),
            "names": ["height", "width", "channels"],
        }
    return feats


def _synth_frame(num_cameras: int, resolution: int, t: int, total: int, device: str):
    """Procedurally generate one frame: a moving gradient per camera + a smooth
    6-DoF state/action vector. Offline fallback only; tensors are built on the
    detected device, then moved to CPU/numpy for LeRobot (which stores numpy)."""
    import numpy as np
    import torch

    phase = t / max(total - 1, 1)
    frame: dict = {}
    for cam in range(num_cameras):
        # A diagonal sweep whose hue offset differs per camera.
        yy, xx = torch.meshgrid(
            torch.linspace(0, 1, resolution, device=device),
            torch.linspace(0, 1, resolution, device=device),
            indexing="ij",
        )
        base = (xx + yy) * 0.5
        r = ((base + phase + cam * 0.2) % 1.0)
        g = ((base + phase * 0.7 + cam * 0.4) % 1.0)
        b = ((base * 0.5 + phase + cam * 0.6) % 1.0)
        img = torch.stack([r, g, b], dim=-1)  # (H, W, 3) on device
        img = (img * 255).clamp(0, 255).to(torch.uint8).cpu().numpy()
        frame[f"observation.images.cam_{cam}"] = img

    state = np.array(
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
    # Action = next-step delta (simple, smooth).
    action = (state * 0.98).astype(np.float32)
    frame["observation.state"] = state
    frame["action"] = action
    return frame


class _BuildSpec(NamedTuple):
    """Everything `build_episode` needs, derived from the source so the v3
    features and the per-frame data always agree."""

    frame_fn: Callable[[int, int], dict]
    robot_type: str
    source_label: str
    cameras: list[dict]  # [{height, width}] in order
    fps: int
    state_dim: int
    action_dim: int
    num_frames: int


def _bounded(available: int, max_frames: int | None) -> int:
    """Frames to record: the source episode length, lowered by an optional
    `max_frames` and always clamped to the MAX_EPISODE_FRAMES safety ceiling."""
    cap = MAX_EPISODE_FRAMES if max_frames is None else min(max_frames, MAX_EPISODE_FRAMES)
    return max(1, min(available, cap))


def _resolve_frame_source(
    source_repo_id: str = hf_source.SOURCE_REPO_ID,
    allow_synth_fallback: bool = True,
    source_episode: int = 0,
    device: str = "cpu",
    max_frames: int | None = None,
) -> _BuildSpec:
    """Resolve the footage source and the exact shape to record.

    PRIMARY: real footage from `hf_source`, mirroring the source's cameras, fps,
    native resolution, state/action dims, and episode length. FALLBACK (logged,
    fixed shape): the procedural `_synth_frame` gradient, used ONLY when
    `allow_synth_fallback` and the source can't load, so the live demo never
    crashes offline. A user-chosen source (`allow_synth_fallback=False`) re-raises
    instead of silently substituting synthetic frames.
    """
    try:
        info = hf_source.inspect_source(source_repo_id, source_episode)
    except hf_source.RealSourceUnavailable as e:
        if not allow_synth_fallback:
            raise
        logger.warning(
            "Real footage source %s unavailable (%s); FALLING BACK to synthetic "
            "gradient frames for this episode. This must not be used as seeded "
            "demo data.", source_repo_id, e,
        )

        def synth(t: int, total: int):
            return _synth_frame(_FALLBACK_CAMERAS, _FALLBACK_RESOLUTION, t, total, device)

        cams = [
            {"height": _FALLBACK_RESOLUTION, "width": _FALLBACK_RESOLUTION}
        ] * _FALLBACK_CAMERAS
        return _BuildSpec(
            synth, "synthetic", "synthetic-fallback", cams, _FALLBACK_FPS,
            _FALLBACK_DOF, _FALLBACK_DOF, _bounded(_FALLBACK_FRAMES, max_frames),
        )

    def real(t: int, total: int):
        return hf_source.real_frame(
            t, total, source_episode=source_episode, repo_id=source_repo_id,
        )

    return _BuildSpec(
        real, info["robot_type"], source_repo_id,
        [{"height": c["height"], "width": c["width"]} for c in info["cameras"]],
        info["fps"], info["state_dim"], info["action_dim"],
        _bounded(info["episode_frames"], max_frames),
    )


def build_episode(
    root: str,
    repo_id: str,
    task: str,
    device: str,
    source_episode: int = 0,
    source_repo_id: str = hf_source.SOURCE_REPO_ID,
    allow_synth_fallback: bool = True,
    max_frames: int | None = None,
) -> str:
    """Build a one-episode v3 dataset on disk at `root` using the real API.

    The recorded shape (cameras, fps, native resolution, state/action dims,
    length) is **derived from the source** via `_resolve_frame_source`, not
    imposed — so an external user's data is reproduced faithfully. `max_frames`
    optionally caps the length. Returns the written `robot_type` (the source's
    real type, or "synthetic" for the offline fallback).
    """
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    spec = _resolve_frame_source(
        source_repo_id=source_repo_id,
        allow_synth_fallback=allow_synth_fallback,
        source_episode=source_episode,
        device=device,
        max_frames=max_frames,
    )

    ds = LeRobotDataset.create(
        repo_id=repo_id,
        fps=spec.fps,
        features=_features(spec.cameras, spec.state_dim, spec.action_dim),
        root=root,
        robot_type=spec.robot_type,
        use_videos=True,
    )
    for t in range(spec.num_frames):
        frame = spec.frame_fn(t, spec.num_frames)
        frame["task"] = task
        ds.add_frame(frame)
    ds.save_episode()
    ds.finalize()
    logger.info(
        "Built v3 episode: frames=%d cameras=%d fps=%d source=%s robot_type=%s",
        spec.num_frames, len(spec.cameras), spec.fps, spec.source_label, spec.robot_type,
    )
    return spec.robot_type


def make_temp_root() -> str:
    """A throwaway local dir for a v3 dataset. Returns a `root/` subpath that
    does NOT yet exist, because `LeRobotDataset.create()` makes the root itself
    with exist_ok=False. Callers should rmtree the parent (the returned path's
    parent) when done."""
    parent = tempfile.mkdtemp(prefix="lerobot-ep-")
    return str(Path(parent) / "root")


def read_info(root: str) -> dict:
    """Read meta/info.json — the v3 schema, fps, and path templates."""
    import json

    return json.loads((Path(root) / "meta" / "info.json").read_text())


def read_episodes_meta(root: str):
    """Read the v3 meta/episodes/*.parquet rows (offsets, lengths, tasks).

    Returns a list of plain dicts (one per episode) so callers in higher
    layers never touch pyarrow/pandas directly.
    """
    import pandas as pd

    rows: list[dict] = []
    ep_dir = Path(root) / "meta" / "episodes"
    for pq in sorted(ep_dir.rglob("*.parquet")):
        df = pd.read_parquet(pq)
        rows.extend(df.to_dict(orient="records"))
    return rows


def read_tasks(root: str) -> list[str]:
    """Read the task labels from meta/tasks.parquet (v3) or tasks.jsonl (legacy)."""
    import json

    import pandas as pd

    pq = Path(root) / "meta" / "tasks.parquet"
    if pq.exists():
        df = pd.read_parquet(pq)
        if df.index.name == "task" or "task" not in df.columns:
            return list(df.index.astype(str))
        return list(df["task"].astype(str))
    jl = Path(root) / "meta" / "tasks.jsonl"
    if jl.exists():
        return [json.loads(line)["task"] for line in jl.read_text().splitlines() if line.strip()]
    return []

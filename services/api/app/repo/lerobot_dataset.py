"""Adapter over the real HuggingFace LeRobot v3 dataset SDK.

This is the only place LeRobot / torch are imported. It synthesizes a
teleoperation episode (procedural multi-camera frames + numpy state/action),
builds it on local disk with the genuine
`LeRobotDataset.create() -> add_frame -> save_episode -> finalize` v3 API, and
reads back the v3 metadata (info.json + meta/episodes/*.parquet). Heavy ML
imports are lazy so the FastAPI app boots and the structural tests run without
torch/lerobot installed (they live in the separate requirements-ml.txt step).
"""

import tempfile
from pathlib import Path


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


def _features(num_cameras: int, resolution: int) -> dict:
    """v3 feature schema: per-camera video + a 6-DoF state/action vector."""
    feats: dict = {
        "observation.state": {
            "dtype": "float32",
            "shape": (6,),
            "names": ["x", "y", "z", "roll", "pitch", "yaw"],
        },
        "action": {
            "dtype": "float32",
            "shape": (6,),
            "names": ["x", "y", "z", "roll", "pitch", "yaw"],
        },
    }
    for cam in range(num_cameras):
        feats[f"observation.images.cam_{cam}"] = {
            "dtype": "video",
            "shape": (resolution, resolution, 3),
            "names": ["height", "width", "channels"],
        }
    return feats


def camera_keys(num_cameras: int) -> list[str]:
    return [f"observation.images.cam_{c}" for c in range(num_cameras)]


def _synth_frame(num_cameras: int, resolution: int, t: int, total: int, device: str):
    """Procedurally generate one frame: a moving gradient per camera + a
    smooth state/action vector. Deterministic-ish per timestep so the demo
    video has visible motion. Tensors are created on the detected device,
    then moved to CPU/numpy for LeRobot (which stores numpy)."""
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


def build_episode(
    root: str,
    repo_id: str,
    task: str,
    num_cameras: int,
    num_frames: int,
    fps: int,
    resolution: int,
    device: str,
) -> None:
    """Build a one-episode v3 dataset on disk at `root` using the real API."""
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=_features(num_cameras, resolution),
        root=root,
        robot_type="synthetic",
        use_videos=True,
    )
    for t in range(num_frames):
        frame = _synth_frame(num_cameras, resolution, t, num_frames, device)
        frame["task"] = task
        ds.add_frame(frame)
    ds.save_episode()
    ds.finalize()


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

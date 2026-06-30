"""Pure helpers for parsing/rewriting LeRobot v3 episode metadata.

Kept separate from the orchestration in `service/episodes.py` so each file
stays small and the v3-format specifics live in one place. No boto3/lerobot
imports — operates on already-downloaded local v3 trees and parsed dicts.
"""

from pathlib import Path

from app.types import Episode, EpisodeCameraVideo
from app.types.formatting import humanize_bytes


def first_task(row: dict) -> str:
    """Extract the episode's task label from a v3 episodes-parquet row."""
    tasks = row.get("tasks")
    if isinstance(tasks, (list, tuple)) and len(tasks):
        return str(tasks[0])
    if hasattr(tasks, "tolist"):
        lst = tasks.tolist()
        if lst:
            return str(lst[0])
    return str(row.get("task", "unknown"))


def camera_from_video_key(key: str, prefix: str) -> str:
    rest = key[len(prefix):]  # videos/<cam>/chunk-.../file-....mp4
    parts = rest.split("/")
    if len(parts) >= 2 and parts[0] == "videos":
        return parts[1].replace("observation.images.", "")
    return "cam"


def build_episode(
    index: int,
    prefix: str,
    objs: list[dict],
    info: dict,
    meta_rows: list[dict],
) -> Episode:
    """Assemble an Episode model from v3 meta + B2 object listing."""
    total_bytes = sum(o["size"] for o in objs)
    row = meta_rows[0] if meta_rows else {}
    cams = [k for k in info.get("features", {}) if str(k).startswith("observation.images.")]
    # Native (non-square) frame size of the first camera — v3 video shape is
    # (height, width, channels).
    frame_height, frame_width = 0, 0
    for k in cams:
        shp = info["features"][k].get("shape") or []
        if len(shp) >= 2:
            frame_height, frame_width = int(shp[0]), int(shp[1])
            break

    videos: list[EpisodeCameraVideo] = []
    for o in objs:
        if o["key"].endswith(".mp4"):
            cam = camera_from_video_key(o["key"], prefix)
            videos.append(
                EpisodeCameraVideo(
                    camera=cam,
                    key=o["key"],
                    size_bytes=o["size"],
                    size_human=humanize_bytes(o["size"]),
                )
            )

    return Episode(
        episode_index=index,
        task=first_task(row),
        num_frames=int(row.get("length", info.get("total_frames", 0)) or 0),
        fps=int(info.get("fps", 0)),
        num_cameras=len(cams),
        cameras=[c.replace("observation.images.", "") for c in cams],
        frame_height=frame_height,
        frame_width=frame_width,
        dataset_from_index=int(row.get("dataset_from_index", 0) or 0),
        dataset_to_index=int(row.get("dataset_to_index", 0) or 0),
        size_bytes=total_bytes,
        size_human=humanize_bytes(total_bytes),
        prefix=prefix,
        videos=videos,
    )


def rewrite_task(local_root: str, task: str) -> None:
    """Rewrite the task label across an episode's v3 meta parquet files."""
    import pandas as pd

    ep_dir = Path(local_root) / "meta" / "episodes"
    for pq_path in ep_dir.rglob("*.parquet"):
        df = pd.read_parquet(pq_path)
        if "tasks" in df.columns:
            df["tasks"] = [[task] for _ in range(len(df))]
        if "task" in df.columns:
            df["task"] = task
        df.to_parquet(pq_path)
    tasks_pq = Path(local_root) / "meta" / "tasks.parquet"
    if tasks_pq.exists():
        tdf = pd.read_parquet(tasks_pq).reset_index()
        col = "task" if "task" in tdf.columns else tdf.columns[0]
        tdf[col] = task
        tdf.to_parquet(tasks_pq, index=False)

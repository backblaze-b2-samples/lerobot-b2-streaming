from pydantic import BaseModel, Field


class WorkerStreamStats(BaseModel):
    """Per-worker result of a concurrent streaming run."""

    worker_id: int
    task: str | None = None
    episodes_streamed: int
    frames_decoded: int
    bytes_fetched: int
    bytes_fetched_human: str
    throughput_frames_per_s: float
    elapsed_s: float


class StreamRunStats(BaseModel):
    """Aggregate result of a streaming run (single or N-worker).

    The headline invariant the UI shows: bytes_fetched (only the ranged-GET
    bytes pulled from B2) is far smaller than total_dataset_bytes.
    """

    workers: int
    episodes_streamed: int
    frames_decoded: int
    # Marquee numbers — the whole point of the bridge.
    bytes_fetched: int
    bytes_fetched_human: str
    total_dataset_bytes: int
    total_dataset_bytes_human: str
    fetch_ratio: float = Field(
        description="bytes_fetched / total_dataset_bytes (≪ 1.0 is the win)"
    )
    elapsed_s: float
    throughput_frames_per_s: float
    train_loss_start: float | None = None
    train_loss_end: float | None = None
    device: str
    per_worker: list[WorkerStreamStats] = Field(default_factory=list)


class StreamRunRequest(BaseModel):
    """Start a streaming run over a chosen episode or task split."""

    episode_index: int | None = None
    task: str | None = None
    workers: int = 1
    max_frames: int = 0  # 0 = all frames in the selection


class DatasetStats(BaseModel):
    """Dashboard aggregations over the dataset prefix on B2."""

    total_episodes: int
    total_frames: int
    total_cameras: int
    total_tasks: int
    total_dataset_bytes: int
    total_dataset_bytes_human: str
    tasks: list[str]


class DailyEpisodeCount(BaseModel):
    date: str
    episodes: int

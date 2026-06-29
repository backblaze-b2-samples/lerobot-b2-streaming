from datetime import datetime

from pydantic import BaseModel, Field

# Finite option sets surfaced as selectors in the create/edit UI. Kept here so
# the API can validate against the same lists the frontend renders.
PRESET_TASKS = [
    "Pick up the cube",
    "Stack blocks",
    "Open the drawer",
    "Push the button",
]
ALLOWED_NUM_CAMERAS = [1, 2, 3]
ALLOWED_NUM_FRAMES = [30, 60, 120]
ALLOWED_FPS = [10, 30]
ALLOWED_RESOLUTIONS = [128, 256]

# Curated, vetted-public **LeRobot v3** datasets offered in the source-dataset
# dropdown. The first entry is the default. All confirmed codebase_version v3.0
# with video cameras. A "Custom repo…" option in the UI accepts any other public
# `owner/name`; this list is just the convenient, known-good shortlist.
PRESET_SOURCES = [
    "lerobot/svla_so101_pickplace",
    "lerobot/svla_so100_pickplace",
    "lerobot/aloha_sim_insertion_human",
    "lerobot/pusht",
]
# HuggingFace `owner/name` repo id (used to validate a custom source).
SOURCE_REPO_ID_PATTERN = r"^[A-Za-z0-9][\w.-]*/[\w.-]+$"


class EpisodeCameraVideo(BaseModel):
    """One per-camera MP4 shard belonging to an episode."""

    camera: str
    key: str
    size_bytes: int
    size_human: str


class Episode(BaseModel):
    """A single teleoperation demonstration episode in a v3 dataset on B2."""

    episode_index: int
    task: str
    num_frames: int
    fps: int
    num_cameras: int
    cameras: list[str]
    resolution: int
    # Frame offsets into the shared data shard (v3 byte/frame offsets).
    dataset_from_index: int
    dataset_to_index: int
    size_bytes: int
    size_human: str
    prefix: str
    created_at: datetime | None = None
    videos: list[EpisodeCameraVideo] = Field(default_factory=list)


class EpisodeCreateRequest(BaseModel):
    """Create form payload — record a real-footage episode and push it to B2."""

    task: str
    num_cameras: int = 2
    num_frames: int = 60
    fps: int = 30
    resolution: int = 256
    # HuggingFace v3 dataset the real footage is drawn from. None → server
    # default (kept for API back-compat; the form always sends an explicit one).
    source_repo_id: str | None = None


class EpisodeUpdateRequest(BaseModel):
    """Edit form payload — relabel the episode's task annotation."""

    task: str


class EpisodeCreateResult(BaseModel):
    episode: Episode
    bytes_uploaded: int
    bytes_uploaded_human: str
    object_count: int
    device: str


class EpisodeFormOptions(BaseModel):
    """Finite option sets + safe defaults the create/edit forms render."""

    tasks: list[str]
    num_cameras: list[int]
    num_frames: list[int]
    fps: list[int]
    resolutions: list[int]
    sources: list[str]
    default_task: str
    default_num_cameras: int
    default_num_frames: int
    default_fps: int
    default_resolution: int
    default_source: str

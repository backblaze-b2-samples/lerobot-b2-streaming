from datetime import datetime

from pydantic import BaseModel, Field

# Task labels surfaced as a selector in the create/edit UI. Kept here so the API
# can validate against the same list the frontend renders.
PRESET_TASKS = [
    "Pick up the cube",
    "Stack blocks",
    "Open the drawer",
    "Push the button",
]

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

# Safety ceiling on how many frames a single ingest records, so a long source
# episode still finishes "in a few seconds" and the uploaded tree stays bounded.
# The recording otherwise mirrors the source (cameras/fps/resolution/length); the
# only knob is an optional `max_frames` that can lower this further.
MAX_EPISODE_FRAMES = 600


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
    # Native frame size of the first camera (sources are not square - e.g.
    # 480x640 - so height and width are reported separately, not as one int).
    frame_height: int
    frame_width: int
    # Frame offsets into the shared data shard (v3 byte/frame offsets).
    dataset_from_index: int
    dataset_to_index: int
    size_bytes: int
    size_human: str
    prefix: str
    created_at: datetime | None = None
    videos: list[EpisodeCameraVideo] = Field(default_factory=list)


class SourceCamera(BaseModel):
    """One real camera stream in a source dataset (native, non-square size)."""

    name: str
    height: int
    width: int


class SourceInfo(BaseModel):
    """The real shape of a source dataset, used to preview/validate an ingest
    before it runs. The recording reproduces exactly these values."""

    repo_id: str
    robot_type: str
    fps: int
    cameras: list[SourceCamera]
    num_cameras: int
    # Frames in the first source episode — the full length that will be recorded
    # unless `max_frames`/the ceiling lowers it.
    episode_frames: int
    state_dim: int
    action_dim: int
    task: str | None = None


class EpisodeCreateRequest(BaseModel):
    """Create form payload — record a real-footage episode and push it to B2.

    The recorded shape (cameras, fps, resolution, state/action dims, length) is
    derived from the source dataset itself; the only inputs are which source to
    draw from, the task label, and an optional cap on frames."""

    # HuggingFace v3 dataset the real footage is drawn from. None → server
    # default (kept for API back-compat; the form always sends an explicit one).
    source_repo_id: str | None = None
    task: str
    # Optional cap on frames recorded; None → the full first source episode
    # (still bounded by MAX_EPISODE_FRAMES).
    max_frames: int | None = None


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
    """Option sets + safe defaults the create/edit forms render. The recording
    shape is no longer a set of knobs — it comes from the chosen source — so this
    is just the task labels, the curated source shortlist, and the frames ceiling."""

    tasks: list[str]
    sources: list[str]
    default_task: str
    default_source: str
    max_frames: int

"""Dashboard aggregations over the dataset prefix on B2.

Reads the v3 metadata of every episode under the dataset prefix and rolls it up
into the cards / chart / table the dashboard renders. No boto3/lerobot imports
here — it composes the episodes service.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from app.service import episodes as ep_service
from app.types import DailyEpisodeCount, DatasetStats
from app.types.formatting import humanize_bytes


def get_dataset_stats() -> DatasetStats:
    episodes = ep_service.list_episodes()
    total_frames = sum(e.num_frames for e in episodes)
    total_bytes = sum(e.size_bytes for e in episodes)
    cameras: set[str] = set()
    tasks: set[str] = set()
    for e in episodes:
        cameras.update(e.cameras)
        tasks.add(e.task)
    return DatasetStats(
        total_episodes=len(episodes),
        total_frames=total_frames,
        total_cameras=len(cameras),
        total_tasks=len(tasks),
        total_dataset_bytes=total_bytes,
        total_dataset_bytes_human=humanize_bytes(total_bytes),
        tasks=sorted(tasks),
    )


def get_ingest_activity(days: int = 7) -> list[DailyEpisodeCount]:
    """Episodes recorded per day, derived from each episode's objects'
    LastModified. We approximate recorded-at by the episode's earliest object."""
    from app.repo import list_files

    prefix = f"{ep_service.settings.dataset_prefix}episodes/"
    today = datetime.now(UTC).date()
    cutoff = today - timedelta(days=days - 1)
    counts: dict[str, int] = defaultdict(int)

    # list_files returns FileMetadata with uploaded_at; group by episode and
    # keep the earliest date we see as that episode's "recorded" day.
    seen_eps: dict[str, str] = {}
    for f in list_files(prefix=prefix, max_keys=1000):
        seg = f.key[len(prefix):].split("/", 1)[0]
        if not seg.startswith("ep_"):
            continue
        iso = f.uploaded_at.date().isoformat()
        cur = seen_eps.get(seg)
        if cur is None or iso < cur:
            seen_eps[seg] = iso

    for iso in seen_eps.values():
        if iso >= cutoff.isoformat():
            counts[iso] += 1

    return [
        DailyEpisodeCount(
            date=(cutoff + timedelta(days=i)).isoformat(),
            episodes=counts.get((cutoff + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]

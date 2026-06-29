<!-- last_verified: 2026-06-29 -->
# Feature: Dataset index & query

## Purpose
List and filter episodes by task label or id, reading the v3 metadata
(`meta/info.json`, `meta/episodes/*.parquet`, `meta/tasks.parquet`) straight
from B2 — no separate database.

## Used By
- UI: `/episodes` (list + task filter), dashboard table
- API: `GET /episodes?task=...`, `GET /episodes/{index}`

## Core Functions
- `services/api/app/service/episodes.py` — `list_episodes()`, `get_episode()`
- `services/api/app/service/episode_meta.py` — `build_episode()`, `first_task()`
- `services/api/app/repo/lerobot_dataset.py` — `read_info()`, `read_episodes_meta()`, `read_tasks()`
- `services/api/app/repo/b2_objects.py` — `list_keys()`, `get_object_bytes()`

## Inputs
- `task`: optional task label (filter)
- `index`: episode index (detail)

## Outputs
- `Episode[]` / `Episode` (task, frames, fps, cameras, resolution, frame range,
  size, prefix, video shards)

## Flow
- List the episode prefixes under `lerobot/episodes/`
- For each, download the small `meta/` files and parse the v3 tables
- Assemble `Episode` models; filter by task if requested

## Edge Cases
- Episode missing → 404
- Empty dataset → empty list
- Legacy `tasks.jsonl` vs v3 `tasks.parquet` → both handled

## UX States
- Loading: skeleton rows
- Empty: "No episodes in this dataset yet" with a record CTA
- Error: inline `ErrorState` with Retry

## Verification
- Quick verify: `pnpm test:api`
- Pass criteria: list/detail return parsed v3 metadata for real episodes on B2

## Related Docs
- [Episode library](episode-library.md)
- [Episode ingest](episode-ingest.md)

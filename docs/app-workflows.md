<!-- last_verified: 2026-06-29 -->
# App Workflows

User journeys inside the application. The primary entity is the **Episode**
(one teleoperation demonstration); all five lifecycle verbs are reachable in the
UI.

## Record an Episode (create)

- User navigates to `/episodes/new`
- Picks the **source dataset** — a curated dropdown of vetted public LeRobot v3
  datasets, or "Custom repo…" to type any other public HuggingFace `owner/name`
  (the bring-your-own-data path). Then picks finite parameters from selectors —
  task (preset list), cameras (1–3), frames (30/60/120), fps (10/30), resolution
  (128/256). Safe defaults are shown as guidance (no autofill button).
- Submits → backend pulls the chosen source's first episodes from the Hub (cached
  per repo), builds a genuine LeRobot v3 dataset locally (device auto
  CUDA→MPS→CPU), encodes per-camera MP4s, and uploads the v3 tree to the episode's
  B2 prefix. A custom source that can't load (private/gated/not-v3) returns a
  clear error rather than recording synthetic frames.
- On success: toast with bytes uploaded + object count, redirect to the detail page
- See: [Episode ingest](features/episode-ingest.md)

## Browse the Dataset Library (read)

- User navigates to `/episodes` — the sample-scoped explorer over the dataset
  prefix (distinct from the full-bucket `/files`)
- Filters by task label via a selector
- Opens an episode to `/episodes/[id]`: per-camera MP4 players (presigned URLs),
  frames/fps/cameras/resolution/frame-range, B2 size + prefix
- See: [Dataset index & query](features/dataset-index-query.md), [Episode library](features/episode-library.md)

## Relabel an Episode (edit)

- On `/episodes/[id]`, the Edit card is pre-filled with the real task
- User picks a new task from the same preset selector and saves
- Backend rewrites the task annotation in the episode's v3 metadata on B2
  (frames are immutable; the label is index metadata)
- Toast confirms; the detail + lists reflect the new label

## Delete an Episode (delete)

- From a list row action or the detail page, the user confirms in a dialog
- Backend deletes every object under that episode's prefix only
  (`lerobot/episodes/ep_NNNNNN/`) — no other episode is touched
- Toast reports the object count removed

## Stream from B2 (run)

- User navigates to `/stream` (or "Stream" from an episode)
- Picks a single episode or a task split, and a worker count (1/2/4/8)
- Backend reads v3 metadata, then ranged-GETs only the needed Parquet row-groups
  and video byte-ranges, decodes frames, and runs a mini training step
- The UI shows **bytes fetched from B2 via Range vs total dataset size**
  (the headline ratio), frames decoded, throughput, device, and per-worker stats
- See: [B2 streaming](features/b2-streaming.md), [Concurrent streaming](features/concurrent-streaming.md)

## View Dashboard

- User navigates to `/` (home)
- Dataset-stats cards (episodes, frames, cameras, tasks, total bytes on B2),
  ingest activity chart, recent-episodes table
- See: [Dashboard](features/dashboard.md)

## Retained file surface

- `/upload` and `/files` keep the starter-kit upload + full-bucket browse flows
  intact, so the bucket stays fully inspectable. See
  [File Upload](features/file-upload.md), [File Browser](features/file-browser.md).

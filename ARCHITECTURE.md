<!-- last_verified: 2026-06-29 -->
# Architecture

## Components

- **apps/web/** — Next.js 16 frontend (App Router, Tailwind v4, shadcn/ui)
  - Dashboard with dataset stats, ingest activity, recent episodes
  - `/episodes` sample-scoped explorer + `/episodes/[id]` detail (per-camera MP4, metadata, relabel, delete)
  - `/episodes/new` record form (real-footage v3 episode → B2)
  - `/stream` streaming run surface (single + N-worker, bytes-fetched vs total)
  - Retained `/files` full-bucket explorer + `/upload`
  - Dark mode via `next-themes`
- **services/api/** — FastAPI backend (layered architecture)
  - Episode CRUD + relabel + delete, dataset stats, streaming runs
  - B2 S3 integration via boto3; LeRobot v3 build/read + the streaming bridge contained in `repo/`
  - Health check endpoint with B2 connectivity verification
  - Structured JSON logging with request tracing; Prometheus-format `/metrics`
- **packages/shared/** — TypeScript type definitions mirroring the Pydantic models

## LeRobotDataset v3 on-disk layout

The genuine LeRobot v3 format (built locally, mirrored to B2 per episode):

```
meta/info.json                       schema, fps, path templates
meta/stats.json                      normalization stats
meta/tasks.parquet                   task label -> id (jsonl in legacy)
meta/episodes/chunk-000/file-000.parquet   per-episode lengths, tasks, and
                                     byte/frame offsets into the shared shards
data/chunk-000/file-000.parquet      many episodes per file (state/action rows)
videos/<camera>/chunk-000/file-000.mp4   many episodes per camera shard
```

The `meta/episodes/*.parquet` rows carry `dataset_from_index` / `dataset_to_index`
(frame range in the data shard), `data/chunk_index` / `data/file_index` (which
data shard), and per-video `videos/<key>/from_timestamp` / `to_timestamp`. These
offsets are exactly what the streaming bridge reads to plan ranged GETs.

## B2 prefix layout

Everything lives under `DATASET_PREFIX` (default `lerobot/`), one v3 tree per
episode so deletes are naturally prefix-scoped:

```
lerobot/episodes/ep_000000/
  meta/info.json
  meta/episodes/chunk-000/file-000.parquet
  meta/tasks.parquet
  data/chunk-000/file-000.parquet
  videos/observation.images.cam_0/chunk-000/file-000.mp4
  videos/observation.images.cam_1/chunk-000/file-000.mp4
```

## Backend Layering

```
types/     Pydantic models — no logic, no imports from other layers
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Data access (boto3 B2 client, LeRobot SDK, streaming bridge)
  |
service/   Business logic — calls repo, returns types
  |
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` → `config` → `repo` → `service` → `runtime`
2. No backward imports
3. `boto3` only in `repo/`; LeRobot / torch usage also contained in `repo/`
4. All boundary data uses Pydantic models
5. Each file stays under 300 lines

### Directory Structure

```
services/api/
  main.py                  App entrypoint, middleware, router registration
  requirements.txt         Base deps (no torch) — boots + structural tests
  requirements-ml.txt      ML deps (lerobot, torch, torchcodec) — pinned window
  app/
    types/                 Pydantic models (Episode, StreamRunStats, FileMetadata…)
    config/                Settings (B2_* + DATASET_PREFIX); endpoint derived from region
    repo/
      b2_client.py         Shared boto3 S3 client (custom UA) + file-upload ops
      b2_objects.py        Dataset/streaming S3 ops: ranged GET, list, head, delete-prefix
      lerobot_dataset.py   Real v3 build (create→add_frame→save_episode→finalize) + read
      hf_source.py         Real-robot footage source (lerobot/svla_so101_pickplace);
                           synthetic gradient kept only as a logged offline fallback
      b2_stream.py         The B2/S3 streaming bridge (ranged-GET Parquet + video)
    service/
      episodes.py          Episode lifecycle orchestration
      episode_meta.py      v3 metadata parsing / task rewrite helpers
      streaming.py         Single + concurrent streaming runs, mini training step
      dataset_stats.py     Dashboard aggregations
      files.py / upload.py / metadata.py  retained file surface
    runtime/
      episodes.py          Episode CRUD + relabel + form options + source inspect + dataset stats
      streaming.py         POST /stream
      files.py / upload.py / health.py / metrics.py  retained
  tests/                   pytest (structural + streaming contract + file tests)
```

## Streaming data flow (marquee)

`StreamingLeRobotDataset` is HuggingFace-Hub-only (no S3 support — open feature
request huggingface/lerobot#764). This sample implements the bridge the v3 format
was designed for:

1. Browser → `POST /stream` (episode index or task split, worker count).
2. `service/streaming.py` resolves the selection to episode indices and reads each
   episode's v3 metadata from B2 (small full GETs).
3. For each episode, `repo/b2_stream.py`:
   - reads the data Parquet **footer** with a small ranged GET to locate the
     row-group byte span, then ranged-GETs **only** that span and slices the
     episode's rows by frame index;
   - ranged-GETs the camera MP4's byte window and decodes frames via torchcodec.
4. The streamed rows feed a **mini** one-step MLP update (the training data path,
   not a full policy train).
5. The response reports `bytes_fetched`, `total_dataset_bytes`, `fetch_ratio`
   (≪ 1.0), throughput, and per-worker stats. Concurrent workers each take a
   different task split from the shared B2 bucket.

## Other data flows

- **Inspect source** (preview/validate): Browser → `GET /episodes/source-info?repo_id=…`
  → `repo/hf_source.inspect_source` loads (and caches) the source and reports its
  **real shape** — cameras + native resolution, fps, state/action dims, episode
  length, robot_type — or a 400 if it can't load. The create form previews this
  and blocks recording until it succeeds.
- **Ingest**: Browser → `POST /episodes` (`source_repo_id`, `task`, optional
  `max_frames`) → service builds a v3 episode locally that **mirrors the source's
  real shape** rather than imposing one (`repo/hf_source.py` lazily pulls a couple
  of episodes of the chosen dataset — default `lerobot/svla_so101_pickplace` —
  and caches them per `repo_id`; device auto CUDA→MPS→CPU) → uploads the tree to
  the episode's B2 prefix. For the **default** source, if the Hub is unreachable
  the build falls back to fixed-shape procedural frames (logged) so the live demo
  never crashes; a **user-chosen** source that can't load fails loud with a 400.
  `robot_type` records which source was used (the source's real type, or
  `synthetic` for the fallback). The recorded v3 features therefore carry the
  source's **native (non-square) per-camera resolution** and its real state/action
  dimensionality — not a forced 256² / 6-DoF shape.
- **Index/list**: Browser → `GET /episodes` → reads `meta/*` for each episode.
- **Read detail**: `GET /episodes/{i}` + `GET /episodes/{i}/video?camera=…` (presigned MP4).
- **Edit (relabel)**: `PATCH /episodes/{i}` → rewrites the task in the v3 meta on B2.
- **Delete**: `DELETE /episodes/{i}` → `delete_prefix(...)` scoped to that episode.

## Device selection

`repo/lerobot_dataset.select_device()` returns the first available of
**CUDA → Apple MPS → CPU**, defaulting to CPU. Tensor ops follow the detected
device; video encode/decode always runs on CPU via torchcodec/PyAV. No GPU is
ever required.

## Deployment

- **Local dev** — `pnpm dev` runs both services via `concurrently` (web :3000, API :8000).
- **Railway** — two services from the same repo; see `infra/railway/README.md`
  (the API build must also `pip install -r requirements-ml.txt`).

## Data Stores

- **Backblaze B2** — object storage (S3-compatible API). No application database;
  B2 is the sole data store, and v3 metadata on B2 is the dataset index.

## Observability

- Structured JSON logging with `request_id`; request timing middleware
- `/metrics` (Prometheus format) and `/health` (B2 connectivity)

## Canonical Files

- Streaming bridge: `services/api/app/repo/b2_stream.py`
- LeRobot v3 adapter: `services/api/app/repo/lerobot_dataset.py`
- Real-robot footage source: `services/api/app/repo/hf_source.py`
- Dataset/streaming S3 ops: `services/api/app/repo/b2_objects.py`
- Episode orchestration: `services/api/app/service/episodes.py`
- Streaming runs: `services/api/app/service/streaming.py`
- Routers: `services/api/app/runtime/episodes.py`, `streaming.py`
- Config (region-derived endpoint): `services/api/app/config/settings.py`
- Frontend API client / hooks: `apps/web/src/lib/api-client.ts`, `apps/web/src/lib/queries.ts`
- Shared types: `packages/shared/src/types.ts`

## References

- [docs/SECURITY.md](docs/SECURITY.md), [docs/RELIABILITY.md](docs/RELIABILITY.md)
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions

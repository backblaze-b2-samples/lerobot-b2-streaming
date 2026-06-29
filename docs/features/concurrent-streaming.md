<!-- last_verified: 2026-06-29 -->
# Feature: Concurrent multi-worker streaming (Serve/Query)

## Purpose
Demonstrate the shared-backend / fleet story: spawn N concurrent stream readers,
each pulling a different episode/task split from the same B2 bucket, and report
per-worker plus total throughput and bytes fetched.

## Used By
- UI: `/stream` (worker selector 1 | 2 | 4 | 8)
- API: `POST /stream` with `workers > 1`

## Core Functions
- `services/api/app/service/streaming.py` — `run_stream()` shards the selected
  episodes round-robin across a `ThreadPoolExecutor`; `_run_worker()` per worker
- `apps/web/src/components/stream/stream-runner.tsx` — per-worker table

## Inputs
- `workers`: 1 | 2 | 4 | 8 (capped at 8 and at the number of episodes)
- `task` / `episode_index`: the selection to split

## Outputs
- `StreamRunStats.per_worker[]` (episodes, frames, bytes fetched, fps per worker)
  plus the aggregate totals and bytes-fetched-vs-total ratio

## Flow
- Resolve the selection to episode indices
- Round-robin episodes into N buckets; run each bucket on its own worker thread,
  each issuing independent S3 ranged GETs against the shared bucket
- Aggregate per-worker and total stats

## Edge Cases
- Fewer episodes than workers → workers scale down to the episode count
- `workers` out of range → 400

## UX States
- Loading: "Streaming from B2…"
- Loaded: aggregate cards + a per-worker throughput table (shown when workers > 1)

## Verification
- End-to-end: record ≥2 episodes, run with `workers=2`, confirm per-worker rows
  and total bytes_fetched < total_dataset_bytes
- Quick verify: `pnpm test:api`

## Related Docs
- [B2 streaming](b2-streaming.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)

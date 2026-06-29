<!-- last_verified: 2026-06-29 -->
# Feature: B2 S3 chunk-by-chunk streaming (marquee)

## Purpose
Stream an episode (or task split) back from B2 by fetching **only** the Parquet
row-groups and video byte-ranges it needs via S3 ranged GETs — never the whole
dataset — and feed it into a mini training loop.

## The honest framing (LeRobot#764)
`StreamingLeRobotDataset` is **HuggingFace-Hub-only**: it streams from a `repo_id`
and has no S3 / custom-endpoint / arbitrary-root support — that is the open
feature request [huggingface/lerobot#764](https://github.com/huggingface/lerobot/issues/764).
This sample does **not** use it for B2. Instead it implements the bridge the v3
format was designed for, using the byte/frame offsets v3 records per episode. Do
not imply LeRobot natively streams from B2.

## Used By
- UI: `/stream`
- API: `POST /stream`

## Core Functions
- `services/api/app/repo/b2_stream.py` — `fetch_data_rows()` (ranged-GET Parquet
  footer + row-group span, slice the episode's rows), `fetch_video_range()`
  (ranged-GET MP4 window, decode via torchcodec)
- `services/api/app/service/streaming.py` — `run_stream()`, mini one-step MLP update
- `services/api/app/repo/b2_objects.py` — `get_object_range()` (S3 `Range` request)

## Inputs
- `episode_index`: optional single episode
- `task`: optional task split
- `workers`: 1 | 2 | 4 | 8
- `max_frames`: optional cap

## Outputs
- `StreamRunStats` — `bytes_fetched` vs `total_dataset_bytes`, `fetch_ratio`
  (≪ 1.0), frames decoded, throughput, device, mini-train loss, per-worker stats

## Flow
- Resolve the selection to episode indices; read each episode's v3 metadata from B2
- For each episode: ranged-GET the data Parquet's footer to find the row-group
  byte span, ranged-GET that span only, slice rows by frame index; ranged-GET the
  camera MP4's byte window and decode frames
- Feed the streamed state/action rows into a one-step MLP update
- Aggregate and return the bytes-fetched-vs-total invariant

## Edge Cases
- Episode/selection empty → 404
- Video decode best-effort → a decode failure is logged, frame count falls back to rows
- No GPU → runs on CPU; never requires a GPU

## UX States
- Loading: "Streaming from B2…"
- Error: inline `ErrorState` with Retry
- Loaded: a prominent bytes-fetched / total bar + stat cards

## Verification
- Contract test: `services/api/tests/test_streaming_contract.py` (ranged GET +
  bridge helpers present; device defaults to CPU without torch)
- End-to-end: record an episode, stream it, assert ≥1 frame decoded and
  bytes_fetched < total_dataset_bytes
- Quick verify: `pnpm test:api`

## Related Docs
- [Concurrent streaming](concurrent-streaming.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)

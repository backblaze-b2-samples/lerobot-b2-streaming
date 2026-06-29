<!-- last_verified: 2026-06-29 -->
# Feature: Episode ingest → B2

## Purpose
Record a synthetic teleoperation episode with the genuine LeRobot v3 API and
persist the whole dataset tree to Backblaze B2.

## Used By
- UI: `/episodes/new` (create form)
- API: `POST /episodes`, `GET /episodes/options`

## Core Functions
- `services/api/app/repo/lerobot_dataset.py` — `build_episode()` wraps the real
  `LeRobotDataset.create() → add_frame → save_episode → finalize`; `select_device()`
- `services/api/app/service/episodes.py` — `create_episode()` orchestration + upload
- `services/api/app/repo/b2_objects.py` — `upload_path()` / `put_bytes()`
- `apps/web/src/components/episodes/episode-create-form.tsx`

## Inputs
- `task`: enum (preset list) — selector
- `num_cameras`: 1 | 2 | 3 — selector
- `num_frames`: 30 | 60 | 120 — selector
- `fps`: 10 | 30 — selector
- `resolution`: 128 | 256 — selector

Finite fields use selectors; safe defaults (2 cameras · 60 frames · 30 fps ·
256×256) are shown as guidance, never autofilled.

## Outputs
- `EpisodeCreateResult` (the new `Episode`, bytes uploaded, object count, device)
- Side effect: a full v3 tree written under `lerobot/episodes/ep_NNNNNN/` on B2

## Flow
- Validate finite parameters server-side
- Pick the next episode index; auto-detect device (CUDA→MPS→CPU)
- Build the v3 dataset on disk with the real LeRobot API; encode MP4 per camera
- Upload the tree to the episode's B2 prefix; clean up the temp dir
- Read the episode back from B2 metadata and return it

## Edge Cases
- Invalid finite value → 400 with a clear message
- No GPU → builds on CPU (default); never errors on a missing GPU
- ML deps not installed → import error surfaces at create time (documented setup step)

## UX States
- Loading: "Recording & uploading…" button state
- Error: toast with the API message
- Success: toast + redirect to the episode detail page

## Verification
- Contract test: `services/api/tests/test_streaming_contract.py` (build helpers present)
- End-to-end: record an episode, confirm 7 objects under its prefix on B2
- Quick verify: `pnpm test:api`
- Pass criteria: tests green; a create call returns a real `Episode` with frames > 0

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [B2 streaming](b2-streaming.md)

<!-- last_verified: 2026-06-29 -->
# Feature: Episode ingest → B2

## Purpose
Record a teleoperation episode from **real robot camera footage** with the
genuine LeRobot v3 API and persist the whole dataset tree to Backblaze B2.

The frames come from a small **public** LeRobot dataset on the HuggingFace Hub —
`lerobot/svla_so101_pickplace`, a real teleoperated SO-101 arm (robot_type
`so100_follower`), already in v3.0 format (~86 MB, 2 cameras at 480×640, 30 fps,
6-DoF state/action). Only a couple of its episodes (0 and 1) are pulled via the
SDK's partial-download path and cached once, so ingest never downloads the whole
dataset and successive recordings reuse the cache. Frames are resized to the
requested square resolution; the source cameras map to `cam_0..cam_{n-1}` (cycled
if fewer source cameras than requested); the real 6-DoF `observation.state` /
`action` vectors are used verbatim.

A procedural moving-gradient generator (`_synth_frame`) survives **only** as a
clearly-logged offline fallback so the live interactive demo never hard-crashes
when the Hub is unreachable. `build_episode` returns the `robot_type` it wrote
(`so100_follower` for real footage, `synthetic` for the fallback) so callers can
tell real demo data apart from the fallback. The seeded demo data is always real.

## Used By
- UI: `/episodes/new` (create form)
- API: `POST /episodes`, `GET /episodes/options`

## Core Functions
- `services/api/app/repo/hf_source.py` — `real_frame()` serves real resized
  camera frames + 6-DoF state/action; `ensure_loaded()` lazily caches the source
- `services/api/app/repo/lerobot_dataset.py` — `build_episode()` wraps the real
  `LeRobotDataset.create() → add_frame → save_episode → finalize` and selects the
  real footage source (with a synthetic fallback); `select_device()`
- `services/api/app/service/episodes.py` — `create_episode()` orchestration + upload
  (rotates `source_episode` so successive recordings show different real clips)
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
- Resolve the frame source: lazily load + cache the real Hub footage (primary),
  or fall back to procedural frames (logged) if the Hub is unreachable
- Build the v3 dataset on disk with the real LeRobot API; encode MP4 per camera
- Upload the tree to the episode's B2 prefix; clean up the temp dir
- Read the episode back from B2 metadata and return it

## Edge Cases
- Invalid finite value → 400 with a clear message
- No GPU → builds on CPU (default); never errors on a missing GPU
- ML deps not installed → import error surfaces at create time (documented setup step)
- Hub unreachable / source can't load → logged fallback to procedural frames so
  the live demo doesn't crash; `robot_type` is then `synthetic` (never seeded as
  demo data)

## UX States
- Loading: "Recording & uploading…" button state
- Error: toast with the API message
- Success: toast + redirect to the episode detail page

## Verification
- Contract test: `services/api/tests/test_streaming_contract.py` (build helpers
  present; real footage wired as primary, synthetic only as fallback)
- Source unit tests: `services/api/tests/test_hf_source.py` — hermetic checks
  (signature parity, 6-DoF coercion, fallback wiring) plus an INTEGRATION test
  that decodes a real frame, skipped unless `RUN_HF_INTEGRATION=1` (keeps
  `pnpm test:api` / `pnpm check:structure` network-free)
- End-to-end: record an episode, confirm 6–7 objects under its prefix on B2 and
  `meta/info.json` `robot_type == "so100_follower"` (real, not the fallback)
- Quick verify: `pnpm test:api`
- Pass criteria: tests green; a create call returns a real `Episode` with frames > 0

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [B2 streaming](b2-streaming.md)

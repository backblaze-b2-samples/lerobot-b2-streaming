<!-- last_verified: 2026-06-29 -->
# Feature: Episode ingest → B2

## Purpose
Record a teleoperation episode from **real robot camera footage** with the
genuine LeRobot v3 API and persist the whole dataset tree to Backblaze B2.

The frames come from a **public** LeRobot **v3** dataset on the HuggingFace Hub.
The source is **selectable per recording**: the create form offers a curated
dropdown of vetted public v3 datasets plus a **"Custom repo…"** option that
accepts any other public `owner/name` (the bring-your-own-data path). The default
is `lerobot/svla_so101_pickplace`, a real teleoperated SO-101 arm (robot_type
`so100_follower`), already in v3.0 format (~86 MB, 2 cameras at 480×640, 30 fps,
6-DoF state/action). Whatever source is chosen, only a couple of its first
episodes are pulled via the SDK's partial-download path and cached **per repo_id**
(`hf_source._CACHE`), so ingest never downloads the whole dataset, successive
recordings reuse the cache, and switching sources doesn't thrash an already-loaded
one. Frames are resized to the requested square resolution; the source cameras map
to `cam_0..cam_{n-1}` (cycled if fewer source cameras than requested); 6-DoF
`observation.state` / `action` vectors are used verbatim when present, else a
derived placeholder is used (the video is the real asset). The recorded
`robot_type` is the source dataset's own.

A procedural moving-gradient generator (`_synth_frame`) survives **only** as a
clearly-logged offline fallback so the live interactive demo never hard-crashes
when the Hub is unreachable — and **only for the default source**. A
**user-chosen** source that can't load (private, gated, not v3, offline) fails
loudly with a 400 instead of silently substituting synthetic frames the user
never asked for. `build_episode` returns the `robot_type` it wrote (the source's
real type for real footage, `synthetic` for the offline fallback) so callers can
tell real demo data apart from the fallback. The seeded demo data is always real.

## Used By
- UI: `/episodes/new` (create form)
- API: `POST /episodes`, `GET /episodes/options`

## Core Functions
- `services/api/app/repo/hf_source.py` — `real_frame(repo_id=…)` serves real
  resized camera frames + 6-DoF state/action from the chosen source;
  `ensure_loaded(repo_id)` lazily caches it **per repo_id** (`_CACHE`);
  `source_robot_type(repo_id)` reports its real robot_type
- `services/api/app/repo/lerobot_dataset.py` — `build_episode(..., source_repo_id,
  allow_synth_fallback)` wraps the real `LeRobotDataset.create() → add_frame →
  save_episode → finalize` and selects the footage source (synthetic fallback
  only when allowed); `select_device()`
- `services/api/app/service/episodes.py` — `create_episode()` orchestration +
  upload; validates `source_repo_id` (`owner/name`), enables the synthetic
  fallback only for the default source, and converts a `RealSourceUnavailable`
  for a chosen source into a 400; rotates `source_episode` across recordings
- `services/api/app/types/episodes.py` — `PRESET_SOURCES` curated list +
  `SOURCE_REPO_ID_PATTERN`
- `services/api/app/repo/b2_objects.py` — `upload_path()` / `put_bytes()`
- `apps/web/src/components/episodes/episode-create-form.tsx`

## Inputs
- `source_repo_id`: curated v3 dataset (dropdown) **or** a custom HuggingFace
  `owner/name` via "Custom repo…" — optional; omit for the server default
- `task`: enum (preset list) — selector
- `num_cameras`: 1 | 2 | 3 — selector
- `num_frames`: 30 | 60 | 120 — selector
- `fps`: 10 | 30 — selector
- `resolution`: 128 | 256 — selector

Finite fields use selectors; safe defaults (2 cameras · 60 frames · 30 fps ·
256×256) are shown as guidance, never autofilled. The source dropdown is the one
field that also accepts free text, gated behind an explicit "Custom repo…" choice
with `owner/name` validation.

## Outputs
- `EpisodeCreateResult` (the new `Episode`, bytes uploaded, object count, device)
- Side effect: a full v3 tree written under `lerobot/episodes/ep_NNNNNN/` on B2

## Flow
- Validate finite parameters + `source_repo_id` format server-side
- Pick the next episode index; auto-detect device (CUDA→MPS→CPU)
- Resolve the frame source: lazily load + cache (per repo_id) the chosen Hub
  footage (primary). For the default source, fall back to procedural frames
  (logged) if the Hub is unreachable; for a user-chosen source, re-raise instead
- Build the v3 dataset on disk with the real LeRobot API; encode MP4 per camera
- Upload the tree to the episode's B2 prefix; clean up the temp dir
- Read the episode back from B2 metadata and return it

## Edge Cases
- Invalid finite value → 400 with a clear message
- Malformed `source_repo_id` (not `owner/name`) → 400 with a clear message
- No GPU → builds on CPU (default); never errors on a missing GPU
- ML deps not installed → import error surfaces at create time (documented setup step)
- **Default** source unreachable → logged fallback to procedural frames so the
  live demo doesn't crash; `robot_type` is then `synthetic` (never seeded as data)
- **User-chosen** source can't load (private/gated/not-v3/offline) → 400
  `EpisodeError` (fail loud); no synthetic substitution
- Source has no camera streams → treated as unloadable (400 for a chosen source)

## UX States
- Loading: "Recording & uploading…" button state
- Error: toast with the API message
- Success: toast + redirect to the episode detail page

## Verification
- Contract test: `services/api/tests/test_streaming_contract.py` (build helpers
  present; real footage wired as primary, synthetic only as fallback)
- Source unit tests: `services/api/tests/test_hf_source.py` — hermetic checks
  (signature parity incl. `repo_id`, 6-DoF coercion, fallback wiring, **per-repo
  caching**, **fail-loud re-raise** for a chosen source) plus an INTEGRATION test
  that decodes a real frame, skipped unless `RUN_HF_INTEGRATION=1` (keeps
  `pnpm test:api` / `pnpm check:structure` network-free)
- Source selection tests: `services/api/tests/test_episode_source.py` —
  `source_repo_id` validation, fail-loud 400 for an unloadable chosen source, and
  `/episodes/options` exposing the curated `sources` + `default_source`
- End-to-end: record an episode, confirm 6–7 objects under its prefix on B2 and
  `meta/info.json` `robot_type == "so100_follower"` (real, not the fallback)
- Quick verify: `pnpm test:api`
- Pass criteria: tests green; a create call returns a real `Episode` with frames > 0

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [B2 streaming](b2-streaming.md)

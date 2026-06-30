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
one. The recording **mirrors the source's real shape** rather than imposing one:
**every** source camera is recorded (no cycling, no duplication) at its **native,
non-square resolution**, at the source's native fps, with the source's real
`observation.state` / `action` vectors at their **true dimensionality** (a derived
placeholder is used only if the source lacks the stream). The recorded `robot_type`
is the source dataset's own. The full first source episode is recorded by default,
bounded by a safety ceiling (`MAX_EPISODE_FRAMES`); an optional `max_frames`
shortens it. The form previews this exact shape (and surfaces a load error)
**before** recording, via `GET /episodes/source-info`.

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
- API: `POST /episodes`, `GET /episodes/options`, `GET /episodes/source-info`

## Core Functions
- `services/api/app/repo/hf_source.py` — `inspect_source(repo_id)` reports the
  source's real shape (cameras + native size, fps, state/action dims, episode
  length, robot_type); `real_frame(t, total, source_episode, repo_id)` serves
  **every** source camera at native resolution + the real state/action vectors
  (no cycling, no resize-to-square, no 6-DoF coercion); `_load_source` caches
  per repo_id (`_CACHE`)
- `services/api/app/repo/lerobot_dataset.py` — `build_episode(..., source_repo_id,
  allow_synth_fallback, max_frames)` derives the v3 features + length **from the
  source** via `_resolve_frame_source`, then runs the real `LeRobotDataset.create()
  → add_frame → save_episode → finalize` (synthetic fallback, fixed shape, only
  when allowed); `select_device()`
- `services/api/app/service/episodes.py` — `create_episode()` orchestration +
  upload (passes only source/task/`max_frames`; shape is derived downstream);
  `inspect_source()` powers the preview/early-validation; validates
  `source_repo_id` (`owner/name`) and `max_frames`; enables the synthetic fallback
  only for the default source; converts a `RealSourceUnavailable` for a chosen
  source into a 400; rotates `source_episode` across recordings
- `services/api/app/service/episode_meta.py` — reads the recorded **non-square**
  `frame_height`/`frame_width` back out of `meta/info.json`
- `services/api/app/types/episodes.py` — `PRESET_SOURCES`, `SOURCE_REPO_ID_PATTERN`,
  `MAX_EPISODE_FRAMES`, `SourceInfo`/`SourceCamera`
- `services/api/app/repo/b2_objects.py` — `upload_path()` / `put_bytes()`
- `apps/web/src/components/episodes/episode-create-form.tsx`

## Inputs
- `source_repo_id`: curated v3 dataset (dropdown) **or** a custom HuggingFace
  `owner/name` via "Custom repo…" — optional; omit for the server default. The
  one field that accepts free text, gated behind an explicit "Custom repo…" choice
  with `owner/name` validation **and** a live `source-info` probe.
- `task`: enum (preset list) — selector; the label stored in this recording's v3
  metadata (the source's own task is shown in the preview for reference).
- `max_frames`: optional integer `1..MAX_EPISODE_FRAMES`; blank = the full first
  source episode.

The recording's **shape is no longer an input** — cameras, fps, resolution, and
state/action dims are derived from the chosen source and shown read-only in the
"What will be recorded" preview before submit.

## Outputs
- `EpisodeCreateResult` (the new `Episode`, bytes uploaded, object count, device)
- Side effect: a full v3 tree written under `lerobot/episodes/ep_NNNNNN/` on B2

## Flow
- (Form, before submit) `GET /episodes/source-info?repo_id=…` previews the real
  shape and validates the source loads; a failure shows in the form and blocks submit
- Validate `source_repo_id` format + `max_frames` range server-side
- Pick the next episode index; auto-detect device (CUDA→MPS→CPU)
- Resolve the frame source + shape from the source: lazily load + cache (per
  repo_id) the chosen Hub footage (primary). For the default source, fall back to
  fixed-shape procedural frames (logged) if the Hub is unreachable; for a
  user-chosen source, re-raise instead
- Build the v3 dataset on disk with the real LeRobot API at the source's native
  per-camera resolution / state-action dims / fps; encode MP4 per camera
- Upload the tree to the episode's B2 prefix; clean up the temp dir
- Read the episode back from B2 metadata and return it

## Edge Cases
- Malformed `source_repo_id` (not `owner/name`) or out-of-range `max_frames` → 400
- No GPU → builds on CPU (default); never errors on a missing GPU
- ML deps not installed → import error surfaces at create time (documented setup step)
- **Default** source unreachable → logged fallback to fixed-shape procedural frames
  so the live demo doesn't crash; `robot_type` is then `synthetic` (never seeded as data)
- **User-chosen** source can't load (private/gated/not-v3/offline) → 400
  `EpisodeError` (fail loud, surfaced in the form preview); no synthetic substitution
- Source has no camera streams, or can't be decoded → treated as unloadable (400 for a chosen source)
- Source episode shorter than `max_frames` → records the full episode (never loops)

## UX States
- Loading: "Recording & uploading…" button state
- Error: toast with the API message
- Success: toast + redirect to the episode detail page

## Verification
- Contract test: `services/api/tests/test_streaming_contract.py` (build helpers
  present; real footage wired as primary, synthetic only as fallback)
- Source unit tests: `services/api/tests/test_hf_source.py` — hermetic checks
  (`real_frame` carries no shape knobs; state/action pass through verbatim incl.
  **high-DoF** widths, placeholder only when absent; synthetic fallback wiring;
  `max_frames` capping; **per-repo caching**; `inspect_source` reports each
  source's distinct shape; **fail-loud re-raise** for a chosen source) plus an
  INTEGRATION test that decodes a real frame at native resolution, skipped unless
  `RUN_HF_INTEGRATION=1` (keeps `pnpm test:api` / `pnpm check:structure` network-free)
- Source selection tests: `services/api/tests/test_episode_source.py` —
  `source_repo_id` + `max_frames` validation, shape is derived (not imposed) in
  `create_episode`, fail-loud 400 for an unloadable chosen source, and the
  `/episodes/options` + `/episodes/source-info` endpoints
- End-to-end: record an episode, confirm objects under its prefix on B2 and that
  `meta/info.json` carries the source's real per-camera (non-square) resolution and
  `robot_type` (real, not the fallback)
- Quick verify: `pnpm test:api`
- Pass criteria: tests green; a create call returns a real `Episode` with frames > 0

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [B2 streaming](b2-streaming.md)

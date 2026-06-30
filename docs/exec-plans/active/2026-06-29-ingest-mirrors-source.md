# Ingest mirrors the source dataset (drop the synthetic-era shape knobs)

## Scope
The record form imposed `num_cameras` (1/2/3), `num_frames` (30/60/120), `fps`
(10/30), and `resolution` (128/256) — synthetic-era knobs that corrupt **real**
footage: cameras were cycled (duplicated streams), frames looped, footage was
squished into a square, fps was mislabeled, and any non-6-DoF state/action was
coerced to a fabricated placeholder. This change makes ingest **mirror the chosen
source's real shape** instead: all cameras at native (non-square) resolution, the
source's fps, real state/action dims, and the source episode's own length. The
only inputs become the source, an optional task label, and an optional frame cap.

## Decisions
- The recording's shape is **derived from the source**, never chosen. The form
  shows a read-only "What will be recorded" preview from a new
  `GET /episodes/source-info` probe, which doubles as **fail-loud validation in
  the form** (a bad/gated/non-v3 repo errors before submit and blocks Record).
- Native resolution, no resize-to-square. `max_frames` (optional) is the size
  lever; default = full first episode, capped at `MAX_EPISODE_FRAMES` (600).
- State/action vectors pass through verbatim at their true width; a placeholder is
  derived only when the source genuinely lacks the stream.
- Task stays a preset selector (the annotation for this recording); the source's
  real task is shown in the preview for reference.
- Synthetic fallback survives only for the **default** source offline, at a fixed
  shape (2 cams · 30 fps · 256² · 6-DoF), clearly logged.

## Files Updated
- `repo/hf_source.py` — `_Source`/`_SourceCamera` carry per-camera native shape +
  state/action dims + task; `inspect_source(repo_id)`; `real_frame(t, total, …)`
  drops the shape knobs (no cycling, no loop, native resolution, real vectors);
  `num_source_episode_frames`.
- `repo/lerobot_dataset.py` — `_features(cameras, state_dim, action_dim)` (per-camera
  non-square + arbitrary dims); `_resolve_frame_source`/`_BuildSpec`/`_bounded`
  derive shape + length from the source; `build_episode(..., max_frames)`.
- `service/episodes.py` — slimmed `_validate_create`; `create_episode` passes only
  source/task/`max_frames`; new `inspect_source()` → `SourceInfo` (400 fail-loud).
- `service/episode_meta.py` — reads non-square `frame_height`/`frame_width`.
- `runtime/episodes.py` — `GET /episodes/source-info`; slimmed `/episodes/options`.
- `types/episodes.py` — `SourceInfo`/`SourceCamera`, `MAX_EPISODE_FRAMES`; slimmed
  `EpisodeCreateRequest`/`EpisodeFormOptions`; `Episode.frame_height`/`frame_width`.
- `packages/shared/src/types.ts` — mirror all of the above.
- `apps/web/src/lib/{api-client,queries}.ts` — `getSourceInfo` + `useSourceInfo`.
- `apps/web/src/components/episodes/episode-create-form.tsx` — four knobs → source
  picker + live preview (debounced, fail-loud) + optional `max_frames`.
- `apps/web/src/components/episodes/episode-detail.tsx` — `frame_width×frame_height`.
- Tests: `test_hf_source.py`, `test_episode_source.py`, `test_streaming_contract.py`.
- Docs: `README.md`, `AGENTS.md`, `ARCHITECTURE.md`,
  `docs/features/episode-ingest.md`, `docs/app-workflows.md`, tech-debt tracker.

## Verification
- `pnpm lint:api && pnpm test:api && pnpm check:structure && pnpm lint && pnpm build`
  — all green (backend 94 passed / 1 skipped).
- Manual: `lerobot/pusht` (1 cam) → preview shows 1 camera, native size → records a
  single non-duplicated camera; default (2 cam) → 2 distinct cameras; bogus custom
  repo → error in the form, Record disabled; valid custom v3 repo → records; Stream
  back (bytes ≪ total holds).

## Out of scope / follow-ups
- Private/gated repos need `HF_TOKEN` (tech-debt).
- Per-camera *differing* resolutions are recorded faithfully but summarized by the
  first camera in the `Episode` card.
- Relaxing the task field to fully free-text (prefilled from the source).

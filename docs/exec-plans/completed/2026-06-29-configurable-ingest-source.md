# Configurable Ingest Source Dataset (from the UI)

## Scope
Let a user choose the ingest **source dataset** from the record form instead of
the previously hardcoded `lerobot/svla_so101_pickplace`. A curated dropdown of
vetted public LeRobot **v3** datasets plus a "Custom repo…" free-text option for
any public HuggingFace `owner/name`. Makes the bring-your-own-data story true
end-to-end through the UI; the streaming bridge was already source-agnostic.

## Decisions
- UX: curated dropdown + "Custom repo…" free-text (a deliberate, validated
  exception to the form's "selectors only" convention).
- A **user-chosen** source that can't load → 400 fail-loud (no silent synthetic
  substitution). Synthetic fallback stays only for the **default** source's
  offline safety net.
- Auto-pull the first 1–2 source episodes (bounded download); no episode-index
  picker.

## Curated list (confirmed `codebase_version: v3.0`, public, with video cameras)
`lerobot/svla_so101_pickplace` (default), `lerobot/svla_so100_pickplace`,
`lerobot/aloha_sim_insertion_human`, `lerobot/pusht`.

## Files Updated
- `services/api/app/repo/hf_source.py` — per-repo cache (`_CACHE`, `_Source`);
  `repo_id` param on `ensure_loaded`/`real_frame`/`source_fps`/
  `num_source_episodes`; new `source_robot_type(repo_id)`; camera-stream guard;
  tolerate missing state/action.
- `services/api/app/repo/lerobot_dataset.py` — `source_repo_id` +
  `allow_synth_fallback` threaded through `build_episode` / `_resolve_frame_source`.
- `services/api/app/service/episodes.py` — `owner/name` validation; default-only
  fallback; `RealSourceUnavailable` → 400 `EpisodeError`.
- `services/api/app/types/episodes.py` — `PRESET_SOURCES`,
  `SOURCE_REPO_ID_PATTERN`, `EpisodeCreateRequest.source_repo_id`,
  `EpisodeFormOptions.sources/default_source`.
- `services/api/app/runtime/episodes.py` — `/episodes/options` returns
  `sources` + `default_source`.
- `packages/shared/src/types.ts` — mirror the two TS type changes.
- `apps/web/src/components/episodes/episode-create-form.tsx` — Source dataset
  dropdown + conditional custom `Input` (`useWatch`), zod `superRefine`.
- Tests: `tests/test_hf_source.py` (per-repo cache, fail-loud re-raise, `repo_id`
  signature), new `tests/test_episode_source.py` (validation, 400 fail-loud,
  options endpoint).
- Docs: `README.md`, `AGENTS.md`, `docs/features/episode-ingest.md`,
  `docs/app-workflows.md`.

## Verification
- `pnpm lint:api && pnpm test:api && pnpm check:structure && pnpm lint &&
  pnpm typecheck` — all green (backend 84 passed / 1 skipped).
- Manual: default record unchanged; pick `lerobot/pusht` → records from it; custom
  bogus id → friendly 400 toast; custom valid v3 id → records; then Stream back.

## Out of scope / follow-ups
- Private/gated repos need an `HF_TOKEN` (future tech-debt item).
- Curated list duplicated front/back (matches the existing `PRESET_TASKS` pattern).

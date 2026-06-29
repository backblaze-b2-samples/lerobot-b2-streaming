# Exec Plan: Real robot footage instead of synthetic frames

Date: 2026-06-29
Status: completed

## Goal

Make the demo data REAL. The "camera" videos are currently synthetic moving
gradients (`_synth_frame` in `repo/lerobot_dataset.py`). Replace the synthetic
frame source with real teleoperation camera footage pulled from a small PUBLIC
`lerobot/*` dataset on the HuggingFace Hub, and seed B2 with a couple of real
episodes as the demo data.

## Invariants to keep (AGENTS.md §3/§4)

- LeRobot / torch imported ONLY inside `services/api/app/repo/` (lazy imports).
- No boto3 outside `repo/`.
- Files under 300 lines (→ put the HF source in a new `repo/hf_source.py`).
- `tests/test_structure.py` stays network-free; new HF-source test guarded
  behind a skip marker so `pnpm test:api` / `pnpm check:structure` stay hermetic.
- Tests + docs updated in the same change.
- Keep the marquee streaming bridge (`repo/b2_stream.py`) and CPU-default device
  path UNCHANGED.

## Steps

- [x] A. Chose `lerobot/svla_so101_pickplace` — real SO-101 arm
      (robot_type `so100_follower`), genuine **v3.0** (no conversion), ~86 MB,
      2 cameras (`observation.images.up` / `...side`, 480×640), 30 fps, and
      **6-DoF** state/action (exact schema match). Loaded episodes [0, 1] via the
      SDK partial-download path (569 frames; ~82 MB cached) and decoded real
      frames with torchcodec. Rejected `koch_pick_place_lego` (Hub 401 / gone)
      and `aloha_static_coffee` (real+v3 but 1.5 GB and 14-DoF, not 6-dim).
- [x] B. Added `repo/hf_source.py` (real_frame + ensure_loaded, PIL resize, 6-DoF
      coercion). `build_episode` uses the real source as PRIMARY and returns the
      `robot_type` it wrote; `_synth_frame` kept only as a logged offline
      fallback. `create_episode` rotates `source_episode` per recording.
- [x] C. Added `tests/test_hf_source.py` (hermetic + a `RUN_HF_INTEGRATION=1`
      integration test) and extended the contract test. lint:api / test:api
      (74 passed, 1 skipped) / check:structure / lint / build all green.
- [x] D. Deleted the 4 synthetic episodes (29 objects) scoped to
      `lerobot/episodes/`; ingested 3 real episodes (ep_000000 "Pick up the
      cube", ep_000001 "Stack blocks", ep_000002 "Open the drawer"; 20 objects,
      736,354 bytes). Verified real: meta `robot_type=so100_follower` + decoded
      B2 frame mean-abs-diff 49.78 vs the synthetic gradient.
- [x] E. Docs updated: lerobot_dataset.py docstring, AGENTS.md, ARCHITECTURE.md,
      docs/features/episode-ingest.md, README.md, episode-list empty state,
      EpisodeCreateRequest docstring. (dashboard.md needed no change — it never
      claimed synthetic.)
- [x] F. Committed on `main` as EduPav <edumarpav@yahoo.com.ar>.

## Notes

- Source dataset cache lives at `/tmp/lerobot-b2-streaming-real` (outside the
  tree); `.gitignore` also defensively ignores any in-tree `LEROBOT_REAL_CACHE`
  override. The committed diff is source/tests/docs only.

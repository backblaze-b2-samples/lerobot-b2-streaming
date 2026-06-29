<!-- last_verified: 2026-06-29 -->
# Feature: Episode library explorer

## Purpose
A sample-scoped explorer over the LeRobot dataset prefix on B2 — the "library"
of recorded episodes, filterable by task — distinct from the full-bucket `/files`
explorer (which is retained).

## Used By
- UI: `/episodes` (list) + `/episodes/[id]` (detail)
- API: `GET /episodes`, `GET /episodes/{index}`, `GET /episodes/{index}/video`

## Core Functions
- `apps/web/src/components/episodes/episode-list.tsx` — table + task filter + row actions
- `apps/web/src/components/episodes/episode-detail.tsx` — cameras, metadata, edit, delete
- `apps/web/src/components/episodes/camera-player.tsx` — presigned-URL MP4 player
- `services/api/app/service/episodes.py` — `list_episodes()`, `camera_video_url()`

## Inputs
- `task`: optional filter (selector: All / preset tasks)
- `index`: episode index (detail)
- `camera`: camera id (video URL)

## Outputs
- Episode rows; per-camera presigned MP4 URLs for playback

## Flow
- List episodes (optionally filtered by task)
- Open an episode → per-camera videos render from presigned URLs; metadata shown
- Row/detail actions deep-link to Stream and to Delete (confirmation dialog)

## Edge Cases
- No episodes / no matches → empty state with a record CTA
- Presigned URL fetch fails → camera tile shows "Preview unavailable"

## UX States
- Loading: skeleton rows / pulsing video tiles
- Empty: prompt to record an episode
- Error: inline `ErrorState` with Retry

## Verification
- Frontend build + lint: `pnpm build && pnpm lint`
- Manual: filter by task, open a detail page, confirm cameras play

## Related Docs
- [Dataset index & query](dataset-index-query.md)
- [File Browser](file-browser.md) (the retained full-bucket explorer)

<!-- last_verified: 2026-06-29 -->
# Feature: Dashboard

## Purpose
Give an at-a-glance overview of the LeRobot dataset on B2: how many episodes,
frames, cameras and tasks exist, how much storage they occupy, ingest activity
over time, and the most recent episodes.

## Used By
- UI: `/` page (dashboard home)
- API: `GET /episodes/stats`, `GET /episodes/stats/activity`, `GET /episodes`

## Core Functions
- `apps/web/src/components/dashboard/dataset-stats-cards.tsx` — 5 stat cards
- `apps/web/src/components/dashboard/ingest-chart.tsx` — episodes recorded/day
- `apps/web/src/components/dashboard/recent-episodes-table.tsx` — last 10 episodes
- `apps/web/src/lib/api-client.ts` — `getDatasetStats()`, `getIngestActivity()`, `getEpisodes()`
- `services/api/app/runtime/episodes.py` — `GET /episodes/stats`, `/episodes/stats/activity`
- `services/api/app/service/dataset_stats.py` — aggregation logic
- `services/api/app/service/episodes.py` — reads each episode's v3 metadata from B2

## Inputs
- None (dashboard loads data automatically)

## Outputs
- `GET /episodes/stats` → `DatasetStats` (total_episodes, total_frames, total_cameras, total_tasks, total_dataset_bytes[_human], tasks)
- `GET /episodes/stats/activity?days=7` → `DailyEpisodeCount[]` (episodes recorded per day)
- `GET /episodes` → `Episode[]`; the table shows the 10 highest-index episodes

## Flow
- Page loads → parallel API calls (dataset stats, ingest activity, episode list)
- Stat cards display episodes, frames, cameras, tasks, total dataset bytes on B2
- Ingest chart shows episodes recorded per day for the last 7 days
- Recent-episodes table shows the latest episodes with task badge, frames, cameras, size

## Edge Cases
- API unavailable → cards/chart/table surface an inline `ErrorState` with Retry
- No episodes → zeroed cards, empty chart + table messages
- Large dataset → listing paginates through B2 objects under the dataset prefix

## UX States
- Loading: skeleton placeholders for cards and table
- Empty: "No episodes yet" prompts to record one
- Loaded: populated cards, chart, table

## Verification
- Quick verify: `pnpm test:api`
- Full verify: `pnpm lint && pnpm lint:api && pnpm test:api && pnpm check:structure`
- Pass criteria: all pytest tests green, no ruff/eslint violations

## Related Docs
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)

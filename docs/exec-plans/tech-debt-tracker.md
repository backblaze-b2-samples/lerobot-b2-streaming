<!-- last_verified: 2026-03-10 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

| Description | Impact | Proposed Resolution | Priority | Status |
|---|---|---|---|---|
| `datetime.utcnow()` deprecated in Python 3.12+ | Naive datetimes, future breakage | Replace with `datetime.now(UTC)` in `repo/b2_client.py`, `service/metadata.py` | High | Resolved |
| S3 client recreated on every API call | Connection pool wasted, added latency | Cache client as module-level singleton via `lru_cache` | High | Resolved |
| `get_upload_stats()` pagination broken at 1000 objects | Stats silently wrong for large buckets | Check `IsTruncated` + use `ContinuationToken` | High | Resolved |
| `record_upload()` never called | `/metrics` always reports 0 uploads | Call from `runtime/upload.py` after successful upload | Medium | Resolved |
| Metrics counters not thread-safe | Race conditions under concurrent requests | Use `threading.Lock` (matches `service/files.py` pattern) | Medium | Resolved |
| `_humanize_bytes` duplicated in Python (repo + service) | DRY violation, drift risk | Extract to `app/types/formatting.py` shared util | Medium | Resolved |
| `humanizeBytes` duplicated in TypeScript | DRY violation | Extract to `lib/utils.ts` | Low | Open |
| `formatDate` duplicated in TypeScript | DRY violation | Extract to `lib/utils.ts` | Low | Open |
| No test harness for feature specs | No automated verification | Add pytest fixtures + test files per feature | Medium | Resolved (partial — tests added for upload, files, activity, errors) |
| Private/gated HF source repos can't be ingested | Bring-your-own-data limited to public datasets | Add optional `HF_TOKEN` env var, pass to `LeRobotDataset` load in `repo/hf_source.py` | Medium | Open |
| `Episode` summarizes a multi-camera dataset's resolution by the first camera | A source whose cameras differ in size shows only the first in the detail card (all are recorded faithfully) | Report per-camera sizes in the `Episode` model + detail UI | Low | Open |
| Curated `PRESET_SOURCES` / `PRESET_TASKS` / frames ceiling duplicated front+back | Drift risk | Have the form read `/episodes/options` instead of hardcoding (matches existing `PRESET_TASKS` pattern) | Low | Open |

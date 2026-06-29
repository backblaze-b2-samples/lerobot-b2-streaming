# Build plan — `lerobot-b2-streaming`

> Source of truth for builder + reviewer. Built by adapting the freshly-cloned
> `vibe-coding-starter-kit` at
> `.claude/scratch/vcsk-5cc73b3b-5717-4838-96d4-e5114d5c3bb6/`. The starter kit is
> the ceiling — strip what this app doesn't need, keep the reusable B2 surface,
> and add the LeRobot-specific layers.

## 1. Purpose

`lerobot-b2-streaming` shows robotics researchers and lab teams how to use a
single **Backblaze B2** bucket as the shared dataset backend for
[HuggingFace LeRobot](https://github.com/huggingface/lerobot). Teleoperation
**episodes** (multi-camera MP4 video + a Parquet state/action table, in the real
**LeRobotDataset v3** layout) are recorded and persisted to B2, indexed by task
label, and then **streamed back chunk-by-chunk from B2 over the S3 API** to feed
training — no per-researcher full-dataset download. It targets ML/robotics
engineers who already know LeRobot and want object storage instead of either a
local disk or the HuggingFace Hub.

### Critical technical reality (read before building — drives the whole design)

Verified against LeRobot 0.4.x–0.5.1 docs + source (June 2026):

- **`LeRobotDataset.create()` / `add_frame()` / `save_episode()` / `finalize()`**
  is the real, local, CPU-friendly way to build a v3 dataset on disk. We use the
  genuine LeRobot API here (vendor fidelity — this must be a real *LeRobot*
  sample, not a parquet/mp4 look-alike).
- **The v3 on-disk layout** is: `meta/info.json` (schema, fps, path templates),
  `meta/stats.json` (norm stats), `meta/tasks.jsonl` (task label → id),
  `meta/episodes/*.parquet` (per-episode lengths, tasks, and **byte/frame
  offsets** into the shared shards), `data/*.parquet` (many episodes per file),
  `videos/<camera>/*.mp4` (many episodes per file, sharded per camera).
- **`StreamingLeRobotDataset` is HuggingFace-Hub-ONLY.** It takes a `repo_id` and
  streams from the Hub. It has **no** native support for S3, a custom endpoint,
  fsspec, or even an arbitrary local `root` — non-Hub roots are an *open feature
  request* (huggingface/lerobot#764). So "stream `StreamingLeRobotDataset`
  directly from B2" as literally worded in the use case is **not** something
  stock LeRobot can do.

**Design consequence (honest framing — this is the sample's differentiator, not a
shortcut):** the sample provides a **B2/S3 streaming bridge**. The v3 format was
explicitly built for chunk-by-chunk access — episode views are reconstructed from
the byte/frame offsets in `meta/episodes/*.parquet`, not file boundaries. So the
bridge reads the small metadata from B2, then issues **S3 ranged GETs** (boto3
`get_object(Range=…)` and/or an `s3fs`/`fsspec` range-capable file handle) to pull
**only the Parquet row-groups and the specific video byte-ranges for the requested
episodes** — never the whole dataset. The measurable, verifiable invariant is
**bytes fetched from B2 ≪ total dataset size**. The README/docs must state plainly
that this bridge is what LeRobot#764 is asking for, and that stock
`StreamingLeRobotDataset` is Hub-only — do **not** imply LeRobot natively streams
from B2.

## 2. Architecture delta from vibe-coding-starter-kit

### KEEP (as-is — starter contract, do not strip/rename/replace)
- The whole UI kit: `apps/web/src/components/ui/*` (shadcn), design tokens in
  `apps/web/src/app/globals.css`, and the `/design` reference page.
- **Bucket explorer `/files`** (full-bucket browse) — `apps/web/src/app/files/`,
  `apps/web/src/components/files/`. **NON-NEGOTIABLE KEEP** — never removable.
- **Upload `/upload`** + its components and the metadata-extraction service
  (Pillow/PyPDF2) it feeds — the reusable B2-write surface stays.
- Sidebar nav scaffold (`app-sidebar.tsx`), header, health banner, command
  palette, theme provider.
- Backend layered architecture (`types→config→repo→service→runtime`), structural
  tests, `/health`, `/metrics`, structured JSON logging, TanStack Query data layer
  (`lib/api-client.ts` + `lib/queries.ts`), shared types package.
- `settings/` page (client-side demo) — keep; it is the in-repo exemplar for the
  Form UX conventions below.

### TRIM (remove / replace from starter — minimal; starter is mostly kept)
- The Dashboard's upload-centric default widgets — `dashboard/stats-cards.tsx`,
  `dashboard/upload-chart.tsx`, `dashboard/recent-uploads-table.tsx` — are
  *replaced* (adapt, not delete the page) with episode/dataset equivalents.
- Starter README screenshots/marketing copy and `docs/features/metadata-extraction.md`
  framing that's upload-only → keep the file-upload + file-browser feature docs
  (pages stay) but rewrite the README and dashboard doc.
- Nothing else is removed — the starter surface is the ceiling and we add on top.

### ADD (new for `lerobot-b2-streaming`)
- **Backend repo layer** (SDK-contained, `<300` lines/file):
  - `repo/b2_client.py` — extend the existing S3 client with `get_object_range()`
    (ranged GET), `put_object`/multipart for shards, `list_objects_v2` under a
    prefix, `delete_objects` scoped to a prefix, presigned URL for MP4 playback.
  - `repo/lerobot_dataset.py` — wraps the real LeRobot SDK: synthesize a
    teleoperation episode (numpy state/action + procedurally-generated camera
    frames), build it with `LeRobotDataset.create()`→`add_frame`→`save_episode`→
    `finalize`, and read v3 metadata (`info.json`, `episodes/*.parquet`,
    `tasks.jsonl`). CPU-default, GPU-autodetect (see Features).
  - `repo/b2_stream.py` — the **B2/S3 streaming bridge**: given episode id(s) or a
    task split, read v3 metadata from B2, then ranged-GET only the needed Parquet
    row-groups + video byte-ranges (boto3 Range / `s3fs`), decode frames + state
    tensors, and report `bytes_fetched` vs `total_dataset_bytes`.
- **Backend service layer**: `service/episodes.py` (ingest/index/list/get/relabel/
  delete orchestration), `service/streaming.py` (single + concurrent-worker
  streaming runs, stats aggregation), `service/dataset_stats.py` (dashboard
  aggregations). All return Pydantic models; no boto3/lerobot imports here.
- **Backend runtime (routers)** — each new endpoint touches the three files
  (`runtime/<router>.py`, `lib/api-client.ts`, `lib/queries.ts`):
  - `runtime/episodes.py` — CRUD+ for the Episode entity (see §4 verbs).
  - `runtime/streaming.py` — start a streaming run; return live/final stats.
- **Frontend pages**:
  - `/episodes` — **sample-specific asset explorer scoped to the dataset prefix**
    (the mandated per-sample explorer; the "Library" of recorded episodes,
    filterable by task label) — distinct from the kept full-bucket `/files`.
  - `/episodes/[id]` — episode detail (read): per-camera MP4 player (presigned
    URL), state/action sparkline/plot, task label, frame count, fps, B2 size +
    keys; hosts Edit (relabel) and Delete actions.
  - `/episodes/new` — create form (record a synthetic episode → write v3 → upload
    to B2). Form UX per §4.
  - `/stream` — the **run** surface: pick an episode or task split, stream it
    chunk-by-chunk from B2, and show live stats (episodes streamed, frames
    decoded, **bytes fetched from B2 via Range vs full dataset size**, throughput,
    and a concurrent N-worker mode for the Serve/Query story).
  - Adapted **Dashboard `/`**: dataset-stats cards (total episodes, total frames,
    cameras, tasks, total dataset bytes on B2), ingest-activity chart (episodes
    recorded over time), recent-episodes table.
- `docs/features/*` for the new features (see §5); `docs/exec-plans/completed/`
  receives this plan on PASS.

### Note on the bucket-explorer tension
None — `/files` (full-bucket browse) stays untouched, and `/episodes` is the
*additional* sample-scoped explorer. Both coexist as intended.

## 3. B2 surface (S3 operations — S3-compatible API ONLY, no b2-native)

| Op | S3 call | Used by |
|----|---------|---------|
| Write dataset shards/meta | `put_object` / multipart `upload_file` | ingest |
| List dataset / bucket | `list_objects_v2` (prefix) | `/episodes`, `/files`, index, stats |
| Object size/metadata | `head_object` | stats, stream planning |
| **Chunk-by-chunk read** | **`get_object(Range=…)`** (and/or `s3fs` range handle) | **streaming bridge (marquee)** |
| Read small meta files | `get_object` (full) | index/query |
| Serve MP4 to browser | `generate_presigned_url` | episode detail player |
| Delete episode | `delete_object` / `delete_objects` **scoped to the episode's prefix** | delete verb |

- **No b2-native API anywhere.** boto3 S3 client only, constructed once in
  `repo/b2_client.py`, with `user_agent_extra` set (Standard #2). The streaming
  bridge's ranged GETs are pure S3 `Range` requests — explicitly **not** a
  b2-native feature, and the documented reason we don't call stock
  `StreamingLeRobotDataset` (Hub-only). If `s3fs`/`fsspec` is used for range
  handles, it must be configured against the B2 S3 endpoint and also carry the
  custom UA where the client allows; if `s3fs` cannot set a custom UA, keep the
  authoritative UA-bearing path on the boto3 client and note the deviation.
- Standardized env vars (Standard #3) — **rename required** (see §6); construct
  `endpoint_url` from `B2_REGION`.

## 4. Key features

Per-feature `deployment` is an explicit field (gates builder + reviewer).

1. **Episode ingest → B2** — `deployment: local`. Synthesize a teleoperation
   episode (procedural multi-camera frames + numpy state/action), build it with
   the **real** `LeRobotDataset.create()` v3 API, then upload the `data/`,
   `videos/`, `meta/` tree to B2. No external API. CPU-default, GPU-autodetect
   (CUDA→MPS→CPU); MPS note: video encode/decode runs through ffmpeg/torchcodec
   on CPU regardless, tensor ops follow the detected device.
2. **Dataset index & query** — `deployment: local`. Read `meta/episodes/*.parquet`
   + `meta/tasks.jsonl` from B2 to list/filter episodes by task label or id.
3. **B2 S3 chunk-by-chunk streaming (marquee)** — `deployment: local`. The bridge
   in `repo/b2_stream.py`; feeds a **mini** training/inference loop (iterate K
   batches, run a trivial CPU op or 1-step update on a tiny MLP — *not* a full
   policy train; framed as "the training data path"). Reports bytes-fetched ≪
   total. No external API.
4. **Episode library explorer** — `deployment: local`. The `/episodes` sample-
   scoped explorer over the dataset prefix.
5. **Concurrent multi-worker streaming (Serve/Query)** — `deployment: local`.
   Spawn N concurrent stream readers, each pulling a different task split from the
   shared B2 bucket; show per-worker throughput + total. Demonstrates the
   shared-backend / fleet story.

- **External API provider:** NONE. The entire ML workload (synthetic episode
  generation, v3 build, streaming, mini training loop) runs **locally**, matching
  the use case ("no second API key, B2 credentials only"). Every feature is
  `deployment: local` and inherits the CPU-default / GPU-autodetect hard rule.
- **Genblaze:** not applicable — the description does not mention Genblaze /
  `genblaze-*` / `genblaze-s3`. Do not route through Genblaze.

### Primary entity & lifecycle verbs (UI completeness)

**Primary entity: `Episode`** (one teleoperation demonstration episode). All five
verbs are user-meaningful and **all are built in the UI** → `omitted_ui_verbs: []`.

| Verb | UI surface | Behavior |
|------|-----------|----------|
| **create** | `/episodes/new` form | Record a synthetic episode → v3 build → upload to B2 |
| **read** | `/episodes` list + `/episodes/[id]` detail | Browse + view cameras/state/task/meta |
| **edit** | `/episodes/[id]` edit form (pre-filled) | **Re-label / re-tag the episode's task annotation** (updates the index metadata in B2). This is the real, lightweight, in-scope edit — frames are immutable, the task label is not. |
| **delete** | `/episodes/[id]` (+ list row action) | Delete the episode's shards/meta from B2, **scoped to that episode's prefix only** |
| **run** | `/stream` | Stream the episode / task split chunk-by-chunk from B2 into the mini training loop |

### Form UX conventions

**Create form (`/episodes/new`)** — fields with finite value sets use selectors
(`Select`/`RadioGroup`/segmented), never free text; CREATE surfaces safe defaults
as placeholder/`FormDescription` guidance (guidance only, never an autofill button):

| Field | Control | Default-hint (guidance for a sound test run) |
|-------|---------|----------------------------------------------|
| `task` (label) | `Select` of preset tasks (e.g. "Pick up the cube", "Stack blocks", "Open the drawer", "Push the button") | "Pick up the cube" |
| `num_cameras` | segmented / `Select` (1–3) | 2 |
| `num_frames` (length) | `Select` (30 / 60 / 120) | 60 |
| `fps` | `Select` (10 / 30) | 30 |
| `resolution` | `Select` (128×128 / 256×256) | 256×256 |

FormDescription line, e.g.: *"Defaults (2 cameras · 60 frames · 30 fps · 256×256)
record a small episode in a few seconds — good for a first run."*

**Edit form (`/episodes/[id]`)** — opens pre-filled with the real episode; the
`task` field uses the same preset `Select` (selector rule applies to edit too). No
default-hint (it's editing a real resource). Exemplar to mirror:
`apps/web/src/components/settings/settings-form.tsx`.

## 5. Doc transforms

- **Rewrite:** `README.md` (full rebrand + new quickstart: install ML deps, record
  demo episodes, stream from B2; lead with the B2-as-dataset-backend value prop and
  the honest "bridge fills LeRobot#764" note). `ARCHITECTURE.md` (add v3 layout, the
  three new repo adapters, new routers/services, B2 prefix layout, streaming data
  flow). `docs/features/dashboard.md` (episode/dataset metrics). `AGENTS.md` repo map
  (new dirs) + rename.
- **Keep (pages stay):** `docs/features/file-upload.md`, `docs/features/file-browser.md`,
  `docs/design-system.md`, `docs/SECURITY.md`, `docs/RELIABILITY.md`,
  `docs/app-workflows.md`, `docs/dev-workflows.md` (update the last two for episode
  journeys + ML dev setup).
- **Delete:** `docs/features/metadata-extraction.md` only if the upload metadata
  feature is trimmed — but it's KEPT, so keep this doc too (just don't feature it in
  the README). Net: no feature doc deleted.
- **Add stubs:** `docs/features/episode-ingest.md`, `dataset-index-query.md`,
  `b2-streaming.md`, `episode-library.md`, `concurrent-streaming.md`.

## 6. Rename table

| From (`vibe-coding-starter-kit`) | To (`lerobot-b2-streaming`) |
|---|---|
| repo dir / kebab id | `lerobot-b2-streaming` |
| root `package.json` `name` | `lerobot-b2-streaming` |
| pkg scope `@vibe-coding-starter-kit/web` | `@lerobot-b2-streaming/web` |
| pkg scope `@vibe-coding-starter-kit/shared` | `@lerobot-b2-streaming/shared` |
| `APP_NAME` ("OSS Starter Kit") in `lib/app-config.ts` | `LeRobot B2 Streaming` |
| `APP_DESCRIPTION` | `Stream LeRobot teleoperation datasets straight from Backblaze B2` |
| FastAPI title ("OSS Starter Kit API") in `main.py` | `LeRobot B2 Streaming API` |
| Railway service names / infra labels | `lerobot-b2-streaming-web` / `lerobot-b2-streaming-api` |
| `user_agent_extra` (`b2ai-oss-start`) | `b2ai-lerobot-b2-streaming` (sample-specific custom UA; no claimed issue value available) |
| UTM `utm_content=b2ai-oss-start` in README links | `utm_content=b2ai-lerobot-b2-streaming` |
| **Env var** `B2_KEY_ID` | **`B2_APPLICATION_KEY_ID`** (Standard #3) |
| **Env var** `B2_ENDPOINT` (full URL) | **`B2_REGION`** (derive `endpoint_url=f"https://s3.{B2_REGION}.backblazeb2.com"`) |
| **Env var** `B2_PUBLIC_URL` | **`B2_PUBLIC_URL_BASE`** (Standard #3) |
| Env var `B2_APPLICATION_KEY` | unchanged (already Standard #3) |
| Env var `B2_BUCKET_NAME` | unchanged (already Standard #3) |

Update `.env.example`, `settings.py`, `main.py` validation, `infra/railway/README.md`,
README setup steps, and `pnpm dev:*` scripts accordingly. The starter's hardcoded
header/title leak ("OSS Starter Kit"/"Page" fallback) must resolve through the single
`APP_NAME` const — verify the header shows "LeRobot B2 Streaming", not a stale string.

## 7. Dependency pinning (ML — clean-install correctness is mandatory)

Unpinned ML deps are a known false-green (boots + structural tests pass, marquee
feature explodes on a fresh clone). Put ML deps in
`services/api/requirements-ml.txt` (kept out of the structural-test fast path,
documented in README as a separate install step) and **pin a verified window**:

- `lerobot` — pin to a version that includes v3 **and matches the build machine's
  Python**: latest is `0.5.1` (needs Python ≥3.12); `0.4.4` needs Python ≥3.10.
  The builder MUST: create the venv, detect the Python version, pin the
  highest-compatible `lerobot` (`>=0.4.4,<0.6` style with the exact resolved
  version recorded), and **verify the imports actually resolve**:
  `from lerobot.datasets.lerobot_dataset import LeRobotDataset` and the streaming
  symbol (`from lerobot.datasets.streaming_dataset import StreamingLeRobotDataset`
  — confirm the real import path; docs show two candidate paths).
- Transitive pins lerobot already constrains (record exact resolved versions):
  `torch>=2.7,<2.11`, `torchvision>=0.22,<0.26`, `torchcodec>=0.3,<0.11`,
  `av>=15,<16`, `datasets>=4,<5`, `huggingface-hub>=1,<2`, plus `pyarrow` and
  `numpy`. Use CPU torch wheels by default.
- `s3fs`/`fsspec` if the bridge uses range handles — pin compatibly.
- **End-to-end verification during the build (not just boot+tests):** record one
  synthetic episode, upload to B2, and run a streaming pass that decodes ≥1 frame
  and reports bytes-fetched ≪ total. A green `pnpm test:api` + boot is NOT
  sufficient evidence the marquee feature works — exercise it.
- Video decode: rely on torchcodec/`av` (bundled ffmpeg), not a bare system
  `ffmpeg` (Homebrew's is slim). Note this in README.

## 8. Standards checklist (must hold at review)

- [ ] S3-compatible API is the default; **zero** b2-native calls.
- [ ] Custom `user_agent_extra` on the boto3 S3 client (`b2ai-lerobot-b2-streaming`).
- [ ] Env vars exactly: `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`,
      `B2_BUCKET_NAME`, `B2_REGION`, `B2_PUBLIC_URL_BASE` (no `B2_KEY_ID`/`B2_ENDPOINT`/
      `B2_PUBLIC_URL` left anywhere — grep the whole tree incl. infra + docs).
- [ ] boto3 only in `repo/`; lerobot/torch SDK usage contained in `repo/`.
- [ ] All 5 Episode verbs present in the UI (`omitted_ui_verbs: []`).
- [ ] Create/edit forms follow the Form UX conventions (selectors + create-only hints).
- [ ] Bucket explorer `/files` intact; `/episodes` sample-scoped explorer added.
- [ ] Files <300 lines; structural tests + lint green; docs updated same-change.
- [ ] ML deps pinned + marquee streaming verified end-to-end on CPU from a fresh venv.
- [ ] README states honestly that the B2 streaming bridge fills LeRobot#764 and that
      stock `StreamingLeRobotDataset` is Hub-only — no implication LeRobot natively
      streams from B2.
- [ ] No real secrets; `.env.example` placeholders only.

# Railway Deployment

Deploy both services (web + api) on Railway.

> Note: the **episode ingest** and **B2 streaming** features need the ML deps
> (`services/api/requirements-ml.txt` — torch, lerobot, torchcodec). On Railway
> add `pip install -r requirements-ml.txt` to the API build command and size the
> service for a CPU torch install. The features run CPU-only by default; no GPU
> is required.

## Setup

1. Create a new Railway project
2. Add two services from the same repo:

### Web Service (Next.js) — `lerobot-s3-streaming-web`
- **Root Directory**: `apps/web`
- **Build Command**: `pnpm install && pnpm build`
- **Start Command**: `pnpm start`
- **Port**: `3000`

### API Service (FastAPI) — `lerobot-s3-streaming-api`
- **Root Directory**: `services/api`
- **Build Command**: `pip install -r requirements.txt && pip install -r requirements-ml.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Environment Variables

Set these on the API service:

| Variable | Value |
|----------|-------|
| `B2_REGION` | Your B2 region (e.g. `us-west-004`) — the S3 endpoint is derived from it |
| `B2_APPLICATION_KEY_ID` | Your B2 application key ID |
| `B2_APPLICATION_KEY` | Your B2 application key |
| `B2_BUCKET_NAME` | Your bucket name |
| `B2_PUBLIC_URL_BASE` | (optional) public base URL for the bucket; leave unset to use presigned URLs |
| `API_CORS_ORIGINS` | Your web service URL (e.g., `https://web-production-xxx.up.railway.app`) |

Set this on the Web service:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | Your API service URL (e.g., `https://api-production-xxx.up.railway.app`) |

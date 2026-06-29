"""Streaming-run orchestration over the B2/S3 ranged-GET bridge.

Single and concurrent N-worker runs. Each run reads v3 metadata for the chosen
episode(s), streams only the needed bytes from B2 via the bridge, decodes
frames, feeds a *mini* one-step training update on a tiny MLP (the training
data path — not a full policy train), and reports bytes_fetched ≪ total.

No boto3/lerobot imports here; the bridge (repo/b2_stream) and the meta reader
(service/episodes) own those.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.repo import b2_stream
from app.repo import lerobot_dataset as ld
from app.service import episodes as ep_service
from app.types import StreamRunRequest, StreamRunStats, WorkerStreamStats
from app.types.formatting import humanize_bytes

logger = logging.getLogger(__name__)

MAX_WORKERS = 8


class StreamError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _select_indices(req: StreamRunRequest) -> list[int]:
    if req.episode_index is not None:
        ep_service.get_episode(req.episode_index)  # 404s if missing
        return [req.episode_index]
    eps = ep_service.list_episodes(task=req.task)
    if not eps:
        raise StreamError("No episodes match the selection", status_code=404)
    return [e.episode_index for e in eps]


def _mini_train_step(table, mlp_state: dict, device: str) -> float:
    """One gradient step of a tiny MLP on the streamed state->action rows.

    This is deliberately trivial — it exists to prove the streamed bytes feed a
    real training loop, not to train a policy. Returns the batch loss.
    """
    import torch

    cols = table.column_names
    if "observation.state" not in cols or "action" not in cols:
        return 0.0
    x = torch.tensor(table.column("observation.state").to_pylist(), dtype=torch.float32, device=device)
    y = torch.tensor(table.column("action").to_pylist(), dtype=torch.float32, device=device)
    if x.ndim != 2 or x.shape[0] == 0:
        return 0.0

    model = mlp_state["model"]
    opt = mlp_state["opt"]
    opt.zero_grad()
    pred = model(x)
    loss = torch.nn.functional.mse_loss(pred, y)
    loss.backward()
    opt.step()
    return float(loss.detach().cpu())


def _new_mlp(dim: int, device: str) -> dict:
    import torch

    model = torch.nn.Sequential(
        torch.nn.Linear(dim, 32), torch.nn.ReLU(), torch.nn.Linear(32, dim)
    ).to(device)
    opt = torch.optim.SGD(model.parameters(), lr=1e-2)
    return {"model": model, "opt": opt}


def _stream_one_episode(index: int, mlp_state: dict, device: str, max_frames: int) -> dict:
    """Stream a single episode from B2: ranged-GET data rows + a video range,
    decode, run one mini-train step. Returns per-episode counters."""
    ep = ep_service.get_episode(index)
    objs = ep_service.list_keys(ep.prefix)
    total_bytes = sum(o["size"] for o in objs)

    data_key = next((o["key"] for o in objs if o["key"].endswith(".parquet") and "/data/" in o["key"]), None)
    bytes_fetched = 0
    frames = 0
    loss = None

    if data_key:
        table, fetched = b2_stream.fetch_data_rows(
            data_key, ep.dataset_from_index, ep.dataset_to_index
        )
        bytes_fetched += fetched
        frames = table.num_rows
        if mlp_state is not None:
            loss = _mini_train_step(table, mlp_state, device)

    # Stream one camera's video byte-range to prove video chunking too.
    if ep.videos:
        v = ep.videos[0]
        duration = ep.num_frames / max(ep.fps, 1)
        try:
            vframes, vfetched, _vtotal = b2_stream.fetch_video_range(
                v.key, 0.0, duration, ep.fps
            )
            bytes_fetched += vfetched
            frames = max(frames, vframes)
        except Exception as e:  # video decode is best-effort
            logger.warning("Video stream skipped for ep %d: %s", index, e)

    if max_frames and frames > max_frames:
        frames = max_frames

    return {
        "frames": frames,
        "bytes_fetched": bytes_fetched,
        "total_bytes": total_bytes,
        "loss": loss,
    }


def _run_worker(worker_id: int, indices: list[int], device: str, max_frames: int) -> dict:
    mlp_state = _new_mlp(6, device)
    start = time.time()
    frames = 0
    fetched = 0
    total = 0
    loss_start = None
    loss_end = None
    for idx in indices:
        r = _stream_one_episode(idx, mlp_state, device, max_frames)
        frames += r["frames"]
        fetched += r["bytes_fetched"]
        total += r["total_bytes"]
        if r["loss"] is not None:
            if loss_start is None:
                loss_start = r["loss"]
            loss_end = r["loss"]
    elapsed = max(time.time() - start, 1e-6)
    return {
        "worker_id": worker_id,
        "episodes": len(indices),
        "frames": frames,
        "fetched": fetched,
        "total": total,
        "elapsed": elapsed,
        "loss_start": loss_start,
        "loss_end": loss_end,
    }


def run_stream(req: StreamRunRequest) -> StreamRunStats:
    indices = _select_indices(req)
    workers = max(1, min(req.workers, MAX_WORKERS, len(indices)))
    device = ld.select_device()

    # Round-robin episodes across workers (each worker gets a task split).
    buckets: list[list[int]] = [[] for _ in range(workers)]
    for i, idx in enumerate(indices):
        buckets[i % workers].append(idx)
    buckets = [b for b in buckets if b]

    start = time.time()
    if len(buckets) == 1:
        results = [_run_worker(0, buckets[0], device, req.max_frames)]
    else:
        with ThreadPoolExecutor(max_workers=len(buckets)) as pool:
            results = list(
                pool.map(
                    lambda a: _run_worker(a[0], a[1], device, req.max_frames),
                    list(enumerate(buckets)),
                )
            )
    elapsed = max(time.time() - start, 1e-6)

    per_worker = [
        WorkerStreamStats(
            worker_id=r["worker_id"],
            episodes_streamed=r["episodes"],
            frames_decoded=r["frames"],
            bytes_fetched=r["fetched"],
            bytes_fetched_human=humanize_bytes(r["fetched"]),
            throughput_frames_per_s=r["frames"] / r["elapsed"],
            elapsed_s=round(r["elapsed"], 3),
        )
        for r in results
    ]
    fetched = sum(r["fetched"] for r in results)
    frames = sum(r["frames"] for r in results)
    total = sum(r["total"] for r in results)
    losses_start = [r["loss_start"] for r in results if r["loss_start"] is not None]
    losses_end = [r["loss_end"] for r in results if r["loss_end"] is not None]

    logger.info(
        "Stream run: workers=%d episodes=%d frames=%d fetched=%d total=%d ratio=%.4f",
        len(buckets), len(indices), frames, fetched, total,
        (fetched / total) if total else 0.0,
    )
    return StreamRunStats(
        workers=len(buckets),
        episodes_streamed=len(indices),
        frames_decoded=frames,
        bytes_fetched=fetched,
        bytes_fetched_human=humanize_bytes(fetched),
        total_dataset_bytes=total,
        total_dataset_bytes_human=humanize_bytes(total),
        fetch_ratio=round((fetched / total), 6) if total else 0.0,
        elapsed_s=round(elapsed, 3),
        throughput_frames_per_s=round(frames / elapsed, 2),
        train_loss_start=round(sum(losses_start) / len(losses_start), 6) if losses_start else None,
        train_loss_end=round(sum(losses_end) / len(losses_end), 6) if losses_end else None,
        device=device,
        per_worker=per_worker,
    )

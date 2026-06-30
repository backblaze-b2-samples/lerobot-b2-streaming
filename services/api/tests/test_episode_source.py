"""Tests for the user-selectable ingest source dataset + derived shape.

Hermetic: the repo/B2 and ML boundaries are monkeypatched, so these run in the
default `pnpm test:api` path with no network and no ML deps.
"""

from types import SimpleNamespace

import pytest

from app.repo.hf_source import RealSourceUnavailable
from app.service import episodes
from app.types import EpisodeCreateRequest
from app.types.episodes import MAX_EPISODE_FRAMES


def _req(**overrides) -> EpisodeCreateRequest:
    base = dict(task="Pick up the cube")
    base.update(overrides)
    return EpisodeCreateRequest(**base)


def test_validate_accepts_default_preset_and_custom_sources():
    # None (server default), a curated preset, and a custom owner/name all pass.
    episodes._validate_create(_req(source_repo_id=None))
    episodes._validate_create(_req(source_repo_id="lerobot/svla_so101_pickplace"))
    episodes._validate_create(_req(source_repo_id="my-org/my-so101-dataset"))


@pytest.mark.parametrize("bad", ["not-a-repo", "owner/", "/name", "owner name", "owner//name"])
def test_validate_rejects_malformed_source_repo_id(bad):
    with pytest.raises(episodes.EpisodeError):
        episodes._validate_create(_req(source_repo_id=bad))


@pytest.mark.parametrize("bad", [0, -5, MAX_EPISODE_FRAMES + 1])
def test_validate_rejects_out_of_range_max_frames(bad):
    with pytest.raises(episodes.EpisodeError):
        episodes._validate_create(_req(max_frames=bad))


def test_create_fails_loud_when_chosen_source_cannot_load(monkeypatch):
    """A user-chosen source that can't load surfaces a 400 EpisodeError rather
    than silently recording the synthetic fallback the user never asked for."""
    monkeypatch.setattr(episodes, "_next_episode_index", lambda: 0)
    monkeypatch.setattr(episodes.ld, "select_device", lambda: "cpu")
    monkeypatch.setattr(episodes.ld, "make_temp_root", lambda: "/tmp/lerobot-test/root")
    monkeypatch.setattr(episodes, "_cleanup_root", lambda root: None)

    def boom(**_kwargs):
        raise RealSourceUnavailable("not a v3 dataset")

    monkeypatch.setattr(episodes.ld, "build_episode", boom)

    with pytest.raises(episodes.EpisodeError) as exc:
        episodes.create_episode(_req(source_repo_id="owner/missing"))
    assert exc.value.status_code == 400
    assert "owner/missing" in exc.value.detail


def test_create_passes_max_frames_and_does_not_impose_shape(monkeypatch):
    """create_episode forwards only source/task/max_frames to build_episode —
    the shape (cameras/fps/resolution/dims) is derived there, not imposed here."""
    captured = {}
    monkeypatch.setattr(episodes, "_next_episode_index", lambda: 7)
    monkeypatch.setattr(episodes.ld, "select_device", lambda: "cpu")
    monkeypatch.setattr(episodes.ld, "make_temp_root", lambda: "/tmp/lerobot-test/root")
    monkeypatch.setattr(episodes, "_cleanup_root", lambda root: None)
    monkeypatch.setattr(episodes, "_upload_tree", lambda root, idx: (123, 6))
    monkeypatch.setattr(
        episodes, "get_episode", lambda idx: SimpleNamespace(num_frames=42, num_cameras=1)
    )
    monkeypatch.setattr(episodes, "EpisodeCreateResult", lambda **kw: kw)

    def fake_build(**kwargs):
        captured.update(kwargs)
        return "so100_follower"

    monkeypatch.setattr(episodes.ld, "build_episode", fake_build)
    episodes.create_episode(_req(source_repo_id="lerobot/pusht", max_frames=42))

    assert captured["source_repo_id"] == "lerobot/pusht"
    assert captured["max_frames"] == 42
    # No imposed shape knobs leak into the build call.
    for gone in ("num_cameras", "num_frames", "fps", "resolution"):
        assert gone not in captured


def test_inspect_source_maps_unloadable_to_400(monkeypatch):
    def boom(repo_id, source_episode=0):
        raise RealSourceUnavailable("gated")

    monkeypatch.setattr(episodes.hf_source, "inspect_source", boom)
    with pytest.raises(episodes.EpisodeError) as exc:
        episodes.inspect_source("owner/gated")
    assert exc.value.status_code == 400


def test_inspect_source_rejects_malformed_repo_id():
    with pytest.raises(episodes.EpisodeError):
        episodes.inspect_source("not-a-repo")


async def test_options_endpoint_exposes_sources(client):
    resp = await client.get("/episodes/options")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"], "curated source list must be non-empty"
    assert body["default_source"] in body["sources"]
    assert body["max_frames"] >= 1


async def test_source_info_endpoint_returns_real_shape(client, monkeypatch):
    def fake_inspect(repo_id, source_episode=0):
        return {
            "repo_id": repo_id,
            "robot_type": "so100_follower",
            "fps": 30,
            "cameras": [{"name": "up", "height": 480, "width": 640}],
            "num_cameras": 1,
            "episode_frames": 320,
            "state_dim": 6,
            "action_dim": 6,
            "task": "Pick up the cube",
        }

    monkeypatch.setattr(episodes.hf_source, "inspect_source", fake_inspect)
    resp = await client.get("/episodes/source-info?repo_id=lerobot/pusht")
    assert resp.status_code == 200
    body = resp.json()
    assert body["num_cameras"] == 1
    assert body["cameras"][0]["width"] == 640
    assert body["episode_frames"] == 320


async def test_source_info_endpoint_400s_on_bad_repo(client):
    resp = await client.get("/episodes/source-info?repo_id=not-a-repo")
    assert resp.status_code == 400

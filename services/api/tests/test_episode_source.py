"""Tests for the user-selectable ingest source dataset.

Hermetic: the repo/B2 and ML boundaries are monkeypatched, so these run in the
default `pnpm test:api` path with no network and no ML deps.
"""

import pytest

from app.repo.hf_source import RealSourceUnavailable
from app.service import episodes
from app.types import EpisodeCreateRequest


def _req(**overrides) -> EpisodeCreateRequest:
    base = dict(task="Pick up the cube", num_cameras=2, num_frames=60, fps=30, resolution=256)
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


async def test_options_endpoint_exposes_sources(client):
    resp = await client.get("/episodes/options")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"], "curated source list must be non-empty"
    assert body["default_source"] in body["sources"]

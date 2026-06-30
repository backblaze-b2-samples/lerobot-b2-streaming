"""Tests for the real-robot footage source (`repo/hf_source.py`).

The hermetic part (signatures, fallback wiring, per-repo cache, state/action
pass-through) runs in the default `pnpm test:api` path with NO network and NO ML
deps. The end-to-end "actually decode a real frame from the Hub" check is an
INTEGRATION test that is skipped unless `RUN_HF_INTEGRATION=1` is set, so the
default test run and `pnpm check:structure` stay network-free and fast.
"""

import importlib
import inspect
import os

import pytest

from app.repo import hf_source
from app.repo import lerobot_dataset as ld


def test_real_frame_signature_indexes_a_source_episode():
    """real_frame no longer takes synthetic shape knobs (num_cameras/resolution):
    the recording mirrors the source. It indexes a timestep into a chosen source
    episode of a chosen repo."""
    params = list(inspect.signature(hf_source.real_frame).parameters)
    assert params[:2] == ["t", "total"]
    assert "source_episode" in params
    assert "repo_id" in params
    # The removed synthetic knobs must be gone.
    assert "num_cameras" not in params
    assert "resolution" not in params


def test_source_constants_point_at_a_real_v3_dataset():
    assert hf_source.SOURCE_REPO_ID == "lerobot/svla_so101_pickplace"
    assert hf_source.SOURCE_ROBOT_TYPE == "so100_follower"
    assert hf_source.SOURCE_EPISODES  # non-empty


def test_vec_or_placeholder_passes_real_vectors_through_verbatim():
    """A source vector whose width matches the declared dim is used verbatim —
    the real signal is never replaced with a fabricated one."""
    np = importlib.import_module("numpy")
    sample = {"observation.state": np.array([1, 2, 3, 4, 5, 6], dtype=np.float32)}
    out = hf_source._vec_or_placeholder(sample, "observation.state", dim=6, t=0, total=10)
    assert out.shape == (6,)
    assert out.dtype == np.float32
    assert out.tolist() == [1, 2, 3, 4, 5, 6]


def test_vec_or_placeholder_preserves_high_dof_widths():
    """A 14-DoF (e.g. bimanual ALOHA) vector is preserved at its real width, not
    coerced down to 6 — the old _fit_6dof behaviour that mangled it is gone."""
    np = importlib.import_module("numpy")
    real = np.arange(14, dtype=np.float32)
    sample = {"action": real}
    out = hf_source._vec_or_placeholder(sample, "action", dim=14, t=3, total=10)
    assert out.shape == (14,)
    assert out.tolist() == real.tolist()


def test_vec_or_placeholder_derives_when_source_lacks_the_stream():
    """Only when the source has no such stream do we derive a placeholder — of
    the declared width, so the v3 feature schema still holds."""
    np = importlib.import_module("numpy")
    out = hf_source._vec_or_placeholder({}, "observation.state", dim=7, t=5, total=10)
    assert out.shape == (7,)
    assert out.dtype == np.float32
    assert np.isfinite(out).all()


def test_resolve_frame_source_falls_back_to_synthetic_when_default_unavailable(monkeypatch):
    """If the DEFAULT Hub source can't load, _resolve_frame_source must yield the
    synthetic fallback spec (fixed shape) rather than raising — so the live demo
    never crashes offline. We stub the loader to fail."""

    def boom(*_args, **_kwargs):
        raise hf_source.RealSourceUnavailable("offline")

    monkeypatch.setattr(hf_source, "_load_source", boom)
    spec = ld._resolve_frame_source(
        source_repo_id=hf_source.SOURCE_REPO_ID, allow_synth_fallback=True
    )
    assert spec.robot_type == "synthetic"
    assert spec.source_label == "synthetic-fallback"
    assert spec.num_frames >= 1
    # The fallback frame is synth-shaped at the fixed fallback resolution.
    frame = spec.frame_fn(0, spec.num_frames)
    assert "observation.images.cam_0" in frame
    assert frame["observation.images.cam_0"].shape == (256, 256, 3)


def test_resolve_frame_source_reraises_for_a_chosen_source(monkeypatch):
    """A user-CHOSEN source (allow_synth_fallback=False) must surface a load
    failure instead of silently substituting synthetic frames."""

    def boom(*_args, **_kwargs):
        raise hf_source.RealSourceUnavailable("not a v3 dataset")

    monkeypatch.setattr(hf_source, "_load_source", boom)
    with pytest.raises(hf_source.RealSourceUnavailable):
        ld._resolve_frame_source(
            source_repo_id="owner/custom", allow_synth_fallback=False
        )


def test_max_frames_caps_below_the_episode_length(monkeypatch):
    """An optional max_frames lowers the recorded length below the source episode
    (and the safety ceiling always applies)."""

    def fake_inspect(repo_id, source_episode=0):
        return {
            "repo_id": repo_id,
            "robot_type": "so100_follower",
            "fps": 30,
            "cameras": [{"name": "up", "height": 480, "width": 640}],
            "num_cameras": 1,
            "episode_frames": 400,
            "state_dim": 6,
            "action_dim": 6,
            "task": "Pick up the cube",
        }

    monkeypatch.setattr(hf_source, "inspect_source", fake_inspect)
    capped = ld._resolve_frame_source(source_repo_id="owner/x", max_frames=50)
    assert capped.num_frames == 50
    assert capped.fps == 30
    assert capped.cameras == [{"height": 480, "width": 640}]
    full = ld._resolve_frame_source(source_repo_id="owner/x", max_frames=None)
    assert full.num_frames == 400


def test_sources_are_cached_per_repo_id(monkeypatch):
    """Each source is cached under its repo_id so switching datasets never
    thrashes an already-loaded one, and the metadata accessors read per repo."""
    monkeypatch.setattr(hf_source, "_CACHE", {})
    a = hf_source._Source(
        dataset=object(),
        episode_rows=[[0, 1], [2, 3], [4, 5]],
        cameras=[
            hf_source._SourceCamera("observation.images.up", 480, 640),
            hf_source._SourceCamera("observation.images.side", 480, 640),
        ],
        fps=30,
        robot_type="so100_follower",
        state_dim=6,
        action_dim=6,
        task="Pick up the cube",
    )
    b = hf_source._Source(
        dataset=object(),
        episode_rows=[[0]],
        cameras=[hf_source._SourceCamera("observation.image", 96, 96)],
        fps=10,
        robot_type="aloha",
        state_dim=14,
        action_dim=14,
        task=None,
    )
    hf_source._CACHE["owner/a"] = a
    hf_source._CACHE["owner/b"] = b

    # Pre-seeded entries are returned without ever touching the (heavy) loader.
    assert hf_source._load_source("owner/a") is a
    assert hf_source.num_source_episodes("owner/a") == 3
    assert hf_source.num_source_episodes("owner/b") == 1
    assert hf_source.source_fps("owner/a") == 30
    assert hf_source.source_fps("owner/b") == 10
    assert hf_source.source_robot_type("owner/a") == "so100_follower"
    assert hf_source.source_robot_type("owner/b") == "aloha"

    # inspect_source reports each source's real, distinct shape.
    info_a = hf_source.inspect_source("owner/a")
    assert info_a["num_cameras"] == 2
    assert info_a["cameras"][0] == {"name": "up", "height": 480, "width": 640}
    assert info_a["state_dim"] == 6
    info_b = hf_source.inspect_source("owner/b")
    assert info_b["num_cameras"] == 1
    assert info_b["state_dim"] == 14

    # An unknown repo reports "not loaded" — never another repo's data.
    assert hf_source.num_source_episodes("owner/unknown") == 0
    assert hf_source.source_fps("owner/unknown") is None
    assert hf_source.source_robot_type("owner/unknown") == hf_source.SOURCE_ROBOT_TYPE


@pytest.mark.skipif(
    os.environ.get("RUN_HF_INTEGRATION") != "1",
    reason="network/Hub integration test; set RUN_HF_INTEGRATION=1 to run",
)
def test_real_frame_decodes_genuine_footage():
    """INTEGRATION: pull the real source and assert a decoded frame is genuine
    camera footage at the source's native (non-square) resolution."""
    import numpy as np

    info = hf_source.inspect_source(hf_source.SOURCE_REPO_ID)
    cam0 = info["cameras"][0]
    frame = hf_source.real_frame(t=10, total=60)
    img = frame["observation.images.cam_0"]
    assert img.shape == (cam0["height"], cam0["width"], 3)
    assert img.dtype == np.uint8
    # Real footage has structure the synthetic gradient lacks: far higher local
    # variance than the smooth monotonic diagonal sweep.
    assert float(img.std()) > 5.0
    # Real state should be present, finite, and at the source's real width.
    state = frame["observation.state"]
    assert state.shape == (info["state_dim"],)
    assert np.isfinite(state).all()

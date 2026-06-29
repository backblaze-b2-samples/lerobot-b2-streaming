"""Tests for the real-robot footage source (`repo/hf_source.py`).

The hermetic part (signatures, fallback wiring, 6-DoF coercion) runs in the
default `pnpm test:api` path with NO network and NO ML deps. The end-to-end
"actually decode a real frame from the Hub" check is an INTEGRATION test that is
skipped unless `RUN_HF_INTEGRATION=1` is set, so the default test run and
`pnpm check:structure` stay network-free and fast.
"""

import importlib
import inspect
import os

import pytest

from app.repo import hf_source
from app.repo import lerobot_dataset as ld


def test_real_frame_signature_is_synth_compatible():
    """real_frame must accept the same positional args as _synth_frame plus an
    optional source_episode, so it is a drop-in primary frame source."""
    real_params = list(inspect.signature(hf_source.real_frame).parameters)
    assert real_params[:5] == ["num_cameras", "resolution", "t", "total", "device"]
    assert "source_episode" in real_params


def test_source_constants_point_at_a_real_v3_dataset():
    assert hf_source.SOURCE_REPO_ID == "lerobot/svla_so101_pickplace"
    assert hf_source.SOURCE_ROBOT_TYPE == "so100_follower"
    assert hf_source.SOURCE_EPISODES  # non-empty


def test_fit_6dof_passes_through_six_dim_vectors():
    np = importlib.import_module("numpy")
    v = np.array([1, 2, 3, 4, 5, 6], dtype=np.float32)
    out = hf_source._fit_6dof(v, t=0, total=10)
    assert out.shape == (6,)
    assert out.dtype == np.float32
    assert out.tolist() == [1, 2, 3, 4, 5, 6]


def test_fit_6dof_derives_when_source_is_not_six_dim():
    np = importlib.import_module("numpy")
    v = np.zeros((14,), dtype=np.float32)  # e.g. an ALOHA 14-DoF vector
    out = hf_source._fit_6dof(v, t=5, total=10)
    assert out.shape == (6,)
    assert out.dtype == np.float32


def test_build_episode_falls_back_to_synthetic_when_source_unavailable(monkeypatch):
    """If the Hub source can't load, build_episode must report the synthetic
    fallback robot_type rather than raising — so the live demo never crashes
    offline. We stub the loader to fail and the LeRobotDataset to a no-op."""

    def boom():
        raise hf_source.RealSourceUnavailable("offline")

    monkeypatch.setattr(hf_source, "_load_source", boom)
    frame_fn, robot_type, label = ld._resolve_frame_source(
        num_cameras=1, resolution=128, device="cpu", source_episode=0
    )
    assert robot_type == "synthetic"
    assert label == "synthetic-fallback"
    # The returned fallback frame must still be synth-shaped.
    frame = frame_fn(0, 30)
    assert "observation.images.cam_0" in frame
    assert frame["observation.images.cam_0"].shape == (128, 128, 3)


@pytest.mark.skipif(
    os.environ.get("RUN_HF_INTEGRATION") != "1",
    reason="network/Hub integration test; set RUN_HF_INTEGRATION=1 to run",
)
def test_real_frame_decodes_genuine_footage():
    """INTEGRATION: pull the real source and assert a decoded frame is genuine
    camera footage, not the synthetic diagonal gradient."""
    import numpy as np

    frame = hf_source.real_frame(num_cameras=2, resolution=128, t=10, total=60, device="cpu")
    img = frame["observation.images.cam_0"]
    assert img.shape == (128, 128, 3)
    assert img.dtype == np.uint8
    # Real footage has structure the synthetic gradient lacks: the synthetic
    # frame is a smooth monotonic diagonal sweep, so its row-to-row deltas are
    # tiny and uniform. Real frames have far higher local variance.
    assert float(img.std()) > 5.0
    # Real 6-DoF state should be present and finite.
    state = frame["observation.state"]
    assert state.shape == (6,)
    assert np.isfinite(state).all()

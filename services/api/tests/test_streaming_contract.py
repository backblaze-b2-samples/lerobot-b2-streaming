"""No-network contract tests for the LeRobot v3 + B2 streaming surface.

These run in the fast path (no ML deps, no B2). They guard the module/route
contract so a refactor that breaks the streaming bridge or episode API is caught
even before the ML end-to-end verification runs.
"""

import inspect

from app.repo import b2_objects, b2_stream
from app.repo import lerobot_dataset as ld
from app.types.episodes import (
    ALLOWED_FPS,
    ALLOWED_NUM_CAMERAS,
    ALLOWED_NUM_FRAMES,
    ALLOWED_RESOLUTIONS,
    PRESET_TASKS,
)


def test_ranged_get_exists_on_object_repo():
    """The marquee S3 op — a ranged GET — must exist with (key, start, end)."""
    assert hasattr(b2_objects, "get_object_range")
    params = list(inspect.signature(b2_objects.get_object_range).parameters)
    assert params == ["key", "start", "end"]


def test_bridge_exposes_fetch_helpers():
    assert hasattr(b2_stream, "fetch_data_rows")
    assert hasattr(b2_stream, "fetch_video_range")


def test_device_autodetect_defaults_to_cpu_without_torch(monkeypatch):
    """With torch unimportable, select_device() must fall back to CPU, never
    raise or hard-require a GPU."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("torch not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ld.select_device() == "cpu"


def test_lerobot_build_helpers_present():
    """Guard the real v3 build entrypoints we wrap."""
    for fn in ("build_episode", "read_info", "read_episodes_meta", "read_tasks"):
        assert hasattr(ld, fn), f"missing lerobot_dataset.{fn}"


def test_build_episode_sources_real_footage():
    """The frame source is the real Hub footage adapter, with a synthetic
    fallback — not synthetic-as-primary. Guard the wiring without any network."""
    from app.repo import hf_source

    # The real source is wired in and resolves to a frame fn + robot_type.
    assert hasattr(ld, "_resolve_frame_source")
    assert hf_source.SOURCE_REPO_ID.startswith("lerobot/")
    # build_episode forwards a source_episode selector to rotate real clips.
    params = list(inspect.signature(ld.build_episode).parameters)
    assert "source_episode" in params


def test_form_option_sets_nonempty():
    assert PRESET_TASKS
    assert ALLOWED_NUM_CAMERAS == [1, 2, 3]
    assert ALLOWED_NUM_FRAMES == [30, 60, 120]
    assert ALLOWED_FPS == [10, 30]
    assert ALLOWED_RESOLUTIONS == [128, 256]


def test_episode_routes_registered():
    from main import app

    paths = set(app.openapi()["paths"].keys())
    for expected in ("/episodes", "/episodes/{index}", "/episodes/options", "/stream"):
        assert expected in paths, f"route {expected} not registered"

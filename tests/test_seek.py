"""Red tests for the video-seek bugfix task.

All times are integer milliseconds (ms).  An index is::

    {"keyframes": [...], "duration": int, "timescale": int}

No test sleeps, uses randomness or touches the network.
"""

import pytest

from playback import seek


class _ProbeKeyframes:
    """Read-only keyframe sequence that counts every access."""

    def __init__(self, values):
        self._values = list(values)
        self.reads = 0

    def __len__(self):
        return len(self._values)

    def __getitem__(self, position):
        self.reads += 1
        return self._values[position]

    def __iter__(self):
        for value in self._values:
            self.reads += 1
            yield value


def test_find_keyframe_large_index_uses_binary_search():
    keyframes = _ProbeKeyframes(i * 40 for i in range(2048))
    index = {"keyframes": keyframes, "duration": 81880, "timescale": 1000}

    assert seek.find_keyframe(index, 60017) == 60000
    assert keyframes.reads <= 64


def test_seek_plan_precise_decodes_to_target():
    index = {
        "keyframes": [0, 1000, 2000, 3000],
        "duration": 4000,
        "timescale": 1000,
    }

    precise = seek.seek_plan(index, 1500, "precise")
    fast = seek.seek_plan(index, 1500, "fast")

    assert precise == {"keyframe": 1000, "decode_to": 1500, "delta_ms": 500}
    assert fast == {"keyframe": 1000, "decode_to": 1000, "delta_ms": 500}


def test_seek_plan_clamps_target_beyond_duration():
    index = {"keyframes": [0, 1000, 2000], "duration": 2500, "timescale": 1000}

    plan = seek.seek_plan(index, 999999, "precise")

    assert plan["keyframe"] == 2000
    assert plan["decode_to"] == 2500
    assert plan["delta_ms"] == 500
    assert seek.clamp_target(index, 2500) == 2500
    assert seek.clamp_target(index, 999999) == 2500
    with pytest.raises(seek.SeekError):
        seek.clamp_target(index, -1)


def test_pts_to_frame_exact_for_ntsc_29_97():
    fps = (30000, 1001)

    assert seek.pts_to_frame(0, 1000, fps) == 0
    assert seek.pts_to_frame(1001, 1000, fps) == 30
    assert seek.pts_to_frame(10010, 1000, fps) == 300
    assert seek.pts_to_frame(33367, 1000, fps) == 1000


def test_frame_roundtrip_closes_for_ntsc():
    fps = (30000, 1001)

    pts = seek.frame_to_pts(1000, 1000, fps)
    assert pts == 33367

    frame = seek.pts_to_frame(pts, 1000, fps)
    assert frame == 1000
    assert abs(seek.frame_to_pts(frame, 1000, fps) - pts) <= 1


def test_merge_ranges_merges_touching_intervals():
    ranges = [(300, 400), (0, 100), (150, 260), (100, 200)]

    assert seek.merge_ranges(ranges, 0) == [(0, 260), (300, 400)]
    assert seek.merge_ranges([], 0) == []
    assert seek.merge_ranges([(0, 100), (110, 200)], 5) == [(0, 100), (110, 200)]
    assert seek.merge_ranges([(0, 100), (110, 200)], 10) == [(0, 200)]


def test_estimate_decode_cost_respects_keyframe_distance():
    far = {"keyframe": 0, "decode_to": 1200, "delta_ms": 1200}
    near = {"keyframe": 1000, "decode_to": 1200, "delta_ms": 200}
    on_keyframe = {"keyframe": 1000, "decode_to": 1000, "delta_ms": 0}

    assert seek.estimate_decode_cost(far, 40) == 30
    assert seek.estimate_decode_cost(near, 40) == 5
    assert seek.estimate_decode_cost(on_keyframe, 40) == 0


def test_seek_batch_sorts_targets_ascending():
    index = {"keyframes": [0, 1000, 2000], "duration": 3000, "timescale": 1000}

    batch = seek.seek_batch(index, [2500, 1500, 1200])

    assert batch["order"] == [1200, 1500, 2500]
    assert [plan["decode_to"] for plan in batch["results"]] == [1200, 1500, 2500]
    assert batch["decodes"] == 2


def test_conversion_uses_media_timescale():
    fps = (30000, 1001)
    timescale = 44100

    assert seek.pts_to_frame(10010, timescale, fps) == 300
    assert seek.pts_to_frame(20020, timescale, fps) == 600
    assert seek.frame_to_pts(300, timescale, fps) == 10010


def test_seek_batch_rejects_invalid_target_atomically():
    index = {"keyframes": [0, 1000, 2000], "duration": 3000, "timescale": 1000}

    with pytest.raises(seek.SeekError):
        seek.seek_batch(index, [500, -1, 1500])

    with pytest.raises(seek.SeekError):
        seek.seek_batch(index, [500, 3001])


def test_seek_plan_target_on_keyframe_has_zero_delta():
    index = {"keyframes": [0, 1000, 2000], "duration": 3000, "timescale": 1000}

    for strategy in ("precise", "fast"):
        plan = seek.seek_plan(index, 2000, strategy)
        assert plan["keyframe"] == 2000
        assert plan["decode_to"] == 2000
        assert plan["delta_ms"] == 0


def test_empty_index_and_empty_targets_return_empty():
    index = {"keyframes": [], "duration": 0, "timescale": 1000}

    assert seek.seek_batch(index, []) == {
        "order": [],
        "results": [],
        "decodes": 0,
    }
    assert seek.merge_ranges([], 10) == []


def test_duration_zero_only_allows_zero():
    index = {"keyframes": [0], "duration": 0, "timescale": 1000}

    assert seek.clamp_target(index, 0) == 0
    assert seek.clamp_target(index, 10) == 0
    assert seek.seek_plan(index, 0, "precise") == {
        "keyframe": 0,
        "decode_to": 0,
        "delta_ms": 0,
    }


def test_roundtrip_within_one_ms_across_frame_rates():
    cases = [
        (10010, 1000, (30000, 1001)),
        (100100, 1000, (30000, 1001)),
        (1000, 1000, 25),
        (500, 1000, 10),
        (2000, 1000, 50),
        (10010, 44100, (30000, 1001)),
    ]

    for pts, timescale, fps in cases:
        frame = seek.pts_to_frame(pts, timescale, fps)
        roundtrip = seek.frame_to_pts(frame, timescale, fps)
        assert abs(roundtrip - pts) <= 1


def test_seek_batch_ascending_decode_count_equals_intervals():
    index = {
        "keyframes": [0, 1000, 2000, 3000],
        "duration": 4000,
        "timescale": 1000,
    }

    batch = seek.seek_batch(index, [500, 1500, 2500, 3500])

    assert batch["order"] == [500, 1500, 2500, 3500]
    assert len(batch["results"]) == 4
    assert batch["decodes"] == 4

    grouped = seek.seek_batch(index, [1200, 1450, 1800])
    assert grouped["decodes"] == 1

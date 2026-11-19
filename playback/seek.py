"""Seek planning primitives for an offline video player.

Coordinate contract:

* Every time value exchanged by this module is an integer number of
  milliseconds (ms): ``target_ms``, ``delta_ms``, ``gap_ms``,
  ``avg_frame_ms``, keyframe pts, durations and the ``pts`` argument all use
  ms.
* ``pts`` means presentation timestamp.  An index is a mapping::

      {"keyframes": [int, ...], "duration": int, "timescale": int}

  where ``keyframes`` is an ascending list of keyframe pts (ms), ``duration``
  is the media length (ms) and ``timescale`` is the media timebase in ticks
  per second.
* Returned times are compared with the expected values with a tolerance of
  1 ms; frame numbers and frame counts are integers and compare exactly.

Nothing here sleeps, uses randomness or touches the network.
"""

from __future__ import annotations


class SeekError(ValueError):
    """Raised when a seek index, target, strategy or batch is invalid."""


def find_keyframe(index, target_ms):
    """Return the latest keyframe pts (ms) that does not exceed ``target_ms``.

    ``index["keyframes"]`` is an ascending sequence of keyframe pts in
    milliseconds; ``target_ms`` is also in ms.  The lookup must use a binary
    search so its cost grows like ``O(log n)`` with the number of keyframes
    instead of linearly with the clip length: the acceptance test counts
    element reads and allows only a logarithmic budget.  The sequence only
    needs ``len()`` and integer indexing, so both plain lists and read-only
    sequence wrappers are supported.

    A target before the first keyframe returns the first keyframe; a target
    after the last one returns the last keyframe.  An empty keyframe list or a
    negative target raises :class:`SeekError`.  Results are exact integer
    milliseconds; the 1 ms tolerance applies when callers compare times.
    """

    raise NotImplementedError


def seek_plan(index, target_ms, strategy):
    """Plan one seek and return its decode window.

    ``strategy="precise"`` decodes from the nearest preceding keyframe through
    ``decode_to == clamp_target(index, target_ms)`` so the decoded picture
    matches the requested time code.  ``strategy="fast"`` stops on the
    keyframe and returns ``decode_to == keyframe``.  Both strategies return
    exactly::

        {"keyframe": int, "decode_to": int, "delta_ms": int}

    where ``delta_ms`` is the distance from the keyframe to the clamped
    target (the seek error still visible on the keyframe).  ``target_ms`` is
    clamped into ``[0, index["duration"]]`` first; a negative target or an
    unsupported strategy raises :class:`SeekError`.  All times are integer
    milliseconds and compare with a 1 ms tolerance.
    """

    raise NotImplementedError


def clamp_target(index, target_ms):
    """Clamp ``target_ms`` into ``[0, index["duration"]]``.

    ``index["duration"]`` is the media length in ms.  A negative target is
    invalid and raises :class:`SeekError` instead of being silently clamped
    to zero; a target beyond the duration is clamped down to the duration so
    the decoder never receives an out-of-range timestamp.  The result is an
    integer millisecond value and compares with a 1 ms tolerance.
    """

    raise NotImplementedError


def pts_to_frame(pts, timescale, fps):
    """Convert a millisecond timestamp to the nearest frame index.

    ``pts`` is in milliseconds (ms), ``timescale`` is the media timebase in
    ticks per second, and ``fps`` is either an integer frame rate or an exact
    ``(num, den)`` pair, for example ``(30000, 1001)`` for 29.97 fps.  The
    conversion uses integer arithmetic only -- a floating point fps is not
    allowed and must not make the frame number drift::

        ticks = pts * timescale // 1000
        frame = round(ticks * num / (den * timescale))

    where ``round`` means round to the nearest frame.  ``pts`` must be
    non-negative and ``timescale``/``fps`` must be positive, otherwise
    :class:`SeekError` is raised.  Frame numbers are exact integers; the 1 ms
    tolerance applies to timestamp comparisons.
    """

    raise NotImplementedError


def frame_to_pts(frame, timescale, fps):
    """Convert a frame index back to a millisecond timestamp.

    This is the inverse of :func:`pts_to_frame` for frame-aligned timestamps::

        ticks = round(frame * den * timescale / num)
        pts = round(ticks * 1000 / timescale)

    For a frame-aligned input the round trip
    ``frame_to_pts(pts_to_frame(x))`` closes within 1 ms even at 29.97 fps;
    an arbitrary millisecond value naturally snaps to its nearest frame
    boundary.  ``frame`` must be non-negative and ``timescale``/``fps`` must
    be positive, otherwise :class:`SeekError` is raised.  Results are integer
    milliseconds and compare with a 1 ms tolerance.
    """

    raise NotImplementedError


def merge_ranges(ranges, gap_ms):
    """Merge overlapping or touching ``(start_ms, end_ms)`` ranges.

    Input ranges are pairs of integer milliseconds, not necessarily sorted.
    They are sorted by start and two ranges merge when the next start is at or
    before ``current_end + gap_ms`` -- so overlaps and exact touches
    (``next_start == current_end``) both merge with ``gap_ms == 0``, while a
    positive ``gap_ms`` additionally bridges small holes.  An empty input
    returns ``[]``.

    ``gap_ms`` must be non-negative and every range must satisfy
    ``start <= end``; otherwise :class:`SeekError` is raised.  Returned bounds
    are exact integer milliseconds and compare with a 1 ms tolerance.
    """

    raise NotImplementedError


def estimate_decode_cost(plan, avg_frame_ms):
    """Estimate how many frames must be decoded to honour ``plan``.

    Only the distance from the keyframe to the decode target matters::

        ceil((plan["decode_to"] - plan["keyframe"]) / avg_frame_ms)

    A plan that stops on its keyframe costs zero frames.  This deliberately
    tracks keyframe density instead of the raw interval length, so two seeks
    ending at the same timestamp cost different amounts when their preceding
    keyframes differ.  ``avg_frame_ms`` must be positive, otherwise
    :class:`SeekError` is raised.  The frame count is an integer; the 1 ms
    tolerance applies to the millisecond inputs.
    """

    raise NotImplementedError


def seek_batch(index, targets):
    """Plan a batch of seeks in ascending target order.

    Every target is validated against ``0 <= target <= index["duration"]``
    first.  If any target is invalid (negative, beyond the duration, or not
    an integer) the whole batch raises :class:`SeekError` and no partial
    result is produced.  Valid targets are then executed in ascending order,
    and consecutive targets that share a keyframe reuse it, so a backwards
    input order never causes repeated decoding.

    ``targets`` is a sequence of integer milliseconds.  Empty ``targets``
    (even with an empty keyframe list) returns::

        {"order": [], "results": [], "decodes": 0}

    Otherwise the result is::

        {
            "order": [target_ms, ...],   # ascending execution order
            "results": [plan, ...],      # seek_plan(..., "precise") each
            "decodes": int,              # keyframe loads, one per group
        }

    ``decodes`` is the number of distinct keyframe groups touched, which for
    an ascending batch equals the number of covered keyframe intervals.  All
    times are integer milliseconds and compare with a 1 ms tolerance.
    """

    raise NotImplementedError

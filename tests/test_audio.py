"""RingBuffer unit tests: write/read-last-n correctness and wraparound. Phase 1."""

from __future__ import annotations

import numpy as np

from munshiji.audio.capture import RingBuffer


def test_read_last_before_any_write_is_empty() -> None:
    buf = RingBuffer(capacity_samples=10)
    assert buf.read_last(5).size == 0


def test_read_last_returns_written_samples_in_order() -> None:
    buf = RingBuffer(capacity_samples=10)
    buf.write(np.array([1, 2, 3], dtype=np.int16))
    result = buf.read_last(3)
    assert list(result) == [1, 2, 3]


def test_read_last_clamps_to_available_samples() -> None:
    buf = RingBuffer(capacity_samples=10)
    buf.write(np.array([1, 2, 3], dtype=np.int16))
    result = buf.read_last(100)
    assert list(result) == [1, 2, 3]


def test_write_wraps_around_capacity() -> None:
    buf = RingBuffer(capacity_samples=5)
    buf.write(np.array([1, 2, 3, 4, 5], dtype=np.int16))
    buf.write(np.array([6, 7], dtype=np.int16))
    # oldest two samples (1, 2) were overwritten by 6, 7
    assert list(buf.read_last(5)) == [3, 4, 5, 6, 7]


def test_write_larger_than_capacity_keeps_most_recent_tail() -> None:
    buf = RingBuffer(capacity_samples=3)
    buf.write(np.arange(10, dtype=np.int16))
    assert list(buf.read_last(3)) == [7, 8, 9]


def test_read_last_after_multiple_partial_writes() -> None:
    buf = RingBuffer(capacity_samples=4)
    buf.write(np.array([1], dtype=np.int16))
    buf.write(np.array([2, 3], dtype=np.int16))
    buf.write(np.array([4, 5], dtype=np.int16))
    # capacity 4, total written 1,2,3,4,5 -> oldest (1,2) fell off
    assert list(buf.read_last(4)) == [2, 3, 4, 5]

"""
The measured outcome of a recorded task demo.
"""

from __future__ import annotations

from cramera_protocol.bundle.acceptance import AcceptanceMetrics

# %% metrics


def test_metrics_keep_the_demo_s_own_names(read_json):
    data = read_json("acceptance_metrics.json")
    metrics = AcceptanceMetrics.from_json(data)
    assert metrics.measurements == data
    assert metrics.to_json() == data

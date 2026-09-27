"""Regression test: every requests failure during a WQP call must degrade to WQPUnavailable.

The module is expected to stop gracefully on *any* transport failure so that run() can
still write results/wqp_status.json and results/wqp_makeup.csv with fallback values.
Only ProxyError / ConnectionError / Timeout were handled at one point, so a redirect loop
or a garbled body (TooManyRedirects, ChunkedEncodingError, ContentDecodingError) escaped
fetch_csv and crashed the whole run.

Pure unit test: the cache path never exists and the download path is never reached, so
nothing is written to disk and no network call is made.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests

from peakflow.wqp import WQPUnavailable, fetch_csv


def _raising_getter(exc):
    def getter(url, params):
        raise exc
    return getter


def _missing_path(tmp_path: Path, name: str) -> Path:
    # Inside pytest's tmp dir but never created: fetch_csv must not reach any write.
    return tmp_path / "no_cache" / name


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.TooManyRedirects("Exceeded 30 redirects."),
        requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead"),
        requests.exceptions.ContentDecodingError("Received response with content-encoding: gzip"),
    ],
    ids=["TooManyRedirects", "ChunkedEncodingError", "ContentDecodingError"],
)
def test_uncommon_transport_failures_become_wqp_unavailable(tmp_path, exc):
    """A non-connection requests failure must surface as WQPUnavailable, not crash the run."""
    path = _missing_path(tmp_path, "station_TEST0000001.csv")

    with pytest.raises(WQPUnavailable) as info:
        fetch_csv(
            "https://www.waterqualitydata.us/data/Station/search",
            {"lat": "40.00000", "long": "-75.00000", "within": "10", "mimeType": "csv"},
            path,
            offline=False,
            getter=_raising_getter(exc),
        )

    # The failure reason has to reach the status file, so keep the exception type in the message.
    assert type(exc).__name__ in str(info.value)
    # Nothing may have been downloaded or cached on the failure path.
    assert not path.exists()


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ProxyError("proxy refused"),
        requests.exceptions.ConnectionError("name resolution failed"),
        requests.exceptions.ConnectTimeout("timed out"),
        requests.exceptions.ReadTimeout("read timed out"),
    ],
    ids=["ProxyError", "ConnectionError", "ConnectTimeout", "ReadTimeout"],
)
def test_network_block_failures_still_become_wqp_unavailable(tmp_path, exc):
    """Must still hold: the originally handled network failures keep degrading gracefully."""
    path = _missing_path(tmp_path, "result_TEST0000001.csv")

    with pytest.raises(WQPUnavailable) as info:
        fetch_csv(
            "https://www.waterqualitydata.us/data/Result/search",
            {"siteid": "USGS-01463500", "mimeType": "csv"},
            path,
            offline=False,
            getter=_raising_getter(exc),
        )

    assert type(exc).__name__ in str(info.value)
    assert not path.exists()
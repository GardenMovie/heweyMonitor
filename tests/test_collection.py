import json
import subprocess
from datetime import datetime, timezone

import pytest

import collection


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "ID_LOG_PATH", str(tmp_path / "insert_ids.json"))
    monkeypatch.setattr(collection, "SPOOL_PATH", str(tmp_path / "spool.json"))


def test_metrics_json_round_trip():
    metrics = {
        "timestamp": datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc),
        "metadata": {"hostname": "test-host"},
        "fields": {"cpu_percent": 1.0, "ram_percent": 2.0, "disk_percent": 3.0, "ping_ms": 4.0},
    }
    doc = collection.metrics_to_json(metrics)
    assert doc["timestamp"] == "2026-07-31T12:00:00+00:00"

    restored = collection.metrics_from_json(doc)
    assert restored == metrics


def test_load_id_log_missing_file_returns_empty_deque():
    log = collection.load_id_log()
    assert list(log) == []


def test_save_and_load_id_log_round_trip():
    collection.save_id_log(["a", "b", "c"])
    log = collection.load_id_log()
    assert list(log) == ["a", "b", "c"]


def test_id_log_respects_maxlen(monkeypatch):
    monkeypatch.setattr(collection, "ID_LOG_MAXLEN", 2)
    log = collection.load_id_log()
    log.append("a")
    log.append("b")
    log.append("c")
    assert list(log) == ["b", "c"]


def test_load_spool_missing_file_returns_empty_deque():
    spool = collection.load_spool()
    assert list(spool) == []


def test_save_and_load_spool_round_trip():
    metrics = {
        "timestamp": datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc),
        "metadata": {"hostname": "test-host"},
        "fields": {"cpu_percent": 1.0, "ram_percent": 2.0, "disk_percent": 3.0, "ping_ms": None},
    }
    collection.save_spool([metrics])
    spool = collection.load_spool()
    assert list(spool) == [metrics]


def test_save_spool_empty_removes_file():
    collection.save_spool([{
        "timestamp": datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc),
        "metadata": {"hostname": "h"},
        "fields": {},
    }])
    assert collection.load_spool()

    collection.save_spool([])
    assert list(collection.load_spool()) == []


def test_ping_latency_parses_time_from_output(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms\n",
        )
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert collection.ping_latency() == 12.3


def test_ping_latency_nonzero_exit_returns_none(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert collection.ping_latency() is None


def test_ping_latency_malformed_output_returns_none(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="time=notanumber ms\n"
        )
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert collection.ping_latency() is None


def test_ping_latency_subprocess_raises_returns_none(monkeypatch):
    def fake_run(*args, **kwargs):
        raise OSError("ping not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert collection.ping_latency() is None


def test_collect_metrics_shape(monkeypatch):
    monkeypatch.setattr(collection.psutil, "cpu_percent", lambda interval=1: 10.0)
    monkeypatch.setattr(
        collection.psutil, "virtual_memory", lambda: type("M", (), {"percent": 20.0})()
    )
    monkeypatch.setattr(
        collection.psutil, "disk_usage", lambda path: type("D", (), {"percent": 30.0})()
    )
    monkeypatch.setattr(collection, "ping_latency", lambda: 5.5)

    metrics = collection.collect_metrics("my-host")

    assert metrics["metadata"] == {"hostname": "my-host"}
    assert metrics["fields"] == {
        "cpu_percent": 10.0,
        "ram_percent": 20.0,
        "disk_percent": 30.0,
        "ping_ms": 5.5,
    }
    assert isinstance(metrics["timestamp"], datetime)

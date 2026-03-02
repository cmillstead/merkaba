# tests/e2e/test_e2e_diagnostics.py
"""Tests for the DiagnosticsStore ring buffer."""

import threading

import pytest

from merkaba.web.diagnostics import DiagnosticsStore, TraceDepth


pytestmark = pytest.mark.e2e


class TestDiagnosticsStore:
    def test_initial_state_empty(self):
        store = DiagnosticsStore(buffer_size=100)
        assert store.get_recent(10) == []
        assert store.get_errors(10) == []
        assert store.get_connections() == []
        summary = store.get_summary()
        assert summary["total_requests"] == 0
        assert summary["total_errors"] == 0

    def test_record_http_request(self):
        store = DiagnosticsStore(buffer_size=100)
        store.record_request({
            "timestamp": "2026-03-01T12:00:00Z",
            "method": "GET",
            "path": "/api/system/status",
            "status": 200,
            "duration_ms": 12.4,
        })
        recent = store.get_recent(10)
        assert len(recent) == 1
        assert recent[0]["method"] == "GET"
        assert recent[0]["path"] == "/api/system/status"

    def test_record_error_request(self):
        store = DiagnosticsStore(buffer_size=100)
        store.record_request({
            "timestamp": "2026-03-01T12:00:00Z",
            "method": "GET",
            "path": "/bad",
            "status": 500,
            "duration_ms": 5.0,
            "error": "Internal Server Error",
        })
        errors = store.get_errors(10)
        assert len(errors) == 1
        assert errors[0]["error"] == "Internal Server Error"

    def test_ring_buffer_eviction(self):
        store = DiagnosticsStore(buffer_size=3)
        for i in range(5):
            store.record_request({
                "timestamp": f"2026-03-01T12:00:0{i}Z",
                "method": "GET",
                "path": f"/req/{i}",
                "status": 200,
                "duration_ms": 1.0,
            })
        recent = store.get_recent(10)
        assert len(recent) == 3
        # Newest first
        assert recent[0]["path"] == "/req/4"
        assert recent[2]["path"] == "/req/2"

    def test_websocket_connection_tracking(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_connect("conn-2", "/ws/chat")
        conns = store.get_connections()
        assert len(conns) == 2
        paths = {c["path"] for c in conns}
        assert paths == {"/ws/control", "/ws/chat"}

    def test_websocket_disconnect_removes(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_disconnect("conn-1")
        assert store.get_connections() == []

    def test_websocket_frame_counting(self):
        store = DiagnosticsStore(buffer_size=100)
        store.ws_connect("conn-1", "/ws/control")
        store.ws_frame_sent("conn-1")
        store.ws_frame_sent("conn-1")
        store.ws_frame_received("conn-1")
        conns = store.get_connections()
        assert conns[0]["frames_sent"] == 2
        assert conns[0]["frames_received"] == 1

    def test_summary_stats(self):
        store = DiagnosticsStore(buffer_size=100)
        for i in range(10):
            store.record_request({
                "timestamp": f"2026-03-01T12:00:0{i}Z",
                "method": "GET",
                "path": f"/req/{i}",
                "status": 500 if i == 0 else 200,
                "duration_ms": float(i + 1),
            })
        summary = store.get_summary()
        assert summary["total_requests"] == 10
        assert summary["total_errors"] == 1
        assert summary["avg_duration_ms"] == 5.5

    def test_trace_depth_change(self):
        store = DiagnosticsStore(buffer_size=100)
        assert store.trace_depth == TraceDepth.FULL
        store.set_trace_depth(TraceDepth.LIGHTWEIGHT)
        assert store.trace_depth == TraceDepth.LIGHTWEIGHT

    def test_thread_safety(self):
        store = DiagnosticsStore(buffer_size=100)
        errors = []

        def writer(start):
            try:
                for i in range(50):
                    store.record_request({
                        "timestamp": "2026-03-01T12:00:00Z",
                        "method": "GET",
                        "path": f"/thread/{start}/{i}",
                        "status": 200,
                        "duration_ms": 1.0,
                    })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        summary = store.get_summary()
        assert summary["total_requests"] == 200

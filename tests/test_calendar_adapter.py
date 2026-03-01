import sys
from unittest.mock import patch, MagicMock
import pytest
from merkaba.integrations.calendar_adapter import CalendarAdapter


class TestCalendarAdapter:
    def test_connect_fails_on_non_darwin(self):
        adapter = CalendarAdapter(name="calendar")
        with patch.object(sys, "platform", "linux"):
            # Re-check platform inside connect
            assert adapter.connect() is False
            assert not adapter.is_connected

    def test_connect_fails_without_eventkit(self):
        adapter = CalendarAdapter(name="calendar")
        with patch.object(sys, "platform", "darwin"), \
             patch.dict(sys.modules, {"EventKit": None}):
            # Import will raise
            result = adapter.connect()
            assert result is False

    def test_connect_succeeds(self):
        adapter = CalendarAdapter(name="calendar")
        mock_ek = MagicMock()
        mock_store = MagicMock()
        mock_ek.EKEventStore.alloc.return_value.init.return_value = mock_store
        with patch.object(sys, "platform", "darwin"), \
             patch.dict(sys.modules, {"EventKit": mock_ek}):
            result = adapter.connect()
            assert result is True
            assert adapter.is_connected

    def test_list_calendars(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        mock_store = MagicMock()
        mock_cal = MagicMock()
        mock_cal.title.return_value = "Personal"
        mock_cal.calendarIdentifier.return_value = "cal-1"
        mock_cal.type.return_value = 0
        mock_cal.color.return_value = "blue"
        mock_store.calendarsForEntityType_.return_value = [mock_cal]
        adapter._store = mock_store

        mock_ek = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek}):
            result = adapter.execute("list_calendars")
        assert result["ok"]
        assert len(result["calendars"]) == 1
        assert result["calendars"][0]["title"] == "Personal"

    def test_list_events(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        mock_store = MagicMock()
        mock_event = MagicMock()
        mock_event.title.return_value = "Meeting"
        mock_event.eventIdentifier.return_value = "evt-1"
        mock_event.startDate.return_value = "2026-03-01 10:00"
        mock_event.endDate.return_value = "2026-03-01 11:00"
        mock_event.location.return_value = "Office"
        mock_event.notes.return_value = ""
        mock_store.eventsMatchingPredicate_.return_value = [mock_event]
        adapter._store = mock_store

        mock_ek = MagicMock()
        mock_foundation = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek, "Foundation": mock_foundation}):
            result = adapter.execute("list_events", {"days": 7})
        assert result["ok"]
        assert len(result["events"]) == 1

    def test_create_event_missing_params(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        adapter._store = MagicMock()
        mock_ek = MagicMock()
        mock_foundation = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek, "Foundation": mock_foundation}):
            result = adapter.execute("create_event", {"title": "Test"})
        assert not result["ok"]
        assert "Missing" in result["error"]

    def test_create_event_success(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        mock_store = MagicMock()
        mock_store.saveEvent_span_error_.return_value = (True, None)
        mock_event = MagicMock()
        mock_event.eventIdentifier.return_value = "new-evt-1"
        adapter._store = mock_store

        mock_ek = MagicMock()
        mock_ek.EKEvent.eventWithEventStore_.return_value = mock_event
        mock_foundation = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek, "Foundation": mock_foundation}):
            result = adapter.execute("create_event", {
                "title": "Test", "start_timestamp": 1709290800, "end_timestamp": 1709294400
            })
        assert result["ok"]

    def test_delete_event_missing_id(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        adapter._store = MagicMock()
        mock_ek = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek}):
            result = adapter.execute("delete_event", {})
        assert not result["ok"]

    def test_delete_event_not_found(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        mock_store = MagicMock()
        mock_store.eventWithIdentifier_.return_value = None
        adapter._store = mock_store
        mock_ek = MagicMock()
        with patch.dict(sys.modules, {"EventKit": mock_ek}):
            result = adapter.execute("delete_event", {"event_id": "nonexistent"})
        assert not result["ok"]

    def test_unknown_action(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        result = adapter.execute("invalid_action")
        assert not result["ok"]

    def test_health_check_not_connected(self):
        adapter = CalendarAdapter(name="calendar")
        result = adapter.health_check()
        assert not result["ok"]

    def test_health_check_connected(self):
        adapter = CalendarAdapter(name="calendar")
        adapter._connected = True
        adapter._store = MagicMock()
        mock_ek = MagicMock()
        mock_ek.EKEventStore.authorizationStatusForEntityType_.return_value = 3  # FullAccess
        mock_ek.EKAuthorizationStatusFullAccess = 3
        mock_ek.EKEntityTypeEvent = 0
        with patch.dict(sys.modules, {"EventKit": mock_ek}):
            result = adapter.health_check()
        assert result["ok"]

"""Apple Calendar integration adapter (macOS only)."""

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from merkaba.integrations.base import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)


@dataclass
class CalendarAdapter(IntegrationAdapter):
    _store: object = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        if sys.platform != "darwin":
            logger.warning("Calendar adapter only available on macOS")
            self._connected = False
            return False
        try:
            import EventKit
            self._store = EventKit.EKEventStore.alloc().init()
            # Request access - on macOS this triggers a permission prompt
            # For programmatic use, we request full access
            self._store.requestFullAccessToEventsWithCompletion_(lambda granted, error: None)
            self._connected = True
            return True
        except ImportError:
            logger.warning("pyobjc-framework-EventKit not installed")
            self._connected = False
            return False
        except Exception as e:
            logger.error("Calendar connect failed: %s", e)
            self._connected = False
            return False

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        actions = {
            "list_calendars": self._list_calendars,
            "list_events": self._list_events,
            "create_event": self._create_event,
            "delete_event": self._delete_event,
        }
        handler = actions.get(action)
        if not handler:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return handler(params)

    def health_check(self) -> dict:
        if not self._connected or not self._store:
            return {"ok": False, "adapter": "calendar", "error": "Not connected"}
        try:
            import EventKit
            status = EventKit.EKEventStore.authorizationStatusForEntityType_(
                EventKit.EKEntityTypeEvent
            )
            authorized = status == EventKit.EKAuthorizationStatusFullAccess
            return {"ok": authorized, "adapter": "calendar", "authorized": authorized}
        except Exception as e:
            return {"ok": False, "adapter": "calendar", "error": str(e)}

    def _list_calendars(self, params: dict) -> dict:
        try:
            import EventKit
            calendars = self._store.calendarsForEntityType_(EventKit.EKEntityTypeEvent)
            result = []
            for cal in calendars:
                result.append({
                    "title": cal.title(),
                    "calendar_id": cal.calendarIdentifier(),
                    "type": str(cal.type()),
                    "color": str(cal.color()),
                })
            return {"ok": True, "calendars": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _list_events(self, params: dict) -> dict:
        try:
            import EventKit
            from Foundation import NSDate

            days = params.get("days", 7)
            start = NSDate.date()
            end = NSDate.dateWithTimeIntervalSinceNow_(days * 86400)

            predicate = self._store.predicateForEventsWithStartDate_endDate_calendars_(
                start, end, None
            )
            events = self._store.eventsMatchingPredicate_(predicate)
            result = []
            for event in (events or []):
                result.append({
                    "title": event.title(),
                    "event_id": event.eventIdentifier(),
                    "start": str(event.startDate()),
                    "end": str(event.endDate()),
                    "location": event.location() or "",
                    "notes": event.notes() or "",
                })
            return {"ok": True, "events": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _create_event(self, params: dict) -> dict:
        try:
            import EventKit
            from Foundation import NSDate

            required = {"title", "start_timestamp", "end_timestamp"}
            if not required.issubset(params.keys()):
                missing = required - params.keys()
                return {"ok": False, "error": f"Missing required params: {missing}"}

            event = EventKit.EKEvent.eventWithEventStore_(self._store)
            event.setTitle_(params["title"])
            event.setStartDate_(NSDate.dateWithTimeIntervalSince1970_(params["start_timestamp"]))
            event.setEndDate_(NSDate.dateWithTimeIntervalSince1970_(params["end_timestamp"]))

            if params.get("location"):
                event.setLocation_(params["location"])
            if params.get("notes"):
                event.setNotes_(params["notes"])

            # Use default calendar
            event.setCalendar_(self._store.defaultCalendarForNewEvents())

            success, error = self._store.saveEvent_span_error_(
                event, EventKit.EKSpanThisEvent, None
            )
            if success:
                return {"ok": True, "event_id": event.eventIdentifier()}
            else:
                return {"ok": False, "error": str(error) if error else "Save failed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _delete_event(self, params: dict) -> dict:
        try:
            import EventKit

            event_id = params.get("event_id")
            if not event_id:
                return {"ok": False, "error": "Missing required param: event_id"}

            event = self._store.eventWithIdentifier_(event_id)
            if not event:
                return {"ok": False, "error": f"Event not found: {event_id}"}

            success, error = self._store.removeEvent_span_error_(
                event, EventKit.EKSpanThisEvent, None
            )
            if success:
                return {"ok": True}
            else:
                return {"ok": False, "error": str(error) if error else "Delete failed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


if sys.platform == "darwin":
    register_adapter("calendar", CalendarAdapter)

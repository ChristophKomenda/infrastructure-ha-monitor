"""Debounced incident detection and recovery tracking."""

import time
from datetime import datetime, timezone


class IncidentTracker:

    def __init__(self, confirmations=2):
        self.confirmations = confirmations
        self.status = "unknown"
        self.incident = "initializing"

        self.pending = None
        self.pending_count = 0

        self.started = None
        self.started_at = None
        self.total_incidents = 0
        self.total_duration = 0.0
        self.last_duration = 0.0

    def update(self, status, incident, now=None):
        now = time.time() if now is None else now
        candidate = (status, incident)

        if candidate == (self.status, self.incident):
            self.pending = None
            self.pending_count = 0

        else:
            if candidate == self.pending:
                self.pending_count += 1
            else:
                self.pending = candidate
                self.pending_count = 1

            if self.pending_count >= self.confirmations:
                self.status, self.incident = candidate
                self.pending = None
                self.pending_count = 0

                if status in ("critical", "degraded"):
                    if self.started is None:
                        self.started = now
                        self.started_at = datetime.fromtimestamp(
                            now, timezone.utc
                        ).isoformat()
                        self.total_incidents += 1

                elif status == "healthy":
                    if self.started is not None:
                        self.last_duration = max(
                            0, now - self.started
                        )
                        self.total_duration += self.last_duration
                        self.started = None
                        self.started_at = None

        active_duration = (
            max(0, now - self.started)
            if self.started is not None else 0
        )

        completed = self.total_incidents - int(
            self.started is not None
        )

        return {
            "status": self.status,
            "incident": self.incident,
            "raw_status": status,
            "raw_incident": incident,
            "incident_count": self.total_incidents,
            "incident_started_at": self.started_at,
            "incident_duration": round(active_duration, 1),
            "last_incident_duration": round(
                self.last_duration, 1
            ),
            "mttr": round(
                self.total_duration / completed, 1
            ) if completed else None,
        }

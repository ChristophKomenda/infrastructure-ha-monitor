"""Persistent infrastructure observability."""

import sqlite3
import time
from pathlib import Path


class History:

    def __init__(self, path, max_gap=20):
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True, exist_ok=True
        )

        self.max_gap = max_gap

        self.db = sqlite3.connect(
            self.path, timeout=10
        )

        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")

        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS samples (
                timestamp REAL PRIMARY KEY,
                status TEXT NOT NULL,
                diagnosis TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY,
                started REAL NOT NULL,
                ended REAL,
                diagnosis TEXT NOT NULL,
                outcome TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_incidents_started
                ON incidents(started);
        """)

        self.db.commit()

    def record(self, status, diagnosis, now=None):
        now = time.time() if now is None else now

        if status not in (
            "healthy", "degraded",
            "critical", "unknown", "pending"
        ):
            status = "unknown"

        with self.db:
            previous = self.db.execute("""
                SELECT timestamp FROM samples
                ORDER BY timestamp DESC LIMIT 1
            """).fetchone()

            active = self.db.execute("""
                SELECT id, started
                FROM incidents
                WHERE ended IS NULL
                ORDER BY id DESC LIMIT 1
            """).fetchone()

            # An unobserved interval cannot be
            # treated as confirmed incident duration.
            if (
                previous
                and now - previous[0] > self.max_gap
                and active
            ):
                self.db.execute("""
                    UPDATE incidents
                    SET ended=?, outcome='interrupted'
                    WHERE id=?
                """, (previous[0], active[0]))

                active = None

            self.db.execute("""
                INSERT OR REPLACE INTO samples
                VALUES (?, ?, ?)
            """, (now, status, diagnosis))

            if status in ("critical", "degraded"):
                if active is None:
                    self.db.execute("""
                        INSERT INTO incidents
                        (started, diagnosis)
                        VALUES (?, ?)
                    """, (now, diagnosis))

            elif status == "healthy" and active:
                unknown = self.db.execute("""
                    SELECT 1 FROM samples
                    WHERE timestamp >= ?
                    AND timestamp < ?
                    AND status='unknown'
                    LIMIT 1
                """, (active[1], now)).fetchone()

                outcome = "interrupted" if unknown else "recovered"

                self.db.execute("""
                    UPDATE incidents
                    SET ended=?, outcome=?
                    WHERE id=?
                """, (now, outcome, active[0]))

            elif status in ("unknown", "pending") and active:
                last_known = self.db.execute("""
                    SELECT MAX(timestamp) FROM samples
                    WHERE timestamp >= ?
                    AND status IN (
                        'healthy', 'critical', 'degraded'
                    )
                """, (active[1],)).fetchone()[0]

                if (
                    last_known is not None
                    and now - last_known > self.max_gap
                ):
                    self.db.execute("""
                        UPDATE incidents
                        SET ended=?, outcome='interrupted'
                        WHERE id=?
                    """, (last_known, active[0]))

    def availability(self, hours, now=None):
        now = time.time() if now is None else now
        start = now - hours * 3600

        rows = self.db.execute("""
            SELECT timestamp, status
            FROM samples
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """, (start - self.max_gap, now)).fetchall()

        observed = 0.0
        available = 0.0
        healthy = 0.0

        for index, (timestamp, status) in enumerate(rows):
            next_timestamp = (
                rows[index + 1][0]
                if index + 1 < len(rows)
                else now
            )

            duration = max(
                0,
                min(
                    next_timestamp,
                    timestamp + self.max_gap,
                    now,
                ) - max(timestamp, start)
            )

            if status in ("unknown", "pending"):
                continue

            observed += duration

            if status in ("healthy", "degraded"):
                available += duration

            if status == "healthy":
                healthy += duration

        return {
            "uptime": round(
                available / observed * 100, 4
            ) if observed else None,

            "healthy": round(
                healthy / observed * 100, 4
            ) if observed else None,

            "coverage": round(
                observed / (hours * 3600) * 100, 4
            ),
        }

    def statistics(self, now=None):
        now = time.time() if now is None else now

        count = self.db.execute("""
            SELECT COUNT(*) FROM incidents
        """).fetchone()[0]

        completed = self.db.execute("""
            SELECT started, ended
            FROM incidents
            WHERE ended IS NOT NULL
            AND outcome='recovered'
            ORDER BY started
        """).fetchall()

        durations = [
            ended - started
            for started, ended in completed
        ]

        active = self.db.execute("""
            SELECT started
            FROM incidents
            WHERE ended IS NULL
            ORDER BY id DESC LIMIT 1
        """).fetchone()

        return {
            "mtbf": self.calculate_mtbf(now),
            "incident_count": count,
            "completed_incidents": len(completed),
            "mttr": round(
                sum(durations) / len(durations), 2
            ) if durations else None,
            "last_incident_duration": (
                round(durations[-1], 2)
                if durations else None
            ),
            "active_incident_duration": (
                round(max(0, now - active[0]), 2)
                if active else 0
            ),
        }

    def live_statistics(self, now=None):
        now = time.time() if now is None else now

        count = self.db.execute(
            "SELECT COUNT(*) FROM incidents"
        ).fetchone()[0]

        active = self.db.execute("""
            SELECT started FROM incidents
            WHERE ended IS NULL
            ORDER BY id DESC LIMIT 1
        """).fetchone()

        return {
            "incident_count": count,
            "active_incident_duration": (
                round(max(0, now - active[0]), 2)
                if active else 0
            ),
        }

    def calculate_mtbf(self, now=None):
        now = time.time() if now is None else now

        incidents = self.db.execute("""
            SELECT started, ended, outcome
            FROM incidents
            WHERE started >= ?
            ORDER BY started
        """, (now - 30 * 86400,)).fetchall()

        intervals = []

        for previous, following in zip(
            incidents, incidents[1:]
        ):
            _, ended, outcome = previous
            next_started = following[0]

            if (
                outcome != "recovered"
                or ended is None
                or next_started <= ended
            ):
                continue

            rows = self.db.execute("""
                SELECT timestamp, status
                FROM samples
                WHERE timestamp >= ?
                AND timestamp < ?
                ORDER BY timestamp
            """, (ended, next_started)).fetchall()

            if not rows or rows[0][0] != ended:
                continue

            if any(
                status not in ("healthy", "pending")
                for _, status in rows
            ):
                continue

            timestamps = [
                timestamp for timestamp, _ in rows
            ] + [next_started]

            if any(
                b - a > self.max_gap
                for a, b in zip(timestamps, timestamps[1:])
            ):
                continue

            intervals.append(next_started - ended)

        return (
            round(sum(intervals) / len(intervals), 2)
            if intervals else None
        )

    def cleanup(self, retention_days=35, now=None):
        now = time.time() if now is None else now

        with self.db:
            self.db.execute("""
                DELETE FROM samples
                WHERE timestamp < ?
            """, (now - retention_days * 86400,))

    def close(self):
        self.db.close()

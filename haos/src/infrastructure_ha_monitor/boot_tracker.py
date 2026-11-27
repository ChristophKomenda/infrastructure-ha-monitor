"""Persistent detection of observed host reboots."""

import math
import uuid


class BootTracker:

    def __init__(self, db):
        self.db = db

        with self.db:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS host_boots (
                    node TEXT PRIMARY KEY,
                    boot_id TEXT NOT NULL,
                    last_seen REAL NOT NULL,
                    reboot_count INTEGER NOT NULL DEFAULT 0
                )
            """)

    def observe(self, node, boot_id, timestamp):
        try:
            boot_id = str(uuid.UUID(boot_id))
            timestamp = float(timestamp)
        except (ValueError, TypeError, AttributeError):
            return

        if not math.isfinite(timestamp):
            return

        with self.db:
            row = self.db.execute("""
                SELECT boot_id, last_seen, reboot_count
                FROM host_boots WHERE node=?
            """, (node,)).fetchone()

            if row is None:
                self.db.execute("""
                    INSERT INTO host_boots
                    VALUES (?, ?, ?, 0)
                """, (node, boot_id, timestamp))
                return

            previous_id, last_seen, count = row

            if timestamp <= last_seen:
                return

            if boot_id != previous_id:
                count += 1

            self.db.execute("""
                UPDATE host_boots
                SET boot_id=?, last_seen=?, reboot_count=?
                WHERE node=?
            """, (
                boot_id, timestamp, count, node
            ))

    def count(self, node):
        row = self.db.execute("""
            SELECT reboot_count
            FROM host_boots WHERE node=?
        """, (node,)).fetchone()

        return row[0] if row else None

    def observe_snapshot(self, node, snapshot, now):
        if not isinstance(snapshot, dict):
            return

        if (
            snapshot.get("schema_version") != 1
            or snapshot.get("node_id") != node
        ):
            return

        try:
            timestamp = float(snapshot["timestamp"])
            age = now - timestamp

            if not math.isfinite(age):
                return

            if not -5 <= age <= 35:
                return

            boot_id = snapshot["data"][
                "host_diagnostics"
            ]["boot_id"]

        except (KeyError, TypeError, ValueError):
            return

        self.observe(node, boot_id, timestamp)

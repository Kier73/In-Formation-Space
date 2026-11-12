"""Durable, single-host SQLite authority for proof-action route epochs.

This store implements RouteEpochLedgerStore with SQLite transactions and
BEGIN IMMEDIATE compare-and-swap. It is suitable for process restarts and
multiple local processes sharing one database on a local filesystem. It is not
a multi-host consensus service and should not be placed on an arbitrary
network filesystem.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from proof_action_route_epoch import (
    ProofActionRouteEpochError,
    ProofActionRouteEpochLedger,
    RouteEpochLedgerStore,
)


class SQLiteRouteEpochStoreError(RuntimeError):
    """SQLite route-epoch store configuration, durability or integrity failure."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SQLiteRouteEpochStoreError(
            "SQLite route-ledger documents must be finite canonical JSON"
        ) from exc


def _copy(value: Any) -> Any:
    return json.loads(_canonical(value))


def _sha256(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SQLiteRouteEpochStoreError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        raise SQLiteRouteEpochStoreError("route-ledger document must be an object")
    copied = _copy(dict(document))
    try:
        ProofActionRouteEpochLedger.from_dict(copied)
    except (ProofActionRouteEpochError, TypeError, ValueError) as exc:
        raise SQLiteRouteEpochStoreError(f"route-ledger document failed validation: {exc}") from exc
    return copied


class SQLiteRouteEpochLedgerStore(RouteEpochLedgerStore):
    """SQLite-backed CAS store with an append-only revision audit table.

    Each successful CAS stores the latest complete route-ledger document and
    one audit row describing the new ledger revision and event digests appended
    by that revision. Writers are serialized by SQLite's BEGIN IMMEDIATE lock.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds):
            raise SQLiteRouteEpochStoreError("timeout_seconds must be a finite positive number")
        if timeout_seconds <= 0:
            raise SQLiteRouteEpochStoreError("timeout_seconds must be positive")
        raw_path = str(path)
        if not raw_path or raw_path == ":memory:":
            raise SQLiteRouteEpochStoreError(
                "a filesystem database path is required for durable route authority"
            )
        self.path = str(Path(raw_path).expanduser().resolve())
        self.timeout_seconds = float(timeout_seconds)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(
            f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}"
        )
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS route_epoch_current (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    ledger_digest TEXT NOT NULL,
                    document_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS route_epoch_revisions (
                    revision INTEGER PRIMARY KEY CHECK (revision > 0),
                    previous_ledger_digest TEXT,
                    ledger_digest TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    appended_event_digests_json TEXT NOT NULL,
                    committed_utc TEXT NOT NULL DEFAULT (
                        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    )
                );
                """
            )
        except sqlite3.Error as exc:
            raise SQLiteRouteEpochStoreError(f"could not initialize SQLite route store: {exc}") from exc
        finally:
            connection.close()

    @staticmethod
    def _parse_document(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SQLiteRouteEpochStoreError("stored route-ledger JSON is malformed") from exc
        return _validate_document(parsed)

    @staticmethod
    def _validate_audit_rows(
        rows: list[sqlite3.Row],
        current_document: Mapping[str, Any] | None,
        current_revision: int | None,
    ) -> None:
        previous_digest: str | None = None
        appended_event_digests: list[str] = []
        expected_revision = 1
        for row in rows:
            revision = row["revision"]
            if type(revision) is not int or revision != expected_revision:
                raise SQLiteRouteEpochStoreError("SQLite route revision sequence is not contiguous")
            previous = row["previous_ledger_digest"]
            if previous != previous_digest:
                raise SQLiteRouteEpochStoreError("SQLite route revision predecessor digest mismatch")
            ledger_digest = _sha256(row["ledger_digest"], "audit.ledger_digest")
            if type(row["actor_id"]) is not str or not row["actor_id"].strip():
                raise SQLiteRouteEpochStoreError("SQLite route revision actor ID is invalid")
            try:
                delta = json.loads(row["appended_event_digests_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise SQLiteRouteEpochStoreError("SQLite route revision event index is malformed") from exc
            if not isinstance(delta, list) or not delta:
                raise SQLiteRouteEpochStoreError("SQLite route revision must append at least one event")
            for digest in delta:
                appended_event_digests.append(_sha256(digest, "audit.appended_event_digest"))
            previous_digest = ledger_digest
            expected_revision += 1

        if current_document is None:
            if rows or current_revision is not None:
                raise SQLiteRouteEpochStoreError("SQLite revision history exists without current state")
            return
        if not rows or current_revision != len(rows):
            raise SQLiteRouteEpochStoreError("SQLite current revision disagrees with its audit history")
        if previous_digest != current_document.get("ledger_digest"):
            raise SQLiteRouteEpochStoreError("SQLite current ledger digest disagrees with its audit history")
        document_event_digests = [
            event.get("event_digest") for event in current_document.get("entries", [])
        ]
        if appended_event_digests != document_event_digests:
            raise SQLiteRouteEpochStoreError(
                "SQLite audit event index does not reproduce the current append-only ledger"
            )

    def _read_current(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[dict[str, Any] | None, int | None]:
        row = connection.execute(
            """
            SELECT revision, ledger_digest, document_json
            FROM route_epoch_current
            WHERE singleton = 1
            """
        ).fetchone()
        if row is None:
            return None, None
        document = self._parse_document(row["document_json"])
        if document["ledger_digest"] != row["ledger_digest"]:
            raise SQLiteRouteEpochStoreError(
                "SQLite current-state digest does not match its stored document"
            )
        return document, row["revision"]

    def load(self) -> dict[str, Any] | None:
        """Load and verify the current ledger plus its append-only revision audit."""
        connection = self._connect()
        try:
            document, revision = self._read_current(connection)
            rows = connection.execute(
                """
                SELECT revision, previous_ledger_digest, ledger_digest,
                       actor_id, appended_event_digests_json, committed_utc
                FROM route_epoch_revisions
                ORDER BY revision
                """
            ).fetchall()
            self._validate_audit_rows(rows, document, revision)
            return None if document is None else _copy(document)
        except sqlite3.Error as exc:
            raise SQLiteRouteEpochStoreError(f"could not load SQLite route ledger: {exc}") from exc
        finally:
            connection.close()

    def compare_and_swap(
        self,
        expected_ledger_digest: str | None,
        replacement: Mapping[str, Any],
        *,
        actor_id: str,
    ) -> bool:
        """Atomically publish an append-only ledger revision.

        Returns False when another writer has already changed the expected
        revision. Raises on malformed, semantically invalid or non-append-only
        replacement documents.
        """
        if type(actor_id) is not str or not actor_id.strip():
            raise SQLiteRouteEpochStoreError("actor_id must be non-empty text")
        if expected_ledger_digest is not None:
            _sha256(expected_ledger_digest, "expected_ledger_digest")
        candidate = _validate_document(replacement)
        candidate_json = _canonical(candidate)
        candidate_digest = _sha256(candidate.get("ledger_digest"), "replacement.ledger_digest")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current, current_revision = self._read_current(connection)
            current_digest = None if current is None else current["ledger_digest"]
            if current_digest != expected_ledger_digest:
                connection.rollback()
                return False

            current_entries = [] if current is None else current["entries"]
            candidate_entries = candidate["entries"]
            if (
                len(candidate_entries) < len(current_entries)
                or candidate_entries[:len(current_entries)] != current_entries
            ):
                raise SQLiteRouteEpochStoreError(
                    "SQLite route ledger replacement is not an append-only extension"
                )
            appended = candidate_entries[len(current_entries):]
            if not appended:
                raise SQLiteRouteEpochStoreError(
                    "SQLite route-ledger CAS must append at least one event"
                )

            audit_rows = connection.execute(
                """
                SELECT revision, previous_ledger_digest, ledger_digest,
                       actor_id, appended_event_digests_json, committed_utc
                FROM route_epoch_revisions
                ORDER BY revision
                """
            ).fetchall()
            self._validate_audit_rows(audit_rows, current, current_revision)

            next_revision = 1 if current_revision is None else current_revision + 1
            appended_digests = [event["event_digest"] for event in appended]
            connection.execute(
                """
                INSERT INTO route_epoch_revisions (
                    revision, previous_ledger_digest, ledger_digest,
                    actor_id, appended_event_digests_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    next_revision,
                    current_digest,
                    candidate_digest,
                    actor_id,
                    _canonical(appended_digests),
                ),
            )
            connection.execute(
                """
                INSERT INTO route_epoch_current (
                    singleton, revision, ledger_digest, document_json
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    revision = excluded.revision,
                    ledger_digest = excluded.ledger_digest,
                    document_json = excluded.document_json
                """,
                (next_revision, candidate_digest, candidate_json),
            )
            connection.commit()
            return True
        except SQLiteRouteEpochStoreError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise SQLiteRouteEpochStoreError(f"SQLite route-ledger CAS failed: {exc}") from exc
        finally:
            connection.close()

    def revision_history(self) -> tuple[dict[str, Any], ...]:
        """Return immutable revision metadata after verifying the audit chain."""
        connection = self._connect()
        try:
            document, revision = self._read_current(connection)
            rows = connection.execute(
                """
                SELECT revision, previous_ledger_digest, ledger_digest,
                       actor_id, appended_event_digests_json, committed_utc
                FROM route_epoch_revisions
                ORDER BY revision
                """
            ).fetchall()
            self._validate_audit_rows(rows, document, revision)
            result = []
            for row in rows:
                result.append({
                    "revision": row["revision"],
                    "previous_ledger_digest": row["previous_ledger_digest"],
                    "ledger_digest": row["ledger_digest"],
                    "actor_id": row["actor_id"],
                    "appended_event_digests": json.loads(row["appended_event_digests_json"]),
                    "committed_utc": row["committed_utc"],
                })
            return tuple(result)
        except sqlite3.Error as exc:
            raise SQLiteRouteEpochStoreError(f"could not read SQLite route revision history: {exc}") from exc
        finally:
            connection.close()


__all__ = [
    "SQLiteRouteEpochStoreError",
    "SQLiteRouteEpochLedgerStore",
]

"""Executable reference models for proof-worker runner crash semantics.

The module deliberately separates pure computation-result persistence from an
external effect provider. Neither implementation claims to make arbitrary
remote side effects transactional.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class RunnerSemanticsError(ValueError):
    """Invalid ticket, request, result, or conflicting idempotency reuse."""


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
        raise RunnerSemanticsError("runner values must be finite JSON data") from exc


def _digest(rendered: str) -> str:
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunnerSemanticsError(f"{label} must be non-empty text")
    return value


def _mapping_json(value: Any, label: str) -> tuple[dict[str, Any], str, str]:
    if not isinstance(value, Mapping):
        raise RunnerSemanticsError(f"{label} must be a JSON object")
    rendered = _canonical(dict(value))
    return json.loads(rendered), rendered, _digest(rendered)


class SQLitePureResultRunner:
    """Persist one published result per ticket for a pure/deterministic compute.

    `compute` executes while a SQLite write transaction is held. A crash before
    commit rolls back the result and a retry may recompute. A crash after commit
    but before the caller receives the result is recovered by replaying the
    stored result. Thus this provides once-only result publication, not an
    exactly-once guarantee that the computation itself ran only once.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS runner_results (
                    execution_id TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    result_digest TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def execute_once(
        self,
        execution_id: str,
        request: Mapping[str, Any],
        *,
        compute: Callable[[dict[str, Any]], Mapping[str, Any]],
        after_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Compute or replay a result under one stable execution ID.

        `after_commit` is a failure-injection hook. Raising from it models a
        process/response failure after the durable result has committed.
        """
        ticket = _identifier(execution_id, "execution_id")
        if not callable(compute):
            raise RunnerSemanticsError("compute must be callable")
        request_copy, _request_json, request_digest = _mapping_json(request, "request")
        connection = self._connect()
        created = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT request_digest, result_json, result_digest FROM runner_results WHERE execution_id = ?",
                (ticket,),
            ).fetchone()
            if existing is not None:
                if existing[0] != request_digest:
                    raise RunnerSemanticsError(
                        "execution ID was reused with a different request digest"
                    )
                if _digest(existing[1]) != existing[2]:
                    raise RunnerSemanticsError("stored runner result digest mismatch")
                result = json.loads(existing[1])
                connection.commit()
                return result

            result, result_json, result_digest = _mapping_json(
                compute(request_copy), "computed result"
            )
            connection.execute(
                """INSERT INTO runner_results
                   (execution_id, request_digest, result_json, result_digest)
                   VALUES (?, ?, ?, ?)""",
                (ticket, request_digest, result_json, result_digest),
            )
            connection.commit()
            created = True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

        if created and after_commit is not None:
            after_commit()
        return result

    def result_count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) FROM runner_results").fetchone()
            return int(row[0])

    def result_for(self, execution_id: str) -> dict[str, Any] | None:
        ticket = _identifier(execution_id, "execution_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT result_json, result_digest FROM runner_results WHERE execution_id = ?",
                (ticket,),
            ).fetchone()
        if row is None:
            return None
        if _digest(row[0]) != row[1]:
            raise RunnerSemanticsError("stored runner result digest mismatch")
        return json.loads(row[0])


class SQLiteIdempotentEffectSink:
    """Reference effect provider with atomic effect + idempotency receipt.

    The `effects` row and the idempotency result are committed in the same
    SQLite transaction. This models a provider whose effect and idempotency
    receipt share one transactional authority. It is not a wrapper that can
    make an arbitrary HTTP call or external side effect atomic.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS effects (
                    effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL UNIQUE,
                    command_digest TEXT NOT NULL,
                    command_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS effect_receipts (
                    execution_id TEXT PRIMARY KEY,
                    command_digest TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    result_digest TEXT NOT NULL
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10.0)
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def apply_once(
        self,
        execution_id: str,
        command: Mapping[str, Any],
        *,
        after_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Apply one modeled effect per ID, replaying its original receipt."""
        ticket = _identifier(execution_id, "execution_id")
        command_copy, command_json, command_digest = _mapping_json(command, "command")
        connection = self._connect()
        created = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT command_digest, result_json, result_digest FROM effect_receipts WHERE execution_id = ?",
                (ticket,),
            ).fetchone()
            if existing is not None:
                if existing[0] != command_digest:
                    raise RunnerSemanticsError(
                        "execution ID was reused with a different command digest"
                    )
                if _digest(existing[1]) != existing[2]:
                    raise RunnerSemanticsError("stored effect receipt digest mismatch")
                result = json.loads(existing[1])
                connection.commit()
                return result

            cursor = connection.execute(
                "INSERT INTO effects (execution_id, command_digest, command_json) VALUES (?, ?, ?)",
                (ticket, command_digest, _canonical(command_copy)),
            )
            effect_id = int(cursor.lastrowid)
            result, result_json, result_digest = _mapping_json(
                {
                    "status": "applied",
                    "execution_id": ticket,
                    "effect_id": effect_id,
                    "command_digest": command_digest,
                },
                "effect receipt",
            )
            connection.execute(
                """INSERT INTO effect_receipts
                   (execution_id, command_digest, result_json, result_digest)
                   VALUES (?, ?, ?, ?)""",
                (ticket, command_digest, result_json, result_digest),
            )
            connection.commit()
            created = True
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

        if created and after_commit is not None:
            after_commit()
        return result

    def effect_count(self) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT COUNT(*) FROM effects").fetchone()
            return int(row[0])

    def receipt_for(self, execution_id: str) -> dict[str, Any] | None:
        ticket = _identifier(execution_id, "execution_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT result_json, result_digest FROM effect_receipts WHERE execution_id = ?",
                (ticket,),
            ).fetchone()
        if row is None:
            return None
        if _digest(row[0]) != row[1]:
            raise RunnerSemanticsError("stored effect receipt digest mismatch")
        return json.loads(row[0])


def nontransactional_recovery_outcomes(
    *,
    effect_already_happened: bool,
) -> dict[str, int]:
    """Return observable effect counts for retry-vs-skip at a `started` ticket.

    The runner's durable state is identical (`started`) in both worlds. Only
    the independent external effect differs: it may not yet have happened, or
    it may have happened just before the crash and before a completion receipt
    was written.
    """
    before_recovery = 1 if effect_already_happened else 0
    return {
        "retry_started": before_recovery + 1,
        "skip_started": before_recovery,
    }

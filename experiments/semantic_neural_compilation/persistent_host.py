"""SNC-003: durable, policy-gated semantic neural realization host.

A verified exact semantic description is compiled once into a rational ReLU
network. SQLite stores its independently verified capsule; same-process reads
reuse the checked model and new processes re-verify the saved capsule before
serving it without rerunning the compiler.

This is a bounded, pure mathematical observer, not a GPU backend or an E-CPU
authorization service. The allowlist belongs to the receiver, never the wire.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

from compiler import AtlasRejected, compile_semantics, parse_atlas, describe
from continuous_equivalence import evaluate, layer, token
from independent_certificate_checker import (
    CertificateError, hash_bytes, parse_network, rational,
)
from verifier import verify_capsule, strict_json

POLICY_SCHEMA = "in-formation-space.snc003.receiver-policy/0.1"
RECEIPT_SCHEMA = "in-formation-space.snc003.observation-receipt/0.1"
COMPILER_ID = "snc001.hinge-realization/0.1"
DB_VERSION = 3
_MAX_RECEIVER_MODELS = 16
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_REQ = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z", re.ASCII)


class HostRejected(ValueError):
    """A request, saved realization, or receiver-owned authority failed closed."""


def require(condition: bool, why: str) -> None:
    if not condition:
        raise HostRejected(why)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == keys,
            f"incorrect {label} fields")
    return value


@dataclass
class Realization:
    semantic_sha256: str
    network_sha256: str
    layers: tuple
    policy_sha256: str


class PersistentSemanticHost:
    def __init__(self, database: Path, policy_path: Path):
        self.database = Path(database)
        self.policy_path = Path(policy_path)
        require(not self.database.is_symlink() and
                not self.policy_path.is_symlink(), "refuse symlinked state or policy")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._memo: dict[str, Realization] = {}
        with self._connect() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            require(version in (0, DB_VERSION), "unsupported database version")
            con.execute("""CREATE TABLE IF NOT EXISTS realizations (
                model TEXT NOT NULL,
                semantic_sha TEXT NOT NULL,
                compiler_id TEXT NOT NULL,
                network_sha TEXT NOT NULL,
                capsule_sha TEXT NOT NULL,
                capsule BLOB NOT NULL,
                PRIMARY KEY (model, semantic_sha, compiler_id)
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS observations (
                request_id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                semantic_sha TEXT NOT NULL,
                coordinate TEXT NOT NULL,
                receipt_sha TEXT NOT NULL,
                receipt BLOB NOT NULL
            )""")
            con.execute(f"PRAGMA user_version={DB_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database, timeout=10.0)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _policy(self, model: str) -> tuple[str, str]:
        require(type(model) is str and _ID.fullmatch(model) is not None,
                "invalid model identity")
        require(not self.policy_path.is_symlink(), "symlinked policy prohibited")
        try:
            raw = self.policy_path.read_bytes()
            require(0 < len(raw) < 16_384, "receiver policy size budget")
            obj = strict_json(raw)
        except (OSError, CertificateError) as exc:
            raise HostRejected("unavailable/noncanonical receiver policy") from exc
        exact_object(obj, {"schema", "models"}, "receiver policy")
        require(obj["schema"] == POLICY_SCHEMA and type(obj["models"]) is dict and
                0 < len(obj["models"]) <= _MAX_RECEIVER_MODELS,
                "unsupported receiver policy")
        for key, value in obj["models"].items():
            require(type(key) is str and _ID.fullmatch(key) is not None and
                    type(value) is str and _HASH.fullmatch(value) is not None,
                    "invalid receiver-owned model pin")
        require(model in obj["models"], "model absent/revoked by receiver policy")
        return obj["models"][model], sha(raw)

    @staticmethod
    def _hydrate(raw: bytes, expected: str, network_sha: str,
                 capsule_sha: str, policy_sha: str) -> Realization:
        require(type(raw) is bytes and 0 < len(raw) <= 512_000 and
                sha(raw) == capsule_sha, "corrupt persisted capsule bytes")
        try:
            checked = verify_capsule(raw, expected_source_sha256=expected)
        except (CertificateError, AtlasRejected, ValueError, KeyError) as exc:
            raise HostRejected("persisted neural certificate verification failed") from exc
        require(checked["generated_network_sha256"] == network_sha,
                "persisted network identity substitution")
        doc = strict_json(raw)
        parsed = parse_network(doc["generated_certificate"]["network"])
        layers = tuple(layer(weights, bias, activation)
                       for activation, weights, bias in parsed)
        return Realization(expected, network_sha, layers, policy_sha)

    def resolve(self, model: str, source: object | None = None
                ) -> tuple[Realization, str, dict[str, int]]:
        expected, policy_sha = self._policy(model)
        if source is not None:
            require(type(source) is list, "semantic atlas must be a list")
            require(hash_bytes(source) == expected,
                    "semantic atlas does not match receiver-owned source identity")
            try:
                regions = parse_atlas(source)
                require(describe(regions) == source, "noncanonical semantic description")
            except AtlasRejected as exc:
                raise HostRejected("invalid source semantic atlas") from exc
        prior = self._memo.get(model)
        if prior is not None and prior.semantic_sha256 == expected and \
                prior.policy_sha256 == policy_sha:
            return prior, "memory-reused", {"construction_ns": 0, "verification_ns": 0}

        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT network_sha, capsule_sha, capsule FROM realizations "
                "WHERE model=? AND semantic_sha=? AND compiler_id=?",
                (model, expected, COMPILER_ID),
            ).fetchone()
            if row is not None:
                started = time.perf_counter_ns()
                realization = self._hydrate(row[2], expected, row[0], row[1],
                                            policy_sha)
                verified_ns = time.perf_counter_ns() - started
                state = "restored-verified"
                timing = {"construction_ns": 0, "verification_ns": verified_ns}
            else:
                require(source is not None,
                        "no admitted realization for this semantic address")
                started = time.perf_counter_ns()
                try:
                    generated = compile_semantics(source)
                except AtlasRejected as exc:
                    raise HostRejected("semantic compiler rejected source") from exc
                constructed_ns = time.perf_counter_ns() - started
                saved = canonical(generated)
                started = time.perf_counter_ns()
                checked = self._hydrate(saved, expected,
                                        generated["generated_certificate"]["network_sha256"],
                                        sha(saved), policy_sha)
                verified_ns = time.perf_counter_ns() - started
                con.execute(
                    "INSERT INTO realizations "
                    "(model, semantic_sha, compiler_id, network_sha, capsule_sha, capsule) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (model, expected, COMPILER_ID, checked.network_sha256,
                     sha(saved), saved),
                )
                realization = checked
                state = "constructed-verified"
                timing = {"construction_ns": constructed_ns,
                          "verification_ns": verified_ns}
        self._memo[model] = realization
        return realization, state, timing

    def observe(self, *, model: str, coordinate: object, request_id: str,
                source: object | None = None) -> dict[str, object]:
        require(type(request_id) is str and _REQ.fullmatch(request_id) is not None,
                "invalid request identity")
        try:
            x = rational(coordinate)
        except CertificateError as exc:
            raise HostRejected("invalid exact input coordinate") from exc
        started = time.perf_counter_ns()
        realization, state, costs = self.resolve(model, source)
        evaluated = tuple(token(value) for value in
                          evaluate(realization.layers, x))
        receipt = {
            "schema": RECEIPT_SCHEMA, "request_id": request_id,
            "model": model, "semantic_sha256": realization.semantic_sha256,
            "generated_network_sha256": realization.network_sha256,
            "coordinate": token(x), "outputs": list(evaluated),
            "arithmetic": "exact-rational-reference-evaluation",
        }
        raw = canonical(receipt)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute(
                "SELECT model, semantic_sha, coordinate, receipt_sha, receipt "
                "FROM observations WHERE request_id=?", (request_id,),
            ).fetchone()
            if prior is not None:
                require(prior[0] == model and prior[1] == realization.semantic_sha256
                        and prior[2] == token(x), "conflicting request ID reuse")
                require(type(prior[4]) is bytes and sha(prior[4]) == prior[3] and
                        prior[4] == raw,
                        "tampered or conflicting saved observation receipt")
                disposition = "idempotent-replay"
            else:
                con.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)",
                    (request_id, model, realization.semantic_sha256,
                     token(x), sha(raw), raw),
                )
                disposition = "new-observation"
        return {
            "status": "verified-exact-mathematical-observation",
            "cache_state": state,
            "disposition": disposition,
            "receipt": receipt,
            "receipt_sha256": sha(raw),
            "construction_ns": costs["construction_ns"],
            "independent_verification_ns": costs["verification_ns"],
            "request_elapsed_ns_local": time.perf_counter_ns() - started,
            "external_execution_authorized": False,
        }

    def count(self, model: str) -> tuple[int, int]:
        expected, _ = self._policy(model)
        with self._connect() as con:
            models = con.execute(
                "SELECT COUNT(*) FROM realizations WHERE model=? AND semantic_sha=? "
                "AND compiler_id=?", (model, expected, COMPILER_ID)).fetchone()[0]
            observations = con.execute(
                "SELECT COUNT(*) FROM observations WHERE model=? AND semantic_sha=?",
                (model, expected)).fetchone()[0]
        return models, observations

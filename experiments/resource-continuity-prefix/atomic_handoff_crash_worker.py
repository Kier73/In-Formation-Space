"""RCP-003 independent worker: hard-crash at one named durable handoff cut.

A parent creates the genuine late E-CPU quorum fork and provisions a separately
protected receiver database. THIS child process performs staged handoff work,
then exits with os._exit before it can send an effect acknowledgement.
Two additional cuts kill the process within a public receiver SQL transaction,
after changing rows but before the COMMIT instruction. A new
Python interpreter/parent must reopen each original journal, recheck evidence
and recover from persistent state alone.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
import sys

# Workers run in CI with explicit PYTHONPATH for pinned E-CPU and VL-I.
from atomic_semantic_effect import (
    load_workspace,open_receiver,seal_successor,
    navigation_for,
)
from temporal_meet import _quorum,successor_membership

CUTS=("after_fork","after_freeze","after_seal","after_activate","after_effect",
      "before_activation_commit","before_effect_commit")


class CrashDuringCommit(sqlite3.Connection):
    """OS hard-kill after SQL state mutation but before durable COMMIT."""

    def execute(self, statement, parameters=()):
        if statement.strip().upper()=="COMMIT":
            os._exit(76 if CUT=="before_activation_commit" else 77)
        return super().execute(statement,parameters)


CUT=""


def interrupt_next_commit(receiver,cut):
    """Inject a fault into the EXACT public receiver method transaction."""
    global CUT
    CUT=cut

    def intercepted_connect():
        db=sqlite3.connect(str(receiver.path),timeout=8,
                           isolation_level=None,factory=CrashDuringCommit)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=8000")
        return db

    receiver._connect=intercepted_connect



def main()->None:
    if len(sys.argv)!=3 or sys.argv[1] not in CUTS:
        raise SystemExit("usage: crash_worker.py CUT ROOT")
    cut,location=sys.argv[1:]
    root=Path(location)
    if cut=="after_fork":
        # The original owner/observer and quorum history have just forked.
        # Nothing about the fork alone permits an external resource effect.
        os._exit(71)
    proof=load_workspace(root)
    receiver=open_receiver(root)
    receiver.freeze(proof)
    if cut=="after_freeze":
        os._exit(72)
    successor=seal_successor(root,proof)
    if cut=="after_seal":
        os._exit(73)
    if cut=="before_activation_commit":
        interrupt_next_commit(receiver,cut)
    installed=receiver.activate(
        proof,
        quorum=_quorum(root/"new-members",
                       successor_membership(proof.evidence.shared_manifest.digest)),
        manifest=successor,
    )
    if cut=="after_activate":
        os._exit(74)
    if cut=="before_effect_commit":
        interrupt_next_commit(receiver,cut)
    receiver.apply(
        epoch=2,root=installed["root"],
        context_digest=installed["context_digest"],
        operation_id="verified-sample-span-navigation",
        navigation=navigation_for(root),
    )
    # The effect is durable, but caller never receives its acknowledgement.
    os._exit(75)


if __name__=="__main__":
    main()

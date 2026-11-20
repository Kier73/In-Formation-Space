"""RCP-003 independent worker: hard-crash at one named durable handoff cut.

A parent creates the genuine late E-CPU quorum fork and provisions a separately
protected receiver database. THIS child process performs staged handoff work,
then exits with os._exit before it can send an effect acknowledgement. A new
Python interpreter/parent must reopen each original journal, recheck evidence
and recover from persistent state alone.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

# Workers run in CI with explicit PYTHONPATH for pinned E-CPU and VL-I.
from atomic_semantic_effect import (
    load_workspace,open_receiver,seal_successor,
    navigation_for,
)
from temporal_meet import _quorum,successor_membership

CUTS=("after_fork","after_freeze","after_seal","after_activate","after_effect")


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
    installed=receiver.activate(
        proof,
        quorum=_quorum(root/"new-members",
                       successor_membership(proof.evidence.shared_manifest.digest)),
        manifest=successor,
    )
    if cut=="after_activate":
        os._exit(74)
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

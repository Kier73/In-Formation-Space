#!/usr/bin/env python3
"""GRC-001: source-verifiable continuity of SAT and exact #SAT after CNF strengthening.

This is a *semantic* continuation mechanism, not reuse of a live execution
claim, host authorization, or even permission to reuse an old compiled machine.
All accepted facts are rechecked from the original source and proof receipts.
Unsupported computations return UNKNOWN. All clauses have width <= 3.
"""
from __future__ import annotations

import json
from time import perf_counter

from direct_sat_compiler import (validate_cnf, check_assignment, source_digest,
                                 produce_direct_sat, verify_direct_sat)
from language_choice_sat import (compile_language, verify_language_receipt)

VERSION = 'grc.sat.source-refinement.v1'


def normalized(clauses, n):
    """Exact CNF semantic normalization: tautologies omitted, duplicates ignored."""
    validate_cnf(clauses, n)
    out = set()
    for clause in clauses:
        lits = set(clause)
        if any(-v in lits for v in lits):
            continue
        out.add(tuple(sorted(lits, key=lambda v:(abs(v), v < 0))))
    return tuple(sorted(out, key=lambda c:(len(c), c)))


def _number(value):
    return (isinstance(value, str) and value.isascii() and
            value.isdecimal() and value == str(int(value)))


def source_extension(old, new, n):
    """The exact semantic premise: old clauses are a subset of new clauses."""
    base, target = set(normalized(old, n)), set(normalized(new, n))
    if not base.issubset(target):
        raise ValueError('new source removes or changes an original constraint')
    return list(sorted(base, key=lambda c:(len(c), c))), list(sorted(target-base,
                                                           key=lambda c:(len(c), c)))


def loss_query(prefix, new_clause):
    """Models lost on adding C: models of prefix AND NOT(C)."""
    return list(prefix) + [(-literal,) for literal in new_clause]


def _check_old(old, n, receipt):
    result = verify_language_receipt(old, n, receipt)
    goal = receipt.get('goal')
    if goal not in ('decision', 'count'):
        raise ValueError('unknown original intention')
    if goal == 'count' and result != 'UNKNOWN' and not _number(result):
        raise ValueError('invalid old exact count')
    return goal, result


def verify_revision(old, new, n, receipt, *, frontier_cell_cap=200000):
    """Replay all mathematical claims; ignore producer's cost and method choices.

    Note: this checker uses existing SPN verifier implementations. It is
    source-independent of the producer *policy*, not a formalized proof kernel.
    """
    old_prefix, added = source_extension(old, new, n)
    if not isinstance(receipt, dict) or receipt.get('version') != VERSION:
        raise ValueError('bad revision receipt')
    if (receipt.get('old_sha256') != source_digest(old,n) or
            receipt.get('new_sha256') != source_digest(new,n)):
        raise ValueError('source revision identity changed')
    previous = receipt.get('previous_receipt')
    goal, old_result = _check_old(old, n, previous)
    if receipt.get('goal') != goal:
        raise ValueError('goal changed across revision')
    steps = receipt.get('steps')
    if not isinstance(steps, list):
        raise ValueError('invalid proof steps')
    if goal == 'decision':
        if steps:
            raise ValueError('decision path must not invent count deltas')
        if old_result == 'UNSAT':
            result = 'UNSAT'             # UNSAT is monotone under strengthening
        elif old_result == 'SAT':
            witness = receipt.get('witness')
            if (not isinstance(witness,list) or len(witness) != n or
                    any(type(b) is not int or b not in (0,1) for b in witness) or
                    not check_assignment(old,witness) or
                    not check_assignment(new,witness)):
                result = 'UNKNOWN'
            else:
                result = 'SAT'
        else:
            result = 'UNKNOWN'
    else:
        if receipt.get('witness') is not None:
            raise ValueError('count revision has spurious witness')
        if old_result == 'UNKNOWN':
            if steps: raise ValueError('unknown baseline has unproved count deltas')
            result = 'UNKNOWN'
        else:
            current = int(old_result)
            prefix = list(old_prefix)
            if len(steps) > len(added):
                raise ValueError('more proofs than additions')
            for idx, step in enumerate(steps):
                clause = added[idx]
                if not isinstance(step, dict) or step.get('clause') != list(clause):
                    raise ValueError('altered or reordered added clause')
                kind = step.get('kind')
                if kind == 'monotone_zero':
                    if current != 0 or step.get('lost') != '0':
                        raise ValueError('unsupported monotone-zero inference')
                    lost = 0
                elif kind == 'entailed':
                    problem = loss_query(prefix,clause)
                    if verify_direct_sat(problem,n,step.get('proof')) != 'UNSAT':
                        raise ValueError('missing complete entailment proof')
                    if step.get('lost') != '0':
                        raise ValueError('false entailment loss')
                    lost = 0
                elif kind == 'counted_loss':
                    problem = loss_query(prefix,clause)
                    got = verify_language_receipt(problem,n,step.get('proof'),
                                                  frontier_cell_cap=frontier_cell_cap)
                    if got == 'UNKNOWN' or not _number(got) or got != step.get('lost'):
                        raise ValueError('changed or incomplete delta count')
                    lost = int(got)
                else:
                    raise ValueError('unknown Ground-revision proof method')
                if lost > current:
                    raise ValueError('count delta exceeds source count')
                current -= lost
                prefix.append(clause)
            if len(steps) != len(added):
                result = 'UNKNOWN'
            else:
                result = str(current)
    if result != receipt.get('result'):
        raise ValueError('revision claim does not follow from checked evidence')
    return result


def construct_revision(old,new,n,previous_receipt,*,
                       node_budget=256,frontier_cell_cap=200000,
                       allow_sfi=False):
    """Apply old verified computation to strengthened source, never trust hints.

    If an exact count delta cannot be proved within resource budgets,
    preserve UNKNOWN rather than claiming that old count still applies.
    """
    old_prefix, added=source_extension(old,new,n)
    goal,old_result=_check_old(old,n,previous_receipt)
    started=perf_counter()
    ledger=[];steps=[];witness=None
    if goal == 'decision':
        if old_result == 'UNSAT':
            result='UNSAT'
        elif old_result == 'SAT':
            # Producing a fresh witness through existing source-verifiable SAT
            # is valid, but any spent work is explicitly charged here.
            t=perf_counter()
            candidate=produce_direct_sat(new,n,node_budget=node_budget)
            status=verify_direct_sat(new,n,candidate)
            if status=='SAT':
                # Locate the proof's witness conservatively; newer proof
                # grammars may not expose it at the same nested level.
                def find_witness(node):
                    if isinstance(node,dict):
                        for key in ('witness','assignment'):
                            v=node.get(key)
                            if (isinstance(v,list) and len(v)==n and
                                all(type(b) is int and b in (0,1) for b in v) and
                                check_assignment(new,v)):
                                return v
                        for v in node.values():
                            found=find_witness(v)
                            if found is not None:return found
                    if isinstance(node,list):
                        for v in node:
                            found=find_witness(v)
                            if found is not None:return found
                    return None
                witness=find_witness(candidate)
            result='SAT' if witness is not None else 'UNKNOWN'
            ledger.append({'step':'revalidate_changed_SAT_witness',
                           'status':status,'ms':round((perf_counter()-t)*1000,3)})
        else:result='UNKNOWN'
    elif old_result=='UNKNOWN':
        result='UNKNOWN'
    else:
        current=int(old_result)
        prefix=list(old_prefix)
        result=None
        for clause in added:
            if current==0:
                steps.append({'kind':'monotone_zero','clause':list(clause),'lost':'0'})
                prefix.append(clause)
                continue
            query=loss_query(prefix,clause)
            t=perf_counter()
            entailed=produce_direct_sat(query,n,node_budget=node_budget)
            if verify_direct_sat(query,n,entailed)=='UNSAT':
                steps.append({'kind':'entailed','clause':list(clause),'lost':'0',
                              'proof':entailed})
                ledger.append({'step':'entailed','ms':round((perf_counter()-t)*1000,3)})
                prefix.append(clause)
                continue
            t=perf_counter()
            counted=compile_language(query,n,goal='count',allow_sfi=allow_sfi,
                                     frontier_cell_cap=frontier_cell_cap)
            loss=verify_language_receipt(query,n,counted,
                                         frontier_cell_cap=frontier_cell_cap)
            ledger.append({'step':'counted_loss','outcome':loss,
                           'ms':round((perf_counter()-t)*1000,3)})
            if loss=='UNKNOWN':
                result='UNKNOWN'
                break
            lost=int(loss)
            if lost>current:raise AssertionError('invalid count observation')
            steps.append({'kind':'counted_loss','clause':list(clause),
                          'lost':loss,'proof':counted})
            current-=lost
            prefix.append(clause)
        if result is None:
            result=str(current)
    receipt={'version':VERSION,'old_sha256':source_digest(old,n),
             'new_sha256':source_digest(new,n),'goal':goal,'result':result,
             'previous_receipt':previous_receipt,'steps':steps,'witness':witness,
             'producer_ledger':{'new_clauses':len(added),'attempts':ledger,
                      'total_ms':round((perf_counter()-started)*1000,3)}}
    if verify_revision(old,new,n,receipt,frontier_cell_cap=frontier_cell_cap)!=result:
        raise AssertionError('source checker rejected generated revision')
    return receipt


if __name__=='__main__':
    old=[(1,2),(-1,2)]
    new=old+[(1,)]
    base=compile_language(old,3,goal='count')
    receipt=construct_revision(old,new,3,base)
    print(json.dumps({'result':receipt['result'],'steps':receipt['steps'],
                      'cost':receipt['producer_ledger']},indent=2))

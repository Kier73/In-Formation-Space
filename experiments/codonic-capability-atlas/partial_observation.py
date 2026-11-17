"""COG-008: partial, counterexample-driven cognitive Ground acquisition.

No source-state or finite-conformance oracle is available to the learner.
COG-007's observation-table *constructor* is reused, but its omniscient
conformance/learn() gate is not called. Only explicit black-box membership
observations can change the proposed Ground. A separate verifier may test it.

The witness chain is content-addressed and receiver-pinned, never by itself an
attestation of a real source. A partial proposal is never called globally exact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Protocol
import copy

from cognitive_grounds import GroundRefused, canonical, digest
from predictive_state import (ActiveMachineLearner, Machine, SCHEMA as MODEL_SCHEMA)

SCHEMA = 'in-formation.partial-cognitive-observer/008'
MAX_MEMBERSHIP = 100_000


class MembershipSource(Protocol):
    source_root: str
    alphabet: tuple[str, ...]
    def query(self, actions: Sequence[str]) -> tuple[tuple, ...]: ...


def _word(word:Sequence[str], alphabet:tuple[str,...])->tuple[str,...]:
    if not isinstance(word,(tuple,list)) or len(word)>64 or any(type(x) is not str or x not in alphabet for x in word):
        raise GroundRefused('query outside pinned finite observation contract')
    return tuple(word)


def _answers(answer:Sequence[Sequence],n:int)->tuple[tuple,...]:
    if not isinstance(answer,(tuple,list)) or len(answer)!=n:
        raise GroundRefused('source reply length contradicts query')
    output=[]
    for v in answer:
        if (not isinstance(v,(tuple,list)) or not 1<=len(v)<=3 or
                any(type(z) not in (int,str) or (type(z) is str and len(z)>1024) for z in v)):
            raise GroundRefused('noncanonical or invalid typed source response')
        output.append(tuple(v))
    return tuple(output)


def genesis(source_root:str,alphabet:tuple[str,...])->str:
    return digest({'schema':SCHEMA,'genesis':source_root,'alphabet':list(alphabet)})


@dataclass(frozen=True)
class MembershipWitness:
    index:int
    previous:str
    path:tuple[str,...]
    outputs:tuple[tuple,...]
    hash:str

    @classmethod
    def create(cls,index:int,previous:str,source_root:str,alphabet:tuple[str,...],path:Sequence[str],outputs:Sequence[Sequence])->'MembershipWitness':
        if type(index) is not int or not 0<=index<MAX_MEMBERSHIP:
            raise GroundRefused('membership index invalid or exceeds budget')
        p=_word(path,alphabet);o=_answers(outputs,len(p))
        if type(previous) is not str or len(previous)!=64:
            raise GroundRefused('invalid previous evidence root')
        h=digest({'schema':SCHEMA,'index':index,'previous':previous,'source_root':source_root,'alphabet':list(alphabet),
                  'path':list(p),'outputs':[list(v) for v in o]})
        return cls(index,previous,p,o,h)

    def document(self)->dict:
        return {'index':self.index,'previous':self.previous,'path':list(self.path),
                'outputs':[list(v) for v in self.outputs],'hash':self.hash}


class ObservedOracle:
    """External black-box source; only membership observations are visible."""
    def __init__(self,source:MembershipSource,*,max_queries:int=MAX_MEMBERSHIP):
        if (type(source.source_root) is not str or len(source.source_root)!=64 or
                not isinstance(source.alphabet,tuple) or not source.alphabet or
                len(set(source.alphabet))!=len(source.alphabet) or
                type(max_queries) is not int or not 1<=max_queries<=MAX_MEMBERSHIP):
            raise GroundRefused('invalid observation source binding')
        self.source=source;self.source_root=source.source_root;self.alphabet=source.alphabet
        self.limit=max_queries;self._observed:dict[tuple[str,...],tuple[tuple,...]]={}
        self.witnesses:list[MembershipWitness]=[]
        self.external_calls=0

    @property
    def head(self)->str:
        return self.witnesses[-1].hash if self.witnesses else genesis(self.source_root,self.alphabet)

    def query(self,path:Sequence[str])->tuple[tuple,...]:
        p=_word(path,self.alphabet)
        if p in self._observed:return self._observed[p]
        if len(self.witnesses)>=self.limit:raise GroundRefused('membership budget exhausted; unknown')
        observed=_answers(self.source.query(p),len(p))
        self.external_calls+=1
        witness=MembershipWitness.create(len(self.witnesses),self.head,self.source_root,self.alphabet,p,observed)
        self.witnesses.append(witness);self._observed[p]=observed
        return observed

    def continuation(self,prefix:Sequence[str],suffix:Sequence[str])->tuple[tuple,...]:
        p=_word(prefix,self.alphabet);s=_word(suffix,self.alphabet)
        if not s:raise GroundRefused('empty distinguishing continuation')
        return self.query(p+s)[len(p):]

    def recheck(self,path:Sequence[str])->bool:
        """Detect source drift or equivocation under a claimed unchanged source root."""
        p=_word(path,self.alphabet)
        if p not in self._observed:raise GroundRefused('cannot recheck unobserved claim')
        fresh=_answers(self.source.query(p),len(p));self.external_calls+=1
        if fresh!=self._observed[p]:raise GroundRefused('source changed under same pinned epoch')
        return True

    def document(self)->dict:
        core={'schema':SCHEMA+'.ledger','source_root':self.source_root,
              'alphabet':list(self.alphabet),'witnesses':[w.document() for w in self.witnesses],
              'head':self.head,'count':len(self.witnesses)}
        return {**core,'digest':digest(core)}


class FrozenOracle:
    """Source-free recovery of exact observed member answers, no host calls."""
    def __init__(self,document:Mapping[str,Any],*,expected_head:str,expected_source_root:str):
        if (not isinstance(document,Mapping) or set(document)!={'schema','source_root','alphabet','witnesses','head','count','digest'}
                or document['schema']!=SCHEMA+'.ledger' or document['source_root']!=expected_source_root):
            raise GroundRefused('wrong observation source or malformed recovered ledger')
        core={k:v for k,v in document.items() if k!='digest'}
        if digest(core)!=document['digest'] or document['head']!=expected_head:
            raise GroundRefused('ledger root does not match independent receiver pin')
        self.source_root=expected_source_root
        a=document['alphabet']
        if not isinstance(a,list) or not a or len(set(a))!=len(a):raise GroundRefused('invalid recovered alphabet')
        self.alphabet=tuple(a)
        self._observed={};self.witnesses=[];self.external_calls=0
        head=genesis(self.source_root,self.alphabet)
        if not isinstance(document['witnesses'],list) or document['count']!=len(document['witnesses']) or len(document['witnesses'])>MAX_MEMBERSHIP:
            raise GroundRefused('invalid recovered observation count')
        for item in document['witnesses']:
            if not isinstance(item,Mapping) or set(item)!={'index','previous','path','outputs','hash'}:
                raise GroundRefused('malformed membership witness')
            w=MembershipWitness.create(len(self.witnesses),head,self.source_root,self.alphabet,item['path'],item['outputs'])
            if w.document()!=dict(item) or w.path in self._observed:
                raise GroundRefused('changed/duplicated membership evidence')
            self.witnesses.append(w);self._observed[w.path]=w.outputs;head=w.hash
        if head!=document['head']:raise GroundRefused('changed membership predecessor chain')
        self.head=head

    def query(self,path:Sequence[str])->tuple[tuple,...]:
        p=_word(path,self.alphabet)
        if p not in self._observed:raise GroundRefused('unobserved Ground query remains unknown after recovery')
        return self._observed[p]

    def continuation(self,prefix:Sequence[str],suffix:Sequence[str])->tuple[tuple,...]:
        p=_word(prefix,self.alphabet);s=_word(suffix,self.alphabet)
        if not s:raise GroundRefused('empty distinguishing continuation')
        return self.query(p+s)[len(p):]


def fit_table(learning:ActiveMachineLearner,*,max_rounds:int=10000)->Machine:
    """Close an observation table, without ever invoking full-state conformance."""
    for _ in range(max_rounds):
        learning.rounds+=1
        if len(learning.S)>2048 or len(learning.E)>2048:
            raise GroundRefused('observational state or suffix budget exceeded')
        if not learning._refine_table():
            return learning.candidate()
    raise GroundRefused('inconclusive observation-table budget')


def first_mismatch(machine:Machine,oracle:ObservedOracle,path:Sequence[str])->tuple[str,...]|None:
    word=_word(path,oracle.alphabet)
    expected=machine.run(word);observed=oracle.query(word)
    for k,(a,b) in enumerate(zip(expected,observed)):
        if a!=b:return word[:k+1]
    return None


def challenge_plan(learning:ActiveMachineLearner,*,max_paths:int=800)->tuple[tuple[str,...],...]:
    """Observation-only checks of representative contexts and future contracts.

    Unlike the COG-007 omniscient conformance oracle this list can miss a
    hidden behavior. Passing the challenge never certifies universal equality.
    """
    alphabet=learning.teacher.alphabet
    core=tuple(a for a in ('minutes','seconds','repeat','clear','noise','who') if a in alphabet)
    suffixes=tuple([(a,) for a in core]+[(a,b) for a in core for b in core if b in ('repeat','minutes','who')])
    reps=tuple(learning.S)
    # Explicit task obligations: a concept acquired under 'mention' may require
    # identity-sensitive recall even when representative states currently merge.
    # This selection uses ONLY advertised input actions, never private source data.
    paths=[];seen=set()
    if 'who' in core:
        for name in alphabet:
            if name.startswith('mention:'):
                path=(name,'who')
                if path not in seen:
                    paths.append(path);seen.add(path)
                    if len(paths)>=max_paths:return tuple(paths)
    for suffix in suffixes:
        for prefix in reps:
            path=prefix+suffix
            if path not in seen and len(path)<=64:
                paths.append(path);seen.add(path)
                if len(paths)>=max_paths:return tuple(paths)
    return tuple(paths)


def experimental_revision(source:ObservedOracle,*,max_cycles:int=18,max_challenges:int=800)->tuple[ActiveMachineLearner,Machine,dict]:
    """Learn from membership queries and actual falsifying counterexamples.

    This intentionally DOES NOT call COG-007's full conformance oracle, nor
    assume a finite reference model is known by the learner.
    """
    if type(max_cycles) is not int or not 1<=max_cycles<=128:raise GroundRefused('invalid revision bound')
    learner=ActiveMachineLearner(source)
    failures=[];checked=0
    for cycle in range(max_cycles):
        machine=fit_table(learner)
        counterexample=None
        for path in challenge_plan(learner,max_paths=max_challenges):
            checked+=1
            counterexample=first_mismatch(machine,source,path)
            if counterexample is not None:break
        if counterexample is None:
            # Important: observational evidence only, no global-equivalence claim.
            remaining=sum(machine.run(w.path)!=w.outputs for w in source.witnesses)
            if remaining:
                raise GroundRefused('candidate contradicts a retained earlier observation')
            return learner,machine,{'status':'provisional_finitely_challenged',
                                    'challenge_paths_checked':checked,
                                    'revisions':len(failures),'counterexamples':[list(x) for x in failures],
                                    'unexplored_continuations':'unknown',
                                    'membership_calls':source.external_calls}
        if counterexample in failures:raise GroundRefused('identical unresolved counterexample')
        failures.append(counterexample)
        learner.counterexamples.append(counterexample)
        for k in range(len(counterexample)):
            suffix=counterexample[k:]
            if suffix not in learner.E:learner.E.append(suffix)
    raise GroundRefused('exhausted challenge budget; no supported full model')


def checkpoint(source:ObservedOracle,learner:ActiveMachineLearner,machine:Machine,report:Mapping[str,Any])->dict:
    if (machine.source_root!=source.source_root or machine.alphabet!=source.alphabet or
            report.get('status')!='provisional_finitely_challenged' or
            any(machine.run(w.path)!=w.outputs for w in source.witnesses)):
        raise GroundRefused('cannot promote a contradictory partial Ground')
    ground={'model':machine.document(),'table':{'S':[list(s) for s in learner.S],
                                               'E':[list(e) for e in learner.E],
                                               'counterexamples':[list(e) for e in learner.counterexamples]},
            'status':'provisional_finitely_challenged',
            'global_equivalence':'not_established',
            'tests':dict(report)}
    core={'schema':SCHEMA+'.checkpoint','source_root':source.source_root,
          'ledger':source.document(),'ground':ground,
          'ledger_head':source.head,'machine_fingerprint':machine.fingerprint}
    return {**core,'digest':digest(core)}


def recover(saved:Mapping[str,Any],*,expected_checkpoint_digest:str,expected_ledger_head:str,
            expected_source_root:str)->tuple[Machine,FrozenOracle]:
    """Fresh-process reconstruction, without source oracle calls or old effects."""
    if (not isinstance(saved,Mapping) or set(saved)!={'schema','source_root','ledger','ground','ledger_head','machine_fingerprint','digest'}
            or saved['schema']!=SCHEMA+'.checkpoint' or saved['source_root']!=expected_source_root or
            saved['ledger_head']!=expected_ledger_head or saved['digest']!=expected_checkpoint_digest):
        raise GroundRefused('stale receiver pins or incompatible Ground')
    if digest({k:v for k,v in saved.items() if k!='digest'})!=saved['digest']:
        raise GroundRefused('changed checkpoint content')
    frozen=FrozenOracle(saved['ledger'],expected_head=expected_ledger_head,expected_source_root=expected_source_root)
    model=Machine.from_document(saved['ground']['model'])
    if (saved['ground']['status']!='provisional_finitely_challenged' or
            saved['ground']['global_equivalence']!='not_established' or
            model.fingerprint!=saved['machine_fingerprint'] or
            model.source_root!=frozen.source_root or model.alphabet!=frozen.alphabet):
        raise GroundRefused('changed or overstated hypothesis state')
    table=saved['ground']['table']
    if not isinstance(table,Mapping) or set(table)!={'S','E','counterexamples'}:
        raise GroundRefused('missing observed learning structure')
    # Restore the *actual* COG007 table constructor from retained observations.
    learner=ActiveMachineLearner(frozen)
    learner.S=[tuple(x) for x in table['S']]
    learner.E=[tuple(x) for x in table['E']]
    learner.counterexamples=[tuple(x) for x in table['counterexamples']]
    regenerated=learner.candidate()
    if regenerated.document()!=model.document():
        raise GroundRefused('hypothesis not independently reconstructible from retained observations')
    if any(model.run(w.path)!=w.outputs for w in frozen.witnesses):
        raise GroundRefused('recovered model contradicts retained observations')
    return model,frozen


def resume_after_revision(old_machine:Machine,new_machine:Machine,*,historical_actions:Sequence[str]|None)->tuple[int,str]:
    """Do not guess a new semantic state from an old, potentially merged index.

    A symbolic access history may be reinterpreted, without repeating any
    external semantic effects. Without one, remapping after refinement is unknown.
    """
    if old_machine.source_root!=new_machine.source_root or old_machine.alphabet!=new_machine.alphabet:
        raise GroundRefused('cannot migrate state across source epochs or contracts')
    if old_machine.fingerprint==new_machine.fingerprint:
        if historical_actions is None:raise GroundRefused('old numerical state index not enough to rebind safely')
        h=_word(historical_actions,old_machine.alphabet)
        return new_machine.state_after(h),'same_model'
    if historical_actions is None:
        raise GroundRefused('old quotient merged distinctions; history needed for safe remapping')
    h=_word(historical_actions,old_machine.alphabet)
    return new_machine.state_after(h),'reinterpreted_symbolic_history_without_external_execution'

"""COG-007: active discovery of task-relative predictive cognitive state.

The learner sees ONLY black-box input/output traces from a COG-006 Session.
An independent finite-contract conformance oracle checks the inferred Mealy
machine, supplies shortest counterexamples, and finally establishes an exact
quotient over the DECLARED finite source/alphabet. No natural-language parser,
real-world truth, or authenticated E-CPU host is inferred.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Sequence
import json
from cognitive_grounds import (Fact, FactGround, Learner, Session, GroundRefused,
                               canonical, digest)

SCHEMA = 'in-formation.predictive-cognitive-ground/007'
UNKNOWN = ('unknown',)
NOTED = ('noted',)
CLEARED = ('cleared',)
NOOP = ('no-op',)
Output = tuple[str, ...] | tuple[str, int]


def source_fixture(subjects: int = 32, distinct_durations: int = 8) -> tuple[FactGround, Learner]:
    """Distinct source identities, with controlled task-equivalent durations."""
    if (type(subjects) is not int or type(distinct_durations) is not int or
            not 2 <= distinct_durations <= subjects <= 1024):
        raise GroundRefused('invalid bounded source universe')
    records=[]
    for i in range(subjects):
        k=i%distinct_durations
        records.append(Fact(f'topic_{i:04d}',(5+k,7,11),2,
                            f'COG007-synthetic-source-{i:04d}'))
    ground=FactGround(tuple(records))
    target=ground.facts[0]
    learner=Learner(ground).admit(target.subject,sum(target.steps))
    if learner.promoted.operators!=('steps','sum'):
        raise GroundRefused('source procedural capability is not admitted')
    return ground,learner


class Teacher:
    """Query-only access to COG006 semantic behavior, not its private state."""
    def __init__(self, ground: FactGround, learner: Learner, *, named: bool = False):
        if learner.ground.root != ground.root or learner.promoted.operators!=('steps','sum'):
            raise GroundRefused('incompatible verified cognitive source')
        self.ground=ground;self.learner=learner;self.named=named
        self.alphabet=tuple(['clear','minutes','seconds','repeat','noise']+
                            (['who'] if named else [])+
                            [f'mention:{fact.subject}' for fact in ground.facts])
        self.cache:dict[tuple[str,...],tuple[Output,...]]={}
        self.calls=0

    @property
    def source_root(self)->str:
        return digest({'schema':SCHEMA,'ground':self.ground.root,
                       'source_learning':self.learner.head,
                       'contract':list(self.alphabet)})

    def query(self, actions: Sequence[str]) -> tuple[Output,...]:
        if len(actions)>64 or any(a not in self.alphabet for a in actions):
            raise GroundRefused('unregistered or excessive observation query')
        path=tuple(actions)
        if path in self.cache:return self.cache[path]
        session=Session(self.learner)
        last:Output|None=None
        out=[]
        for action in path:
            if action.startswith('mention:'):
                session=session.perform('mention',action.split(':',1)[1]);last=None
                result=NOTED
            elif action=='clear':
                session=session.perform('clear');last=None;result=CLEARED
            elif action=='minutes' or action=='seconds':
                session=session.perform('ask_minutes' if action=='minutes' else 'ask_seconds')
                answer=session.turns[-1].answer
                result=(action,answer['value']) if answer['status']=='verified_within_ground' else UNKNOWN
                last=result if result!=UNKNOWN else None
            elif action=='repeat':
                result=last if last is not None else UNKNOWN
            elif action=='who':
                result=('subject',session.anchor) if session.anchor is not None else UNKNOWN
            else:
                result=NOOP
            out.append(result)
        self.calls+=1
        self.cache[path]=tuple(out)
        return self.cache[path]

    def continuation(self, prefix:tuple[str,...], suffix:tuple[str,...]) -> tuple[Output,...]:
        if not suffix:raise GroundRefused('empty distinguishing suffix')
        return self.query(prefix+suffix)[len(prefix):]


@dataclass(frozen=True)
class Machine:
    source_root: str
    alphabet: tuple[str,...]
    representatives: tuple[tuple[str,...],...]
    transitions: tuple[tuple[int,...],...]
    emissions: tuple[tuple[Output,...],...]

    def __post_init__(self):
        size=len(self.representatives)
        if (not 1<=size<=4096 or len(self.transitions)!=size or
                len(self.emissions)!=size or len(self.alphabet)==0 or
                len(set(self.alphabet))!=len(self.alphabet)):
            raise GroundRefused('malformed predictive state machine')
        if not self.representatives[0]==():
            raise GroundRefused('initial state missing')
        for t,o in zip(self.transitions,self.emissions):
            if len(t)!=len(self.alphabet) or len(o)!=len(self.alphabet) or any(
                type(k) is not int or not 0<=k<size for k in t):
                raise GroundRefused('transition/emission table has wrong shape')

    def run_from(self, state:int, path:Sequence[str]) -> tuple[tuple[Output,...],int]:
        """Resume a retained semantic state without replaying predecessor turns."""
        if type(state) is not int or not 0<=state<len(self.representatives):
            raise GroundRefused('invalid retained semantic state')
        out=[];idx={a:i for i,a in enumerate(self.alphabet)}
        for action in path:
            if action not in idx:raise GroundRefused('outside admitted action alphabet')
            j=idx[action]
            out.append(self.emissions[state][j]);state=self.transitions[state][j]
        return tuple(out),state

    def run(self, path:Sequence[str]) -> tuple[Output,...]:
        return self.run_from(0,path)[0]

    def state_after(self, path:Sequence[str])->int:
        return self.run_from(0,path)[1]

    def document(self)->dict:
        return {'schema':SCHEMA,'source_root':self.source_root,'alphabet':list(self.alphabet),
                'representatives':[list(p) for p in self.representatives],
                'transitions':[list(v) for v in self.transitions],
                'emissions':[[list(o) for o in v] for v in self.emissions]}

    @classmethod
    def from_document(cls, doc:dict)->'Machine':
        if not isinstance(doc,dict) or set(doc)!={'schema','source_root','alphabet','representatives','transitions','emissions'} or doc['schema']!=SCHEMA:
            raise GroundRefused('malformed serialized cognitive Ground')
        return cls(doc['source_root'],tuple(doc['alphabet']),
                   tuple(tuple(x) for x in doc['representatives']),
                   tuple(tuple(x) for x in doc['transitions']),
                   tuple(tuple(tuple(o) for o in row) for row in doc['emissions']))

    @property
    def fingerprint(self)->str:return digest(self.document())


def _source_step(ground:FactGround, state:tuple[str|None,str|None], action:str)->tuple[tuple[str|None,str|None],Output]:
    """Independent oracle: direct typed fact semantics, no COG006 Session call."""
    subject,last=state
    if action.startswith('mention:'):
        target=action.split(':',1)[1]
        ground.record(target)
        return (target,None),NOTED
    if action=='clear':return (None,None),CLEARED
    if action=='noise':return state,NOOP
    if action=='who':return state,(('subject',subject) if subject is not None else UNKNOWN)
    if action in ('minutes','seconds'):
        if subject is None:return (subject,None),UNKNOWN
        total=sum(ground.record(subject).steps)
        return (subject,action),(action,total*(60 if action=='seconds' else 1))
    if action=='repeat':
        if subject is None or last is None:return state,UNKNOWN
        total=sum(ground.record(subject).steps)
        return state,(last,total*(60 if last=='seconds' else 1))
    raise GroundRefused('unknown action in source reference')


@dataclass(frozen=True)
class Conformance:
    equivalent: bool
    counterexample: tuple[str,...]|None
    checked_pairs: int
    checked_edges: int
    source_states: int


def conformance(teacher:Teacher, machine:Machine, *, max_pairs:int=500_000)->Conformance:
    """Exhaustive BFS over reachable reference×learned states for THIS finite contract.

    Returns shortest distinguishing input trace or exact equivalence within the
    declared bounded finite source and action set. Does NOT prove PyBot behavior.
    """
    if machine.source_root!=teacher.source_root or machine.alphabet!=teacher.alphabet:
        raise GroundRefused('attempt to verify a different observation contract')
    start=(None,None)
    q=deque([(start,0,())]);visited={(start,0)};source_seen={start};edges=0
    while q:
        source,i,trace=q.popleft()
        for j,action in enumerate(machine.alphabet):
            future,reply=_source_step(teacher.ground,source,action)
            edges+=1;source_seen.add(future)
            if machine.emissions[i][j]!=reply:
                return Conformance(False,trace+(action,),len(visited),edges,len(source_seen))
            dest=machine.transitions[i][j];pair=(future,dest)
            if pair not in visited:
                if len(visited)>=max_pairs:
                    raise GroundRefused('conformance exploration budget exceeded; unresolved')
                visited.add(pair);q.append((future,dest,trace+(action,)))
    return Conformance(True,None,len(visited),edges,len(source_seen))


class ActiveMachineLearner:
    """Observation-table learner with source-supplied counterexample refinement."""
    def __init__(self,teacher:Teacher):
        self.teacher=teacher
        self.S=[()]
        self.E=[('minutes',)]
        self.counterexamples:list[tuple[str,...]]=[]
        self.rounds=0
        self._row_cache={}

    def row(self, prefix:tuple[str,...])->tuple[tuple[Output,...],...]:
        return tuple(self.teacher.continuation(prefix,e) for e in self.E)

    def candidate(self)->Machine:
        rows={self.row(s):i for i,s in enumerate(self.S)}
        if len(rows)!=len(self.S):
            raise GroundRefused('observation table has duplicate representative states')
        table=[];emissions=[]
        for s in self.S:
            t=[];v=[]
            for a in self.teacher.alphabet:
                next_row=self.row(s+(a,))
                if next_row not in rows:raise GroundRefused('observation table is not closed')
                t.append(rows[next_row]);v.append(self.teacher.continuation(s,(a,))[0])
            table.append(tuple(t));emissions.append(tuple(v))
        return Machine(self.teacher.source_root,self.teacher.alphabet,
                       tuple(self.S),tuple(table),tuple(emissions))

    def _refine_table(self)->bool:
        # Closure: expose reachable behavior rows without revealing hidden states.
        rows={self.row(s) for s in self.S}
        for s in tuple(self.S):
            for a in self.teacher.alphabet:
                candidate=s+(a,)
                r=self.row(candidate)
                if r not in rows:
                    self.S.append(candidate);return True
        # Consistency: equivalent rows must remain equivalent after every action.
        for i,s in enumerate(self.S):
            for t in self.S[i+1:]:
                if self.row(s)!=self.row(t):continue
                for a in self.teacher.alphabet:
                    if self.row(s+(a,))==self.row(t+(a,)):continue
                    suffix=next(e for e in self.E if self.teacher.continuation(s+(a,),e)!=self.teacher.continuation(t+(a,),e))
                    witness=(a,)+suffix
                    if witness not in self.E:
                        self.E.append(witness);return True
                    raise GroundRefused('consistency refinement did not progress')
        return False

    def learn(self, *,max_rounds:int=10_000,max_states:int=4096)->tuple[Machine,Conformance]:
        for _ in range(max_rounds):
            self.rounds+=1
            if len(self.S)>max_states or len(self.E)>max_states:
                raise GroundRefused('active cognitive acquisition exceeded memory budget')
            if self._refine_table():continue
            model=self.candidate()
            report=conformance(self.teacher,model)
            if report.equivalent:
                return model,report
            counterexample=report.counterexample
            assert counterexample is not None
            if counterexample in self.counterexamples:
                raise GroundRefused('repeated unresolved counterexample')
            self.counterexamples.append(counterexample)
            # A counterexample is a source observation. Its suffixes expose the
            # missing future distinction, without needing source state access.
            for k in range(len(counterexample)):
                part=counterexample[k:]
                if part not in self.E:self.E.append(part)
        raise GroundRefused('finite conformance not established under learning budget')


def minimality(teacher:Teacher, machine:Machine)->bool:
    """All states reachable and every distinct pair future distinguishable."""
    states=len(machine.representatives)
    reached={0};pending=[0]
    while pending:
        for nxt in machine.transitions[pending.pop()]:
            if nxt not in reached:
                reached.add(nxt);pending.append(nxt)
    if len(reached)!=states:return False
    for i in range(states):
        for j in range(i+1,states):
            q=deque([(i,j)]);checked={(i,j)};found=False
            while q:
                a,b=q.popleft()
                for k in range(len(machine.alphabet)):
                    if machine.emissions[a][k]!=machine.emissions[b][k]:
                        found=True;break
                    u,v=machine.transitions[a][k],machine.transitions[b][k]
                    pair=(min(u,v),max(u,v))
                    if pair not in checked:
                        checked.add(pair);q.append(pair)
                if found:break
            if not found:return False
    return True


def receipt(teacher:Teacher,model:Machine,report:Conformance,learner:ActiveMachineLearner)->dict:
    if not report.equivalent or not minimality(teacher,model):
        raise GroundRefused('unverified, nonminimal predictive state not admitted')
    core={'schema':SCHEMA+'.receipt','source_root':teacher.source_root,
          'hypothesis':model.document(),
          'provenance':'source-pinned finite COG006 typed conversation; no external authentication',
          'scope':'exact declared finite alphabet and finite COG006 source; not PyBot equivalence',
          'evidence':{'counterexamples':[list(x) for x in learner.counterexamples],
                      'candidate_rounds':learner.rounds,
                      'queries_executed':teacher.calls,'query_cache_size':len(teacher.cache),
                      'conformance_pairs':report.checked_pairs,
                      'conformance_edges':report.checked_edges,
                      'source_states':report.source_states,
                      'minimal_state_count':len(model.representatives)}}
    return {**core,'digest':digest(core)}


def restore(teacher:Teacher,saved:dict,*,external_digest:str,independent_verify:bool=True)->Machine:
    if (not isinstance(saved,dict) or set(saved)!={'schema','source_root','hypothesis','provenance','scope','evidence','digest'}
        or saved['schema']!=SCHEMA+'.receipt' or saved['source_root']!=teacher.source_root):
        raise GroundRefused('unknown source or malformed cognitive evidence')
    if digest({k:v for k,v in saved.items() if k!='digest'})!=saved['digest'] or saved['digest']!=external_digest:
        raise GroundRefused('changed or stale externally pinned predictive evidence')
    model=Machine.from_document(saved['hypothesis'])
    if model.source_root!=teacher.source_root or model.alphabet!=teacher.alphabet:
        raise GroundRefused('predictive source/observation contract substitution')
    if independent_verify:
        check=conformance(teacher,model)
        if not check.equivalent or not minimality(teacher,model):
            raise GroundRefused('restored model fails independent behavioral conformance')
    return model

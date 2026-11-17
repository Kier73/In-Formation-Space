"""COG-006: evidence-compiled cognition as typed structure, not generated code.

Small PyBot-inspired target: acquire a *relation-composition program* from
witnessed examples; compile it through a fixed typed operator grammar; retain
only task-relevant conversation context; replay a complete turn ledger in a
fresh interpreter. Natural-language understanding, truth of external data,
authenticated observers and E-CPU Hypervisor execution are OUTSIDE this model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from hashlib import sha256
from typing import Any, Sequence
import json

SCHEMA = 'in-formation.cognitive-capability-ground/006'


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()


class GroundRefused(ValueError):
    pass


@dataclass(frozen=True)
class Fact:
    subject: str
    steps: tuple[int, ...]
    direct_minutes: int
    source: str

    def __post_init__(self):
        if (type(self.subject) is not str or not self.subject.isidentifier()
                or not self.subject or not 1 <= len(self.steps) <= 16
                or any(type(t) is not int or not 0 <= t <= 3600 for t in self.steps)
                or type(self.direct_minutes) is not int or not 0 <= self.direct_minutes <= 36000
                or type(self.source) is not str or not self.source):
            raise GroundRefused('invalid typed source fact')

    def document(self):
        return {'subject': self.subject, 'steps': list(self.steps),
                'direct_minutes': self.direct_minutes, 'source': self.source}


@dataclass(frozen=True)
class FactGround:
    facts: tuple[Fact, ...]
    _index: dict[str, Fact] = field(init=False, repr=False, compare=False)
    _root: str = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not (1 <= len(self.facts) <= 100_000):
            raise GroundRefused('bounded finite evidence universe required')
        names = tuple(f.subject for f in self.facts)
        if names != tuple(sorted(set(names))):
            raise GroundRefused('noncanonical or duplicate subject registry')
        object.__setattr__(self, '_index', {f.subject:f for f in self.facts})
        object.__setattr__(self, '_root', digest({'schema':SCHEMA, 'facts':[f.document() for f in self.facts]}))

    @property
    def root(self) -> str:
        return self._root

    def record(self, subject: str) -> Fact:
        if subject not in self._index:
            raise GroundRefused('source fact unknown')
        return self._index[subject]


@dataclass(frozen=True)
class Operator:
    name: str
    domain: str
    codomain: str
    semantic: str
    cost: int


# The operators are a small *interpreter vocabulary*. New capabilities are
# graphs of these operators, represented as DATA and selected by evidence.
OPS = (
    Operator('direct', 'entity', 'minutes', 'read_direct', 1),
    Operator('steps', 'entity', 'step_list', 'follow_steps', 1),
    Operator('first', 'step_list', 'step', 'first_step', 1),
    Operator('first_minutes', 'step', 'minutes', 'read_step', 1),
    Operator('sum', 'step_list', 'minutes', 'sum_steps', 1),
    Operator('seconds', 'minutes', 'seconds', 'multiply_60', 1),
)
OPMAP = {op.name:op for op in OPS}


@dataclass(frozen=True)
class Program:
    operators: tuple[str, ...]
    goal: str

    def __post_init__(self):
        if self.goal not in ('minutes','seconds') or not (1<=len(self.operators)<=6):
            raise GroundRefused('invalid goal or program depth')
        current='entity'
        for name in self.operators:
            op=OPMAP.get(name)
            if op is None or op.domain != current:
                raise GroundRefused('program cannot be typed or contains unknown operator')
            current=op.codomain
        if current!=self.goal:
            raise GroundRefused('program target type mismatch')

    @property
    def root(self):
        return digest({'schema':SCHEMA,'goal':self.goal,'operators':list(self.operators)})

    @property
    def cost(self):
        return sum(OPMAP[name].cost for name in self.operators)


def enumerate_programs(goal: str = 'minutes') -> tuple[Program, ...]:
    """Compile candidate capability paths from the typed operator graph."""
    if goal not in ('minutes','seconds'):
        raise GroundRefused('unsupported intention type')
    pending=deque([('entity',())]); found=[]
    while pending:
        state,path=pending.popleft()
        if state==goal:
            found.append(Program(path,goal))
            continue
        if len(path)>=6:
            continue
        for op in OPS:
            if op.domain==state:
                pending.append((op.codomain,path+(op.name,)))
    return tuple(sorted(found,key=lambda p:(p.cost,p.operators)))


def realize(ground: FactGround, program: Program, subject: str) -> tuple[int, tuple[str, ...]]:
    """A selected path only visits the demanded source fact and operations."""
    fact=ground.record(subject)
    value: Any=fact
    for name in program.operators:
        if name=='direct': value=fact.direct_minutes
        elif name=='steps': value=fact.steps
        elif name=='first': value=value[0]
        elif name=='first_minutes': value=value  # already a typed step duration
        elif name=='sum': value=sum(value)
        elif name=='seconds': value=value*60
        else: raise GroundRefused('unsupported operator')
    if type(value) is not int:
        raise GroundRefused('non-integer realization')
    return value,(fact.source,)


@dataclass(frozen=True)
class Example:
    index: int
    previous: str
    subject: str
    expected: int
    root: str

    def document(self):
        return {'index':self.index,'previous':self.previous,'subject':self.subject,
                'expected':self.expected,'root':self.root}


@dataclass(frozen=True)
class Learner:
    ground: FactGround
    examples: tuple[Example,...] = ()

    @property
    def genesis(self):
        return digest({'schema':SCHEMA,'kind':'capability-learning','ground':self.ground.root})

    @property
    def head(self):
        return self.examples[-1].root if self.examples else self.genesis

    @property
    def viable(self):
        candidates=enumerate_programs('minutes')
        return tuple(program for program in candidates if all(
            realize(self.ground,program,e.subject)[0]==e.expected for e in self.examples))

    @property
    def promoted(self) -> Program:
        if len(self.viable)!=1:
            raise GroundRefused('capability not uniquely explained by current evidence')
        return self.viable[0]

    def admit(self, subject: str, expected: int) -> 'Learner':
        if type(expected) is not int or expected<0 or subject in (e.subject for e in self.examples):
            raise GroundRefused('invalid or duplicate training observation')
        self.ground.record(subject)
        row={'schema':SCHEMA,'index':len(self.examples),'previous':self.head,
             'ground':self.ground.root,'subject':subject,'expected':expected}
        example=Example(len(self.examples),self.head,subject,expected,digest(row))
        nxt=Learner(self.ground,self.examples+(example,))
        if not nxt.viable:
            raise GroundRefused('observations contradict all typed capability structures')
        return nxt

    def acquire(self, pool: Sequence[str]) -> str:
        """Choose a source subject maximizing disagreement among viable plans."""
        if len(pool)>2048 or not pool:
            raise GroundRefused('invalid bounded acquisition pool')
        known={e.subject for e in self.examples}
        ranked=[]
        for subject in pool:
            if subject in known: continue
            votes=[realize(self.ground,p,subject)[0] for p in self.viable]
            disagreement=sum(int(a!=b) for i,a in enumerate(votes) for b in votes[i+1:])
            ranked.append((-disagreement,subject))
        if not ranked:
            raise GroundRefused('no unobserved acquisition target')
        return min(ranked)[1]

    def document(self):
        return {'schema':SCHEMA,'ground':self.ground.root,
                'examples':[x.document() for x in self.examples],
                'head':self.head,'viable':[p.root for p in self.viable]}

    @classmethod
    def restore(cls, ground: FactGround, document: dict, *, external_head: str) -> 'Learner':
        if not isinstance(document,dict) or set(document)!={'schema','ground','examples','head','viable'}:
            raise GroundRefused('malformed learning Ground')
        if document['schema']!=SCHEMA or document['ground']!=ground.root:
            raise GroundRefused('learning source Ground changed')
        state=cls(ground)
        if not isinstance(document['examples'],list):
            raise GroundRefused('learning events malformed')
        for saved in document['examples']:
            if not isinstance(saved,dict): raise GroundRefused('malformed learning example')
            subject=saved.get('subject'); expected=saved.get('expected')
            state=state.admit(subject,expected)
            if state.examples[-1].document()!=saved:
                raise GroundRefused('learning lineage recomputation mismatch')
        if canonical(state.document()) != canonical(document) or state.head!=external_head:
            raise GroundRefused('changed, rolled back or stale learning evidence')
        return state


@dataclass(frozen=True)
class Turn:
    index: int
    previous: str
    kind: str
    payload: str | None
    answer: dict[str, Any]
    root: str

    def document(self):
        return {'index':self.index,'previous':self.previous,'kind':self.kind,
                'payload':self.payload,'answer':self.answer,'root':self.root}


@dataclass(frozen=True)
class Session:
    learner: Learner
    turns: tuple[Turn,...] = ()
    anchor: str | None = None

    @property
    def genesis(self):
        return digest({'schema':SCHEMA,'kind':'conversation','source':self.learner.ground.root,
                       'capability':self.learner.promoted.root,'training':self.learner.head})

    @property
    def head(self):
        return self.turns[-1].root if self.turns else self.genesis

    def perform(self, kind: str, payload: str | None = None) -> 'Session':
        if kind not in ('mention','ask_minutes','ask_seconds','clear'):
            raise GroundRefused('unknown typed intention')
        anchor=self.anchor
        if kind=='mention':
            if type(payload) is not str: raise GroundRefused('mention needs a subject')
            self.learner.ground.record(payload)
            anchor=payload
            answer={'status':'observed','active_subject':payload}
        elif kind=='clear':
            if payload is not None: raise GroundRefused('clear does not accept payload')
            anchor=None;answer={'status':'cleared'}
        else:
            if payload is not None: raise GroundRefused('follow-up must use retained reference')
            if anchor is None:
                answer={'status':'unresolved','reason':'no_prior_referent'}
            else:
                root=self.learner.promoted.root
                program=(self.learner.promoted if kind=='ask_minutes'
                         else Program(self.learner.promoted.operators+('seconds',),'seconds'))
                value, sources=realize(self.learner.ground,program,anchor)
                answer={'status':'verified_within_ground','value':value,
                        'unit':'minutes' if kind=='ask_minutes' else 'seconds',
                        'subject':anchor,'program':program.root,'basis_program':root,
                        'source_evidence':list(sources)}
        core={'schema':SCHEMA,'index':len(self.turns),'previous':self.head,'kind':kind,
              'payload':payload,'answer':answer,'source_root':self.learner.ground.root,
              'learning_head':self.learner.head}
        turn=Turn(len(self.turns),self.head,kind,payload,answer,digest(core))
        return Session(self.learner,self.turns+(turn,),anchor)

    def document(self):
        return {'schema':SCHEMA,'source_root':self.learner.ground.root,
                'learning_head':self.learner.head,'capability':self.learner.promoted.root,
                'turns':[t.document() for t in self.turns], 'head':self.head,
                'anchor':self.anchor}

    @classmethod
    def restore(cls,learner: Learner,doc: dict,*,external_head: str) -> 'Session':
        if not isinstance(doc,dict) or set(doc)!={'schema','source_root','learning_head','capability','turns','head','anchor'}:
            raise GroundRefused('malformed conversation checkpoint')
        if (doc['schema']!=SCHEMA or doc['source_root']!=learner.ground.root
                or doc['learning_head']!=learner.head or doc['capability']!=learner.promoted.root
                or not isinstance(doc['turns'],list)):
            raise GroundRefused('conversation bound to different admitted Grounds')
        state=cls(learner)
        for record in doc['turns']:
            if not isinstance(record,dict): raise GroundRefused('invalid turn record')
            state=state.perform(record.get('kind'),record.get('payload'))
            if state.turns[-1].document()!=record:
                raise GroundRefused('semantic event or chain changed')
        if canonical(state.document())!=canonical(doc) or state.head!=external_head:
            raise GroundRefused('stale or rewritten conversation history')
        return state


def fixture(size:int=128) -> FactGround:
    """Synthetic task corpus. Do not interpret algorithmic durations as real facts."""
    if type(size) is not int or not 1<=size<=100_000:
        raise GroundRefused('invalid synthetic corpus size')
    facts=[]
    for i in range(size):
        steps=tuple(1+((i*7+j*3)%11) for j in range(3))
        total=sum(steps)
        direct=total if i%7==0 else steps[0]
        facts.append(Fact(f'procedure_{i:06d}',steps,direct,f'synthetic-case-{i:06d}'))
    return FactGround(tuple(facts))

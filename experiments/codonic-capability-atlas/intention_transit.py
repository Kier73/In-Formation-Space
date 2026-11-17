"""COG-010: intention-conditioned navigation of an existing learned Ground.

No new authority, learner, or transport. The cognitive transition system comes
from COG-007/008/009; E-CPU IOS-001 is invoked when installed, and the native
law_certifier's fgraph law is used when installed. COG-009 signed stdio witnesses
are locally scoped research observations, not E-CPU mTLS, Hypervisor or M3.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, Sequence
from cognitive_grounds import GroundRefused, canonical, digest
from predictive_state import Machine, UNKNOWN

SCHEMA = 'ifs.cog010.intention-transit.v1'
COST_SCHEMA = SCHEMA+'.cost'


def require(condition:bool, message:str)->None:
    if not condition: raise GroundRefused(message)


def output(machine:Machine, state:int, action:str)->list[Any]:
    require(action in machine.alphabet, 'intention action not in admitted Ground')
    o, _ = machine.run_from(state,(action,))
    return list(o[0])


@dataclass(frozen=True)
class CognitiveProjection:
    """One bounded, source-pinned exact finite model of existing cognitive behavior.

    This is a projection, NOT a source truth claim or a newly learned law.
    """
    machine: Machine
    intention: str
    public_contract: str = 'anchored-vs-empty-v1'

    def __post_init__(self):
        require(self.intention in {'has_anchor','minutes','seconds','repeat'},'unsupported intention')
        require(len(self.machine.representatives)<=256,'E-CPU IOS-001 finite model capacity exceeded')
        require('minutes' in self.machine.alphabet and 'seconds' in self.machine.alphabet and 'repeat' in self.machine.alphabet,
                'required semantic operators absent from learned Ground')

    def public(self,state:int)->str:
        return 'empty' if output(self.machine,state,'minutes')==list(UNKNOWN) else 'anchored'

    def target(self,state:int)->Any:
        if self.intention=='has_anchor':return self.public(state)=='anchored'
        return output(self.machine,state,self.intention)

    def feature(self,state:int, feature:str)->Any:
        require(feature in ('minutes','repeat'),'unknown measurement feature')
        return output(self.machine,state,feature)

    def model_rows(self)->tuple[dict,...]:
        return tuple({'state_id':f's{state:04d}', 'public':self.public(state),
                      'target':self.target(state),
                      'features':{'minutes':self.feature(state,'minutes'),
                                  'repeat':self.feature(state,'repeat')}}
                     for state in range(len(self.machine.representatives)))

    @property
    def contract_digest(self)->str:
        return digest({'schema':SCHEMA,'projection':'model','machine':self.machine.fingerprint,
                       'source_root':self.machine.source_root,'intention':self.intention,
                       'public_contract':self.public_contract})

    def native_descriptors(self)->tuple[Any,Any,Any,Any]:
        """Re-use E-CPU's actual typed semantic identifiers and projections."""
        from mailcpu.semantic_translation import RepresentationRef,ObservationContract
        subject=RepresentationRef.from_payload('cog010.cognitive.subject',1,
                    {'source_root':self.machine.source_root,'machine':self.machine.fingerprint})
        ground=RepresentationRef.from_payload('cog010.cognitive.ground',1,
                    {'source_root':self.machine.source_root,'machine':self.machine.fingerprint,
                     'meaning':'evidence-scoped-predictive-state-machine'})
        public=ObservationContract.from_definition('cog010.public',1,
                    {'projection':self.public_contract})
        target=ObservationContract.from_definition('cog010.target',1,
                    {'intention':self.intention,'source':self.machine.fingerprint})
        return subject,ground,public,target

    def native_observer_contract(self, feature:str)->Any:
        """Construct a genuine IOS-002/003-compatible ObserverContract."""
        from mailcpu.observer_orbit import ObserverContract
        from mailcpu.semantic_translation import ObservationContract
        require(feature in ('minutes','repeat'),'unknown native observer projection')
        subject,ground,_,_=self.native_descriptors()
        observable=ObservationContract.from_definition(feature,1,
                     {'operation':feature,'machine':self.machine.fingerprint})
        return ObserverContract('observer.cog010.'+feature,1,subject,ground,
                                observable,self.contract_digest)

    def native(self)->Any:
        """Use real E-CPU IOS-001 types. No application-level planner substitute."""
        from mailcpu.intention_sufficiency import FiniteGround,FiniteState
        _,ground,public,target=self.native_descriptors()
        rows=tuple(FiniteState.create(r['state_id'],r['public'],r['target'],r['features'])
                   for r in self.model_rows())
        return FiniteGround(ground.content_digest,
                            public.projection_digest,
                            target.projection_digest,
                            self.contract_digest,rows)


class Planner(Protocol):
    def plan(self,projection:CognitiveProjection, public:str, features:tuple[str,...])->Mapping[str,Any]: ...
    def resolve(self,projection:CognitiveProjection, public:str, features:tuple[str,...],
                plan:Mapping[str,Any], measured:Mapping[str,Any],receipt_digest:str|None)->Mapping[str,Any]: ...


class NativeIOSPlanner:
    """Use E-CPU's IOS-001 exact minimization and native resolution unchanged."""
    def __init__(self,authority_digest:str, provider:str='cog009-signed-provisional',
                 native_contracts:Mapping[str,Any]|None=None):
        require(len(authority_digest)==64 and all(c in '0123456789abcdef' for c in authority_digest),
                'receiver authority fingerprint required')
        self.authority_digest=authority_digest;self.provider=provider
        self.native_contracts=dict(native_contracts or {})

    def offers(self, projection:CognitiveProjection,features:tuple[str,...])->tuple[Any,...]:
        from mailcpu.intention_sufficiency import MeasurementCapability
        require(len(set(features))==len(features),'duplicate feature offer')
        offers=[]
        for name in features:
            if name in self.native_contracts:
                c=self.native_contracts[name]
                require(c==projection.native_observer_contract(name),'stale native observer contract')
                offers.append(MeasurementCapability(name,c.digest,c.observer_id,
                                                    1 if name=='minutes' else 3))
            else:
                offers.append(MeasurementCapability(name,
                       digest({'schema':SCHEMA,'feature':name,'model':projection.contract_digest}),
                       self.provider, 1 if name=='minutes' else 3))
        return tuple(offers)

    def plan(self,projection:CognitiveProjection,public:str,features:tuple[str,...])->Mapping[str,Any]:
        from mailcpu.intention_sufficiency import plan_sufficiency,verify_sufficiency_plan
        model=projection.native();offers=self.offers(projection,features)
        result=plan_sufficiency(model,public,offers,self.authority_digest)
        verify_sufficiency_plan(result,model,public,offers,self.authority_digest)
        return result

    def resolve(self,projection:CognitiveProjection,public:str,features:tuple[str,...],
                plan:Mapping[str,Any],measured:Mapping[str,Any],receipt_digest:str|None)->Mapping[str,Any]:
        from mailcpu.intention_sufficiency import resolve_sufficiency,verify_sufficiency_resolution
        model=projection.native();offers=self.offers(projection,features)
        result=resolve_sufficiency(model,public,offers,self.authority_digest,dict(plan),dict(measured),receipt_digest)
        verify_sufficiency_resolution(result,model,public,offers,self.authority_digest,
                                      dict(plan),dict(measured),receipt_digest)
        return result


class SignedFeatureReader:
    """Provisional signed-C0G009 adapter; NOT a native IOS-002 ObserverReceipt.

    The provider owns the hidden context path. Source signatures and distinct
    enrolled-key agreement are checked by SignedFabric.query. A receiver may
    use this only under its separately configured experimental admission policy.
    """
    def __init__(self,machine:Machine,fabric:Any,hidden_path:Sequence[str]):
        self.machine=machine;self.fabric=fabric
        require(machine.source_root==fabric.source_root,'wrong authenticated source roster/epoch')
        self._hidden=tuple(hidden_path)
        # The hidden context is provider-owned. Validate its *language* only;
        # do not navigate it here to compute or pre-approve a measurement.
        require(len(self._hidden)<=63 and all(a in machine.alphabet for a in self._hidden),
                'hidden source path outside admitted action grammar')
        self.measurement_calls=0
        self.used_receipts=[]

    def read(self, feature:str)->tuple[Any,str]:
        require(feature in ('minutes','repeat'),'unsupported feature')
        path=self._hidden+(feature,)
        before=self.fabric.external_calls
        observed=self.fabric.query(path)
        # The output projection is individually bound to exactly this Ground,
        # context, operation and current pinned signed predecessor chain.
        # Only the enrolled and independently signature-verified source votes
        # establish this *reported* reading. IOS-001 will reject values that
        # cannot belong to the admitted finite model. A possible-but-false
        # signed answer remains a documented trust vulnerability, not truth.
        self.measurement_calls+=1
        proof={'schema':SCHEMA+'.signed-provisional','source_root':self.fabric.source_root,
               'machine':self.machine.fingerprint,'feature':feature,
               'path_digest':digest(list(path)),'output':list(observed[-1]),
               'fabric_head':self.fabric.head,'additional_host_exchanges':self.fabric.external_calls-before}
        proof['digest']=digest(proof)
        self.used_receipts.append(proof)
        return list(observed[-1]),proof['digest']


def execute_intention(projection:CognitiveProjection,public:str,planner:Planner,
                      *,features:tuple[str,...]=('minutes',), reader:SignedFeatureReader|None=None)->dict:
    """E-CPU intention gate, with measurement dispatch only if the plan demands it.

    E-CPU native backend is passed as planner; tests may use a *test-only*
    independent reference backend, which does not confer operational authority.
    """
    require(public in ('anchored','empty'),'unsupported public cognitive observation')
    require(all(f in ('minutes','repeat') for f in features),'unknown offered feature')
    plan=planner.plan(projection,public,features)
    require(plan['status'] in ('READY','MEASURE','REFUSE'),'invalid IOS status')
    selected=tuple(plan['selected_features'])
    before=reader.fabric.external_calls if reader is not None else 0
    if plan['status']=='REFUSE':
        require(not selected,'REFUSE must not request features')
        return {'schema':SCHEMA+'.result','status':'REFUSE','intention':projection.intention,
                'machine_digest':projection.machine.fingerprint,'plan_digest':plan['plan_digest'],
                'result':None,'selected':[],'additional_host_exchanges':0,
                'measurement_receipts':[],'finite_scope':True}
    if plan['status']=='READY':
        require(not selected,'READY cannot request features')
    else:
        require(reader is not None,'MEASURE requires qualified evidence provider')
        require(reader.machine.fingerprint==projection.machine.fingerprint,'changed source Ground')
    measurements={};proofs=[]
    for f in selected:
        value,proof=reader.read(f)
        measurements[f]=value
        # Bind the entire typed research evidence envelope into the result,
        # not only an opaque digest of it. SignedFabric retains the raw receipts.
        proofs.append(dict(reader.used_receipts[-1]))
    receipt_digest=digest({'proofs':proofs,'schema':SCHEMA+'.accepted-provisional'}) if proofs else None
    resolved=planner.resolve(projection,public,features,plan,measurements,receipt_digest)
    status='RESOLVED_WITHOUT_MEASUREMENT' if not selected else 'RESOLVED_AFTER_MEASUREMENT'
    require(resolved['status']==status,'IOS resolution status changed')
    return {'schema':SCHEMA+'.result','status':status,'intention':projection.intention,
            'machine_digest':projection.machine.fingerprint,'plan_digest':plan['plan_digest'],
            'result':resolved['result'],'selected':list(selected),
            'additional_host_exchanges':(reader.fabric.external_calls-before if reader is not None else 0),
            'measurement_receipts':proofs,
            'resolution_digest':resolved['resolution_digest'],'finite_scope':True}


@dataclass(frozen=True)
class FiniteCognitiveOrbit:
    """Reachable product orbit (learned cognitive state, program phase).

    Certified by exhaustive traversal of the reachable finite product cycle,
    not by finite examples of an arbitrary external machine. The E-CPU fgraph
    law consumes this *already checked* structural description.
    """
    machine: Machine
    program: tuple[str,...]
    starting_state:int
    states:tuple[int,...]
    mu:int
    period:int

    @classmethod
    def compile(cls,machine:Machine,program:Sequence[str],starting_state:int=0)->'FiniteCognitiveOrbit':
        program=tuple(program)
        require(program and len(program)<=32 and len(set(machine.alphabet))==len(machine.alphabet),
                'invalid bounded orbit program')
        require(all(op in machine.alphabet for op in program),'orbit program not in cognitive Ground')
        require(type(starting_state) is int and 0<=starting_state<len(machine.representatives),
                'orbit initial state invalid')
        size=len(machine.representatives)*len(program)
        index={word:i for i,word in enumerate(machine.alphabet)}
        state=starting_state;phase=0;seen={};states=[]
        while (state,phase) not in seen:
            require(len(states)<size,'orbit exceeds finite product state count')
            seen[(state,phase)]=len(states)
            states.append(state*len(program)+phase)
            action=program[phase]
            state=machine.transitions[state][index[action]]
            phase=(phase+1)%len(program)
        mu=seen[(state,phase)]
        lam=len(states)-mu
        require(lam>0,'invalid proven finite cycle')
        return cls(machine,program,starting_state,tuple(states),mu,lam)

    @property
    def digest(self)->str:
        return digest({'schema':SCHEMA+'.orbit','machine':self.machine.fingerprint,
                       'source_root':self.machine.source_root,'program':list(self.program),
                       'initial':self.starting_state,'states':list(self.states),
                       'mu':self.mu,'period':self.period})

    def at(self,tick:int)->tuple[int,int]:
        """Constant-size reachable orbit lookup, no predecessor enumeration."""
        require(type(tick) is int and tick>=0,'nonnegative logical coordinate required')
        pos=tick if tick<self.mu else self.mu+(tick-self.mu)%self.period
        encoded=self.states[pos];return divmod(encoded,len(self.program))

    def native_at(self,tick:int)->tuple[int,int]:
        """Actual E-CPU fgraph navigator, with independently checked profile."""
        from mailcpu.law_certifier import Law,navigate_guarded
        law=Law('fgraph',{'orbit':list(self.states),'mu':self.mu,'lam':self.period},
                verdict='GROUND')
        encoded=navigate_guarded(law,tick)
        require(encoded==self.at(tick)[0]*len(self.program)+self.at(tick)[1],
                'native E-CPU disagrees with separately derived orbit')
        return divmod(encoded,len(self.program))

    def independent_validate(self)->bool:
        # Independently traverse every finite reachable product state and its
        # unique successor, including the final closing arc.
        k=len(self.program);idx={a:i for i,a in enumerate(self.machine.alphabet)}
        seen=set();links={};state=self.starting_state;phase=0
        while (state,phase) not in seen:
            seen.add((state,phase))
            code=state*k+phase
            action=self.program[phase]
            nxt=(self.machine.transitions[state][idx[action]],(phase+1)%k)
            links[code]=nxt
            state,phase=nxt
        require(len(seen)==len(self.states),'missing orbit states')
        for step,code in enumerate(self.states):
            s,p=divmod(code,k)
            require((s,p) in seen and links[code]==self.at(step+1),'orbit semantic transition mismatch')
        require(self.at(10**30+11)==self.at(self.mu+(10**30+11-self.mu)%self.period),
                'large time navigation mismatch')
        return True

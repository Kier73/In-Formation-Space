"""CIG-016: proof-directed, counted refinement using existing CIG Grounds.

A positive admitted fiber carries a representative. Prove/count only the
opposite branch; the complementary count follows by conservation.
"""
from collections import Counter
from time import perf_counter_ns
from composed_ground import canonical, compile_ground
from heavy_ground import dpll, normalize
from verify_proof_refinement import Receiver, MAX_FIBERS, MAX_PREDICATES


def truth(row,state):
    return int(any(bool(state & (1<<(abs(l)-1)))==(l>0) for l in row))


def obligation(source,predicates,k,f,opposite):
    rows=list(source)
    for i,p in enumerate(predicates):
        rows.extend([p] if k>>i&1 else [(-l,) for l in p])
    rows.extend([f] if opposite else [(-l,) for l in f])
    return rows


class ProofLanguage:
    def __init__(self,n,source,*,width=12,cells=2_000_000):
        self.receiver=Receiver(n,source);self.n=n;self.source=tuple(canonical(source,n));self.stats=Counter()
        if self._count(self.source,width,cells) is None:raise OverflowError('base count not admitted')
        self.receiver.seed()

    def snapshot(self):return self.receiver.snapshot()

    def _admit(self,rows,route,packet,**kw):
        t=perf_counter_ns();result=self.receiver.admit(rows,route,packet,**kw);self.stats['verify_ns']+=perf_counter_ns()-t
        self.stats['verified_proofs']+=1;return result

    def _count(self,rows,width,cells):
        old=self.receiver.lookup(rows)
        if old is not None and old[1] is not None:
            self.stats['count_hits']+=1;return old
        t=perf_counter_ns();self.stats['count_attempts']+=1
        p=compile_ground(rows,self.n,max_width=width,max_cells=cells)
        self.stats['count_ns']+=perf_counter_ns()-t
        if p['status']=='UNKNOWN':self.stats['count_unknown']+=1;return old
        self.stats['factor_cells']+=p['cells'];self.stats['projection_row_visits']+=p['projection_row_visits']
        return self._admit(rows,'count',p,width=width,cells=cells)

    def _decide(self,rows,nodes,seconds):
        old=self.receiver.lookup(rows)
        if old is not None:self.stats['decision_hits']+=1;return old
        if not nodes:return None
        # Existing bounded DPLL is qualified only for its original source domain.
        try:source=normalize(rows,self.n)
        except ValueError:return None
        t=perf_counter_ns();self.stats['decision_attempts']+=1
        p=dpll(source,self.n,'SAT',max_nodes=nodes,seconds=seconds)
        self.stats['decision_ns']+=perf_counter_ns()-t;self.stats['dpll_nodes']+=p['nodes'];self.stats['dpll_literal_checks']+=p['literal_checks']
        if p['status']=='UNKNOWN':self.stats['decision_unknown']+=1;return None
        return self._admit(rows,'decision',p)

    def extend(self,row,*,width=12,cells=2_000_000,nodes=8,seconds=.1):
        if type(nodes) is not int or not 0<=nodes<=100000 or not 0<seconds<=60:raise ValueError('budget')
        f=tuple(row);p,old=self.snapshot()
        if not f or canonical([f],self.n)!=[f] or f in p or len(p)>=MAX_PREDICATES:raise ValueError('invalid new predicate')
        w=len(p);new={};records={}
        for k,(total,model) in sorted(old.items()):
            b=truth(f,model);rows=obligation(self.source,p,k,f,1-b)
            known=self._decide(rows,nodes,seconds)
            if known is None or known[1] is None:
                known=self._count(rows,width,cells)
            if known is None:records[k]='UNRESOLVED';continue
            status,count,other=known
            if status=='UNSAT':records[k]='DECODE';new[k|(b<<w)]=(total,model)
            elif count is None:records[k]='SPLIT_UNCOUNTED'
            else:
                records[k]='REFINE';new[k|(b<<w)]=(total-count,model);new[k|((1-b)<<w)]=(count,other)
        complete=all(t in ('DECODE','REFINE') for t in records.values()) and len(new)<=MAX_FIBERS
        t=perf_counter_ns();result=self.receiver.check(f,records,new if complete else None);self.stats['refinement_check_ns']+=perf_counter_ns()-t
        self.stats.update(records.values());self.stats['extension_attempts']+=1
        return result

    def query(self,additions):
        """Reuse the actual CIG-014 signed-union interface and checker.

        Counts are from receiver-admitted fibers, not from an external seed.
        No new proof search or count compilation is performed on a cover hit.
        """
        from nonlinear_sufficient import plan,translate
        from verify_nonlinear_sufficient import check_translation
        from regional_memory import identity
        from verify_composed_ground import accepted
        p,fibers=self.snapshot();rows=canonical([*self.source,*additions],self.n)
        d=dict(schema='ifs.cig014.predicate-fiber.v1',n=self.n,scope=list(range(1,self.n+1)),source=[list(c) for c in self.source],visible=[],predicates=[list(c) for c in p])
        seed=dict(descriptor=d,key=identity(d),bins=[[k,str(c)] for k,(c,_) in sorted(fibers.items())],bits=max(0,len(fibers)-1).bit_length())
        desc=dict(version='ifs.cig010.adaptive.v1',scope=d['scope'],clauses=[list(c) for c in rows],boundary=[])
        cover=plan(seed,desc)
        if cover is None:return {'status':'UNRESOLVED'}
        msg=translate(seed,desc,cover)
        if not check_translation(self.n,seed,desc,cover,msg):raise ValueError('retained query failed')
        count=int(msg['counts'][0]);witness=next((w for _,w in fibers.values() if accepted(rows,w)),None)
        if bool(count)!=(witness is not None):raise ValueError('retained query witness mismatch')
        self.stats['query_bins']+=len(fibers);self.stats['query_hits']+=1
        return dict(status='SAT' if count else 'UNSAT',count=str(count),witness=str(witness) if count else None)

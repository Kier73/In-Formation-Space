"""CIG-016 receiver: source-bound proof admission and independent refinement.

Receipts are checked using existing CIG-006 and CIG-008 independent checkers.
A decision witness is never a count. The receiver owns its admitted archive;
external callers cannot bootstrap it by supplying a claimed old histogram.
"""
from collections import Counter
from copy import deepcopy
from verify_composed_ground import normal, accepted, verify as check_count
from verify_heavy_ground import _source, _check_solver_result

MAX_FIBERS=4096
MAX_PREDICATES=32


def bit_value(clause, model):
    return int(any((model//2**(abs(l)-1))%2 == int(l>0) for l in clause))


def strict_count(value):
    if type(value) is not str or not value.isascii() or not value.isdecimal() or str(int(value))!=value:
        raise ValueError('noncanonical count')
    return int(value)


def signature(predicates, model):
    return sum(bit_value(row,model)*2**j for j,row in enumerate(predicates))


def key_for(n, source):
    return n,tuple(normal(source,n))


def predicate(n,row):
    if type(row) not in (list,tuple) or not row or normal([row],n)!=[tuple(row)]:
        raise ValueError('expected canonical nonempty predicate clause')
    return tuple(row)


class Receiver:
    """Trusted local verification boundary, not a network authority service."""
    def __init__(self,n,source):
        self.n=n; self.source=key_for(n,source)[1]; self._proofs={};self._predicates=();self._fibers=None
        self.stats=Counter()

    def snapshot(self):
        if self._fibers is None:raise ValueError('seed not admitted')
        return self._predicates,dict(self._fibers)

    def lookup(self,source):
        return self._proofs.get(key_for(self.n,source))

    def admit(self,source,route,packet,*,width=12,cells=2_000_000):
        """Return (status, exact_count_or_None, witness_or_None)."""
        rows=key_for(self.n,source)[1]
        if route=='count':
            if not check_count(rows,self.n,packet,max_width=width,max_cells=cells):
                raise ValueError('invalid exact count proof')
            count=strict_count(packet['count']);status=packet['status']
        elif route=='decision':
            _check_solver_result(_source(rows,self.n),self.n,'SAT',packet)
            status=packet['status'];count=0 if status=='UNSAT' else None
            if packet.get('count') is not None:raise ValueError('decision count forgery')
        else:raise ValueError('invalid proof route')
        if status not in ('SAT','UNSAT'):raise ValueError('incomplete proof')
        witness=None
        if status=='SAT':
            witness=strict_count(packet['witness'])
            if witness>=2**self.n or not accepted(rows,witness):raise ValueError('invalid source witness')
            if count is not None and not 1<=count<=2**self.n:raise ValueError('invalid positive count')
        elif count!=0 or packet.get('witness') is not None:raise ValueError('invalid contradiction')
        result=(status,count,witness);k=(self.n,rows);old=self._proofs.get(k)
        if old is not None:
            if old[0]!=status or old[1] is not None and count is not None and old[1]!=count:raise ValueError('contradictory proof')
            if old[1] is not None:result=old
        self._proofs[k]=result;self.stats['admissions']+=1
        return result

    def seed(self):
        if self._fibers is not None:raise ValueError('already seeded')
        proof=self.lookup(self.source)
        if proof is None or proof[1] is None:raise ValueError('exact base count required')
        self._fibers={} if not proof[1] else {0:(proof[1],proof[2])}

    def check(self,row,records,claimed):
        """Independently reconstruct each obligation from the receiver's own state.
        Exact partial results do not change the admitted observation language.
        Records are labels; mathematical evidence is looked up by exact CNF.
        """
        p,old=self.snapshot(); f=predicate(self.n,row);w=len(p)
        if f in p or w>=MAX_PREDICATES or set(records)!=set(old) or any(type(k)is not int for k in records):raise ValueError('extension contract')
        new={};status={}
        for k,(total,model) in sorted(old.items()):
            if not accepted(self.source,model) or signature(p,model)!=k:raise ValueError('invalid retained witness')
            assumptions=list(self.source)
            for j,g in enumerate(p):
                if (k//2**j)%2:assumptions.append(g)
                else:assumptions.extend((-l,) for l in g)
            b=bit_value(f,model)
            assumptions.extend([f] if b==0 else [(-l,) for l in f])
            proof=self.lookup(assumptions)
            if proof is None:tag='UNRESOLVED'
            elif proof[0]=='UNSAT':
                tag='DECODE';new[k+b*2**w]=(total,model)
            else:
                other=proof[2]
                if signature(p,other)!=k or bit_value(f,other)==b:raise ValueError('false split witness')
                if proof[1] is None:tag='SPLIT_UNCOUNTED'
                else:
                    count=proof[1]
                    if not 0<count<total:raise ValueError('fiber conservation failed')
                    tag='REFINE';new[k+b*2**w]=(total-count,model);new[k+(1-b)*2**w]=(count,other)
            status[k]=tag
        if records!=status:raise ValueError('incorrect refinement status')
        complete=all(t in ('DECODE','REFINE') for t in status.values()) and len(new)<=MAX_FIBERS
        expected=new if complete else None
        if claimed!=expected or claimed is not None and any(type(k)is not int or type(c)is not int or type(m)is not int for k,(c,m) in claimed.items()):
            raise ValueError('incorrect refined histogram')
        if complete:
            assert sum(c for c,_ in new.values())==sum(c for c,_ in old.values())
            self._predicates=p+(f,);self._fibers=new
        return dict(complete=complete,status=status,old_fibers=len(old),new_fibers=len(new) if complete else None)

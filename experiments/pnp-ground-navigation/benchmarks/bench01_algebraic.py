"""BENCH-01H: exact Fourier-coordinate factorization of bounded strict 3-SAT.

The original clause-violation energy is expanded in Walsh characters over GF(2).
Disjoint LINEAR spans of nonconstant support sets are independent coordinates,
even when the original CNF variable incidence hypergraph is fully connected.
Each small-rank component is minimized exactly; its minimizer multiplicity
combines with an explicit 2^(n-total_rank) source-fibre factor for exact #SAT.

SFI/SPN native algebraic utilities are used when installed, and the result is
checked by an independent original-clause truth-table Fourier reconstruction.
No assumption that arbitrary CNF has small component ranks is made.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
import json
import sys

BASE=Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:sys.path.insert(0,str(BASE))
SPN=BASE/'spectral_phase_navigation'
if SPN.is_dir() and str(SPN) not in sys.path:sys.path.insert(0,str(SPN))
from morphic_sat import normalize

VERSION='ifs.bench01.fourier-coordinate-separator.v1'


def _canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')


def _digest(obj):
    return sha256(_canonical(obj)).hexdigest()


def _canonical_source(clauses,n):
    if type(n) is not int or not 3<=n<=128:
        raise ValueError('bounded source requires 3..128 variables')
    src=[list(x) for x in normalize(clauses,n)]
    if len(src)>4096 or any(len(c)!=3 or len({abs(x) for x in c})!=3 for c in src):
        raise ValueError('this exact 8-scaled Fourier method requires three distinct literals per clause')
    return src


def _coefficients(clauses):
    """Producer: expand each forbidden assignment as product(1+sign*chi)/8."""
    coeff={}
    for clause in clauses:
        variables=[abs(t)-1 for t in clause]
        forbidden=[int(t<0) for t in clause]
        for selected in range(8):
            mask=0;sign=1
            for j,index in enumerate(variables):
                if selected>>j&1:
                    mask ^= 1<<index
                    if forbidden[j]:sign=-sign
            coeff[mask]=coeff.get(mask,0)+sign
    return {x:c for x,c in coeff.items() if c}


def _basis_coordinates(masks):
    """Native SPN-007 source-support coordinates, with a standalone fallback.

    The separate receipt verifier never trusts this coordinate producer and
    independently reconstructs every original parity mask.
    """
    try:
        from direct_sum_grounds import linear_coordinates
    except ImportError:
        pass
    else:
        basis,codes=linear_coordinates(masks)
        return list(basis),codes
    basis=[];pivots={};codes={}
    for mask in sorted(masks):
        residue,code=mask,0
        while residue:
            p=residue.bit_length()-1
            if p not in pivots:
                pos=len(basis)
                basis.append(mask)
                pivots[p]=(residue,code^(1<<pos))
                codes[mask]=1<<pos
                break
            old,oldcode=pivots[p];residue^=old;code^=oldcode
        else:
            codes[mask]=code
    for mask,code in codes.items():
        check=0
        for j,b in enumerate(basis):
            if code>>j&1:check^=b
        if check!=mask:raise AssertionError('incorrect source parity reconstruction')
    return basis,codes


def _support_components(supports):
    """Fundamental-circuit components; delegate to existing SPN-007 when present."""
    native=False
    try:
        from direct_sum_grounds import fundamental_components
    except ImportError:
        components=_fallback_fundamental_components(supports)
    else:
        components,_stats=fundamental_components(supports)
        components=[list(item) for item in components]
        native=True
    return components,native


def _fallback_fundamental_components(supports):
    """Offline research fallback for standalone workspaces lacking SPN-007.

    In the full IFS repository, direct_sum_grounds.fundamental_components is
    used instead. This fallback is not the independent proof verifier.
    """
    masks=sorted(set(supports));parent=list(range(len(masks)));pivots={}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        x,y=find(a),find(b)
        if x!=y:parent[max(x,y)]=min(x,y)
    for idx,mask in enumerate(masks):
        residue,expression=mask,1<<idx
        while residue:
            top=residue.bit_length()-1
            if top not in pivots:
                pivots[top]=(residue,expression)
                break
            row,trace=pivots[top]
            residue^=row;expression^=trace
        if residue==0:
            participants=[i for i in range(idx+1) if expression>>i&1]
            for p in participants[1:]:union(participants[0],p)
    groups={}
    for idx,mask in enumerate(masks):groups.setdefault(find(idx),[]).append(mask)
    return sorted(groups.values(),key=lambda x:x[0])


def _evaluate_component(terms,basis,code,max_rank):
    if len(basis)>max_rank:
        return None
    minima=None;ways=0;first=0
    for x in range(1<<len(basis)):
        energy=sum(coeff * (1 if not (coordinate & x).bit_count()%2 else -1)
                   for _mask,coeff,coordinate in terms)
        if minima is None or energy<minima:
            minima,ways,first=energy,1,x
        elif energy==minima:ways+=1
    return {'minimum':minima,'minimizers':ways,'first_coordinate':first,
            'coordinates_evaluated':1<<len(basis)}


def _solve_parity_requirements(pairs,n):
    """Find one source state inducing the requested parity-coordinate values."""
    pivots={}
    for mask,bit in pairs:
        v,par=mask,bit
        while v:
            p=v.bit_length()-1
            if p not in pivots:
                pivots[p]=(v,par)
                break
            old,oldbit=pivots[p];v^=old;par^=oldbit
        if v==0 and par:raise ValueError('inconsistent claimed independent coordinates')
    result=0
    for p in sorted(pivots):
        row,rhs=pivots[p]
        bit=rhs^((row&result).bit_count()%2)
        if bit:result|=1<<p
    return result


def _satisfies(src,witness):
    return all(any(((witness>>(abs(l)-1))&1)==int(l>0) for l in c) for c in src)


def build(clauses,n,*,max_rank=6,max_cells=4096):
    """Return complete SAT/#SAT evidence or UNKNOWN on any exceeded budget."""
    if type(max_rank) is not int or not 0<=max_rank<=16 or type(max_cells) is not int or not 1<=max_cells<=1<<16:
        raise ValueError('invalid finite coordinate budgets')
    start=perf_counter_ns()
    source=_canonical_source(clauses,n)
    coeff=_coefficients(source)
    supports=sorted(x for x in coeff if x)
    groups,native=_support_components(supports)
    plan=[];cells=0;unknown=False
    for masks in groups:
        basis,codes=_basis_coordinates(masks)
        row={'supports':masks,'basis':basis,
             'terms':[[mask,coeff[mask],codes[mask]] for mask in masks]}
        cells+=1<<len(basis)
        if len(basis)>max_rank or cells>max_cells:
            unknown=True
            row['minimum']=None;row['minimizers']=None;row['first_coordinate']=None
            row['coordinates_evaluated']=0
        else:
            row.update(_evaluate_component([(mask,coeff[mask],codes[mask]) for mask in masks],basis,codes,max_rank))
        plan.append(row)
    total_rank=sum(len(group['basis']) for group in plan)
    if unknown:
        status='UNKNOWN';count=None;minimum=None;witness=None
    else:
        minimum=coeff.get(0,0)+sum(group['minimum'] for group in plan)
        if minimum<0 or minimum%8:
            raise AssertionError('source clause energy cannot be negative or fractional')
        if minimum:
            status='UNSAT';count=0;witness=None
        else:
            status='SAT'
            count=(1<<(n-total_rank))
            parity_eqs=[]
            for group in plan:
                count*=group['minimizers']
                for i,mask in enumerate(group['basis']):
                    parity_eqs.append((mask,(group['first_coordinate']>>i)&1))
            witness=_solve_parity_requirements(parity_eqs,n)
            if not _satisfies(source,witness):
                raise AssertionError('Fourier-minimizing coordinate witness fails original CNF')
    result={'schema':VERSION,'source_sha256':_digest({'n':n,'clauses':source}),
            'n':n,'source_clauses':source,'scaled_eight_constant':coeff.get(0,0),
            'components':plan,'global_rank':total_rank,'minimum_scaled_eight':minimum,
            'status':status,'count':count,'witness_decimal':str(witness) if witness is not None else None,
            'budget':{'max_rank':max_rank,'max_cells':max_cells},
            'observation':{'construction_ms':round((perf_counter_ns()-start)/1e6,6),
                           'native_spn007_used':native}}
    result['digest']=_digest({k:v for k,v in result.items() if k!='digest'})
    return result


def _source_independent_coefficients(source):
    """Verifier: rederive each exact Walsh coefficient through 8 source truth assignments.

    Does not call the producer's forbidden-literal symbolic expansion.
    E(x) = sum violations; coefficients are 8*Ehat(S).
    """
    out={}
    for clause in source:
        positions=sorted(abs(l)-1 for l in clause)
        for choice in range(8):
            support=0
            for j,p in enumerate(positions):
                if choice>>j&1:support|=1<<p
            total=0
            for bits in range(8):
                values={p:(bits>>j)&1 for j,p in enumerate(positions)}
                violation=int(all(values[abs(l)-1]!=int(l>0) for l in clause))
                sign=(-1)**((choice&bits).bit_count()%2)
                total+=violation*sign
            out[support]=out.get(support,0)+total
    return {k:v for k,v in out.items() if v}


def _independent_rank(masks):
    echelon={}
    for mask in masks:
        x=mask
        while x:
            bit=x&-x
            if bit not in echelon:
                echelon[bit]=x;break
            x^=echelon[bit]
    return len(echelon)


def _independent_evaluation(source,components,coefficient,max_rank,max_cells):
    """Verifier: exact minima by direct parity characters and independent rank."""
    all_supports=set(coefficient)-{0}
    partition=[]
    for item in components:
        s=item.get('supports')
        if not isinstance(s,list) or not s or s!=sorted(set(s)):
            raise ValueError('missing, repeated or noncanonical Fourier supports')
        partition.extend(s)
    if len(partition)!=len(set(partition)) or set(partition)!=all_supports:
        raise ValueError('omitted or duplicated source Fourier term')
    total_rank=_independent_rank(partition)
    if sum(_independent_rank(item['supports']) for item in components)!=total_rank:
        raise ValueError('proposed components have dependent linear spans')
    visited=0;complete=True;minimum=coefficient.get(0,0);count=1;eqs=[]
    for item in components:
        supports=item['supports'];basis=item.get('basis')
        if not isinstance(basis,list) or len(basis)!=len(set(basis)) or any(x not in supports for x in basis):
            raise ValueError('unverified source-parity coordinate basis')
        r=_independent_rank(supports)
        if _independent_rank(basis)!=r or len(basis)!=r:
            raise ValueError('incorrect parity coordinate dimension')
        terms=item.get('terms')
        if not isinstance(terms,list) or len(terms)!=len(supports):
            raise ValueError('missing source-energy terms')
        declared={}
        for row in terms:
            if not isinstance(row,list) or len(row)!=3 or any(type(k) is not int for k in row):
                raise ValueError('invalid parity-coordinate term')
            mask,coef,code=row
            if mask in declared or coef!=coefficient.get(mask) or code<0 or code>=1<<r:
                raise ValueError('changed source Fourier coefficient')
            reconstruct=0
            for j,b in enumerate(basis):
                if code>>j&1:reconstruct^=b
            if reconstruct!=mask:
                raise ValueError('false coordinate reconstruction')
            declared[mask]=code
        if set(declared)!=set(supports):
            raise ValueError('not all source coefficient terms reconstructed')
        visited+=(1<<r)
        if r>max_rank or visited>max_cells:
            complete=False
            if any(item.get(k) is not None for k in ('minimum','minimizers','first_coordinate')) or item.get('coordinates_evaluated')!=0:
                raise ValueError('unqualified component is claiming a proved minimum')
            continue
        values=[]
        for x in range(1<<r):
            # use source mask -> parity via declared coordinate reconstruction
            val=sum(coefficient[s]*(1 if (declared[s]&x).bit_count()%2==0 else -1) for s in supports)
            values.append(val)
        m=min(values);ways=values.count(m);first=values.index(m)
        if any(item.get(k)!=v for k,v in [('minimum',m),('minimizers',ways),('first_coordinate',first),('coordinates_evaluated',1<<r)]):
            raise ValueError('component minimum / multiplicity is forged')
        minimum+=m;count*=ways
        for j,b in enumerate(basis):eqs.append((b,(first>>j)&1))
    return complete,minimum,count,total_rank,eqs


def verify(clauses,n,receipt):
    """Admit source-verified SAT/UNSAT/#SAT or an explicit finite-budget refusal.

    Intentionally ignores untrusted producer timing and native-util telemetry.
    """
    src=_canonical_source(clauses,n)
    if type(receipt) is not dict or receipt.get('schema')!=VERSION or receipt.get('n')!=n or receipt.get('source_clauses')!=src:
        raise ValueError('source identity or receipt schema invalid')
    if receipt.get('source_sha256')!=_digest({'n':n,'clauses':src}) or receipt.get('digest')!=_digest({k:v for k,v in receipt.items() if k!='digest'}):
        raise ValueError('tampered source receipt')
    budget=receipt.get('budget')
    if type(budget) is not dict or set(budget)!={'max_rank','max_cells'} or type(budget['max_rank']) is not int or not 0<=budget['max_rank']<=16 or type(budget['max_cells']) is not int or not 1<=budget['max_cells']<=1<<16:
        raise ValueError('invalid bounded computation contract')
    coeff=_source_independent_coefficients(src)
    if receipt.get('scaled_eight_constant')!=coeff.get(0,0):
        raise ValueError('changed source violation constant')
    components=receipt.get('components')
    if not isinstance(components,list) or len(components)>n*8:
        raise ValueError('invalid component record')
    complete,minimum,multiplicity,rank,eqs=_independent_evaluation(src,components,coeff,**budget)
    if rank!=receipt.get('global_rank'):
        raise ValueError('invalid global coordinate rank')
    if not complete:
        status,count,witness,total='UNKNOWN',None,None,None
    elif minimum>0:
        status,count,witness,total='UNSAT',0,None,minimum
    elif minimum==0:
        status='SAT';count=multiplicity*(1<<(n-rank));total=0
        witness=str(_solve_parity_requirements(eqs,n))
        if not _satisfies(src,int(witness)):
            raise ValueError('original CNF rejects minimizer witness')
    else:raise ValueError('negative exact source energy is mathematically impossible')
    if any(receipt.get(k)!=v for k,v in [('status',status),('count',count),('witness_decimal',witness),('minimum_scaled_eight',total)]):
        raise ValueError('false SAT/UNSAT or model count')
    return {'status':status,'count':count,'witness_decimal':witness,'source_verified':True,
            'global_rank':rank,'source_coefficient_count':len(coeff)}


def xor_three(a,b,c,rhs):
    """Encode x_a XOR x_b XOR x_c = rhs as four genuine 3-literal clauses."""
    if len({a,b,c})!=3 or rhs not in (0,1):raise ValueError('invalid 3-XOR source')
    out=[]
    for bits in range(8):
        if bits.bit_count()%2!=rhs:
            out.append(tuple(-v if bits>>j&1 else v for j,v in enumerate((a,b,c))))
    return out


def cycle_xor(n=19,*,unsat=False):
    """Every three consecutive original variables form an XOR observation.

    For 3∤n the circulant rows are linearly independent. Variable incidence
    stays connected with no one-vertex cut. If unsat, include an opposite
    observation on one scope, requiring all outputs of that pair to conflict.
    """
    if n<5 or n%3==0:raise ValueError('cycle dimension must not divide by three')
    rows=[]
    for i in range(n):
        variables=[(i+j)%n+1 for j in range(3)]
        rows+=xor_three(*variables,rhs=(i*7+3)%2)
    if unsat:rows+=xor_three(1,2,3,rhs=0) if (3%2) else xor_three(1,2,3,rhs=1)
    return rows

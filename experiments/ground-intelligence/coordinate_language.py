"""PGI-004: exact separable nonlinear CRT pullbacks, induced from paired cofactors.
Finite prefixes are copied (optionally complemented); maps act on periodic tails.
"""
from dataclasses import dataclass
from math import prod
from ground_network import View, Work, Exhausted, digest

@dataclass(frozen=True)
class CoordinateSkill:
    base: tuple
    maps: tuple
    flip: int = 0
    @property
    def key(self):
        return digest(['pgi.coordinate.v1',self.base,self.maps,self.flip])


def valid(skill):
    return (type(skill) is CoordinateSkill and type(skill.base) is tuple and
            type(skill.maps) is tuple and len(skill.base)==len(skill.maps) and
            type(skill.flip) is int and skill.flip in (0,1) and
            all(type(m) is int and 2<=m<=4096 and type(row) is tuple and len(row)==m and
                all(type(x) is int and 0<=x<m for x in row) for m,row in zip(skill.base,skill.maps)))


def compile_view(source,skill,*,max_work=500000):
    if type(source) is not View or not valid(skill) or source.base!=skill.base:raise ValueError('coordinate contract')
    w=Work(max_work);ids={0:skill.flip,1:1^skill.flip};nodes=[];unique={}
    for i,(j,kids) in enumerate(source.nodes,2):
        w.charge(len(kids)+1);ch=tuple(ids[kids[x]] for x in skill.maps[j])
        if len(set(ch))==1:ids[i]=ch[0];continue
        row=(j,ch)
        if row not in unique:unique[row]=len(nodes)+2;nodes.append(row)
        ids[i]=unique[row]
    pre=source.prefix^(((1<<source.cutoff)-1) if skill.flip else 0)
    return View('coordinate:'+digest([source.key,skill.key]),source.base,tuple(nodes),ids[source.root],source.cutoff,pre),w.used


def compose(first,second):
    """Apply first then second, both acting on the argument of the source."""
    if not valid(first) or not valid(second) or first.base!=second.base:raise ValueError('composition')
    return CoordinateSkill(first.base,tuple(tuple(a[x] for x in b) for a,b in zip(first.maps,second.maps)),first.flip^second.flip)


def discover(source,target,*,max_work=500000):
    """Complete for bijective coordinate maps within budget; no target history.
    Match equivalence classes of *joint* child vectors, then recurse. Equal
    remaining-domain counts prune candidates but never certify equivalence.
    """
    from verify_coordinate_language import verify_pullback
    w=Work(max_work);branches=0;backtracks=0
    if type(source) is not View or type(target) is not View or source.base!=target.base or source.cutoff!=target.cutoff:
        return None,dict(work=0,branches=0,backtracks=0,status='UNKNOWN')
    base=source.base;L=len(base);tails=[prod(base[j:]) for j in range(L+1)]
    def prepare(v):
        counts=[0,1];levels=[L,L]
        for j,ch in v.nodes:
            w.charge(len(ch)+1);counts.append(sum(counts[x]*(tails[j+1]//tails[levels[x]]) for x in ch));levels.append(j)
        return counts,levels
    def child(v,x,j,r):
        return v.nodes[x-2][1][r] if x>=2 and v.nodes[x-2][0]==j else x
    try:
        ac,al=prepare(source);bc,bl=prepare(target)
        def ncount(counts,levels,x,j):return counts[x]*(tails[j]//tails[levels[x]])
        def classes(v,pairs,j,side):
            rows={}
            for r in range(base[j]):
                w.charge(len(pairs)+1);key=tuple(child(v,p[side],j,r) for p in pairs)
                rows.setdefault(key,[]).append(r)
            return rows
        def solve(j,pairs,flip):
            nonlocal branches,backtracks
            w.charge(len(pairs)+1)
            for u,v in pairs:
                if ncount(ac,al,u,j)!=(tails[j]-ncount(bc,bl,v,j) if flip else ncount(bc,bl,v,j)):return None
            if j==L:return () if all(u^flip==v for u,v in pairs) else None
            aa=classes(source,pairs,j,0);bb=classes(target,pairs,j,1)
            if len(aa)!=len(bb):return None
            def sig(row,rs,counts,levels,complement):
                w.charge(len(row)+1);return (len(rs),tuple(tails[j+1]-ncount(counts,levels,x,j+1) if complement else ncount(counts,levels,x,j+1) for x in row))
            bins={}
            for row,rs in aa.items():bins.setdefault(sig(row,rs,ac,al,False),[]).append(row)
            choices=[]
            for row,rs in bb.items():
                options=bins.get(sig(row,rs,bc,bl,flip),[])
                if not options:return None
                choices.append((row,options))
            choices.sort(key=lambda p:len(p[1]));used=set();assign=[]
            # Explicit stack avoids recursion on large class counts.
            def match():
                idx=0;nexts=[0]*len(choices)
                while idx>=0:
                    w.charge()
                    if idx==len(choices):
                        yield tuple(assign);idx-=1
                        if idx>=0:used.remove(assign.pop()[1])
                        continue
                    row,opts=choices[idx]
                    if nexts[idx]>=len(opts):
                        nexts[idx]=0;idx-=1
                        if idx>=0:used.remove(assign.pop()[1])
                        continue
                    opt=opts[nexts[idx]];nexts[idx]+=1
                    if opt in used:continue
                    used.add(opt);assign.append((row,opt));idx+=1
            for matches in match():
                branches+=1;w.charge(base[j]+len(pairs)*len(matches))
                sub=tuple(sorted({(a,b) for row,opt in matches for a,b in zip(opt,row)}))
                tail=solve(j+1,sub,flip)
                if tail is not None:
                    mapping=[0]*base[j]
                    for row,opt in matches:
                        for t,s in zip(bb[row],aa[opt]):mapping[t]=s
                    return (tuple(mapping),)+tail
                backtracks+=1
            return None
        for flip in (0,1):
            if target.prefix!=source.prefix^(((1<<source.cutoff)-1) if flip else 0):continue
            result=solve(0,((source.root,target.root),),flip)
            if result is None:continue
            skill=CoordinateSkill(base,result,flip)
            if w.used>=max_work:raise Exhausted('qualification budget')
            ok,cost=verify_pullback(source,target,skill,max_work=max_work-w.used);w.charge(cost)
            if ok:return skill,dict(work=w.used,branches=branches,backtracks=backtracks,status='FOUND')
    except Exhausted:pass
    return None,dict(work=min(w.used,max_work),branches=branches,backtracks=backtracks,status='UNKNOWN')

class Vocabulary:
    """Retain a callable map only after an admitted example. Replay examples on restore.
    A retained map is a candidate on any compatible source, not evidence about a new target.
    """
    def __init__(self):self.skills={}
    def observe(self,source,target,skill,*,max_work=500000):
        from verify_coordinate_language import verify_pullback
        if not verify_pullback(source,target,skill,max_work=max_work)[0]:return False
        if skill.key not in self.skills and len(self.skills)>=256:return False
        self.skills[skill.key]=(skill,source.key,target.key);return True
    def packet(self):
        return {'schema':'pgi.coordinate-vocabulary.v1','skills':[[k,s.base,s.maps,s.flip,a,b] for k,(s,a,b) in self.skills.items()]}
    @classmethod
    def restore(cls,packet,views,*,max_work=500000):
        if type(packet) is not dict or set(packet)!={'schema','skills'} or packet['schema']!='pgi.coordinate-vocabulary.v1' or type(packet['skills']) is not list or len(packet['skills'])>256:raise ValueError('vocabulary')
        result=cls()
        for k,base,maps,flip,a,b in packet['skills']:
            s=CoordinateSkill(tuple(base),tuple(tuple(row) for row in maps),flip)
            if not valid(s) or k!=s.key or k in result.skills or not result.observe(views[a],views[b],s,max_work=max_work):raise ValueError('unqualified skill')
            if views[a].key!=a or views[b].key!=b:raise ValueError('view binding')
        return result
    def activate(self,source,key,*,max_work=500000):
        from verify_coordinate_language import verify_pullback
        s=self.skills[key][0];v,work=compile_view(source,s,max_work=max_work)
        ok,checked=verify_pullback(source,v,s,max_work=max_work)
        if not ok:return None
        return v,dict(compile_work=work,verification_work=checked)


def discover_collapsing(source,target,*,max_work=500000):
    """General separable maps (including many-to-one), exact bounded search.
    All occurrences of a source cofactor must realize one target cofactor under
    the shared remaining map. No cardinality equality assumed after collapse.
    """
    from verify_coordinate_language import verify_pullback
    w=Work(max_work);branches=0;backtracks=0
    if type(source) is not View or type(target) is not View or source.base!=target.base or source.cutoff!=target.cutoff:
        return None,dict(work=0,branches=0,backtracks=0,status='UNKNOWN')
    base=source.base;L=len(base)
    def classes(v,pairs,j,side):
        rows={}
        for r in range(base[j]):
            w.charge(len(pairs)+1)
            row=tuple(v.nodes[x-2][1][r] if x>=2 and v.nodes[x-2][0]==j else x for x in (p[side] for p in pairs))
            rows.setdefault(row,[]).append(r)
        return rows
    def consistent(pairs,flip):
        found={}
        for a,b in pairs:
            w.charge()
            if a<2 and b!=a^flip:return False
            if a in found and found[a]!=b:return False
            found[a]=b
        return True
    def solve(j,pairs,flip):
        nonlocal branches,backtracks
        w.charge()
        if not consistent(pairs,flip):return None
        if j==L:return ()
        aa=classes(source,pairs,j,0);bb=classes(target,pairs,j,1)
        choices=[]
        for row in bb:
            options=[]
            for opt in aa:
                w.charge();z=tuple(zip(opt,row))
                if consistent(z,flip):options.append((opt,z))
            if not options:return None
            choices.append((row,options))
        choices.sort(key=lambda x:len(x[1]));selected=[];constraints=[{}]
        # Choose one source representative per identical target joint row.
        # Any witness can be normalized this way without changing the suffix.
        nexts=[0]*len(choices);i=0
        while i>=0:
            w.charge()
            if i==len(choices):
                branches+=1;tail=solve(j+1,tuple(sorted(constraints[-1].items())),flip)
                if tail is not None:
                    row=[0]*base[j];w.charge(base[j])
                    for trg,src in selected:
                        for r in bb[trg]:row[r]=aa[src][0]
                    return (tuple(row),)+tail
                backtracks+=1;i-=1
                if i>=0:selected.pop();constraints.pop()
                continue
            trg,opts=choices[i]
            if nexts[i]>=len(opts):
                nexts[i]=0;i-=1
                if i>=0:selected.pop();constraints.pop()
                continue
            src,z=opts[nexts[i]];nexts[i]+=1
            prev=constraints[-1];w.charge(len(prev)+len(z))
            nxt=prev.copy();ok=True
            for a,b in z:
                if a in nxt and nxt[a]!=b:ok=False;break
                nxt[a]=b
            if not ok:continue
            selected.append((trg,src));constraints.append(nxt);i+=1
        return None
    try:
        for flip in (0,1):
            if target.prefix!=source.prefix^(((1<<source.cutoff)-1) if flip else 0):continue
            maps=solve(0,((source.root,target.root),),flip)
            if maps is None:continue
            s=CoordinateSkill(base,maps,flip)
            if w.used>=max_work:raise Exhausted('qualification budget')
            ok,cost=verify_pullback(source,target,s,max_work=max_work-w.used);w.charge(cost)
            if ok:return s,dict(work=w.used,branches=branches,backtracks=backtracks,status='FOUND')
    except Exhausted:pass
    return None,dict(work=min(w.used,max_work),branches=branches,backtracks=backtracks,status='UNKNOWN')

"""Independent synchronized traversal; no producer discovery or compilation."""
from ground_network import View

def verify_pullback(source,target,skill,*,max_work=500000):
    from coordinate_language import CoordinateSkill
    work=0
    try:
        if type(source) is not View or type(target) is not View or type(skill) is not CoordinateSkill or type(max_work) is not int or max_work<1:return False,work
        if type(skill.flip) is not int or skill.flip not in (0,1) or source.base!=target.base or source.base!=skill.base or source.cutoff!=target.cutoff:return False,work
        if type(skill.maps) is not tuple or len(skill.maps)!=len(source.base):return False,work
        for m,row in zip(source.base,skill.maps):
            if type(row) is not tuple or len(row)!=m or any(type(x) is not int or not 0<=x<m for x in row):return False,work
            work+=m
        if work+source.cutoff>max_work:return False,min(work,max_work)
        work+=source.cutoff
        for i in range(source.cutoff):
            if ((source.prefix>>i)&1)^skill.flip!=((target.prefix>>i)&1):return False,work
        stack=[(source.root,target.root)];seen=set();L=len(source.base)
        while stack:
            u,v=stack.pop()
            if (u,v) in seen:continue
            seen.add((u,v));work+=1
            if work>max_work:return False,max_work
            if u<2 and v<2:
                if u^skill.flip!=v:return False,work
                continue
            i=source.nodes[u-2][0] if u>=2 else L
            j=target.nodes[v-2][0] if v>=2 else L
            k=min(i,j);m=source.base[k]
            if work+m>max_work:return False,work
            work+=m
            for r in range(m):
                a=source.nodes[u-2][1][skill.maps[k][r]] if i==k else u
                b=target.nodes[v-2][1][r] if j==k else v
                stack.append((a,b))
        return True,work
    except (TypeError,ValueError,IndexError,AttributeError):return False,work

def verify_composition(first,second,result):
    from coordinate_language import CoordinateSkill
    try:
        if not all(type(s) is CoordinateSkill for s in (first,second,result)):return False
        if first.base!=second.base or first.base!=result.base or result.flip!=first.flip^second.flip:return False
        for s in (first,second,result):
            if type(s.flip) is not int or s.flip not in (0,1) or type(s.maps) is not tuple or len(s.maps)!=len(s.base):return False
            for m,row in zip(s.base,s.maps):
                if type(row) is not tuple or len(row)!=m or any(type(x) is not int or not 0<=x<m for x in row):return False
        return all(z[r]==a[b[r]] for a,b,z in zip(first.maps,second.maps,result.maps) for r in range(len(z)))
    except (TypeError,IndexError,ValueError):return False

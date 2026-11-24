"""Independent skill and pullback checks; no producer normalization/compilation."""
from ground_network import View, MAX_BITS
from collections import deque

def valid(n,lo=0):return type(n) is int and n>=lo and n.bit_length()<=MAX_BITS

def verify_skill(s):
    try:
        from skill_language import Skill
        if type(s) is not Skill or type(s.trace) is not tuple or not 1<=len(s.trace)<=32:return False
        # Traverse backwards: build time map on the argument of the original view.
        x,y,parity=1,0,0
        for op,k in reversed(s.trace):
            if not valid(k):return False
            if op=='advance':y+=k
            elif op=='stride' and k>=1:x*=k;y*=k
            elif op=='flip' and k==0:parity=1-parity
            else:return False
            if not valid(x,1) or not valid(y):return False
        return type(s.form) is tuple and all(type(z) is int for z in s.form) and s.form==(x,y,parity)
    except (ValueError,TypeError,IndexError):return False

def bit(v,t):
    if t<v.cutoff:return v.prefix//(1<<t)%2
    r=v.root
    while r>1:
        j,ch=v.nodes[r-2];r=ch[t%v.base[j]]
    return r

def verify_pullback(source,target,form,*,max_work=500000):
    """Prove target(t)=source(a*t+b) xor c for all nonnegative t.
    Synchronized product of independently structured CRT diagrams, including
    distinct bases and finite prefixes. No global period enumeration.
    """
    w=0
    try:
        if type(source) is not View or type(target) is not View or not valid(max_work,1):return False,w
        a,b,c=form
        if not valid(a,1) or not valid(b) or type(c) is not int or c not in (0,1):return False,w
        s=max(target.cutoff,max(0,-((b-source.cutoff)//a)))
        # For every actual accessed time enforce the finite-prefix contract.
        if s and not valid(a*(s-1)+b):return False,w
        for t in range(s):
            if w>=max_work:return False,w
            w+=1
            if bit(source,a*t+b)^c!=bit(target,t):return False,w
        todo=deque([(source.root,target.root)]);seen=set()
        while todo:
            u,v=todo.popleft()
            if (u,v) in seen:continue
            seen.add((u,v))
            if w>=max_work:return False,w
            w+=1
            if u<2 and v<2:
                if u^c!=v:return False,w
                continue
            p=source.primes[source.nodes[u-2][0]] if u>1 else float('inf')
            q=target.primes[target.nodes[v-2][0]] if v>1 else float('inf')
            m=min(p,q)
            left=source.nodes[u-2][1] if p==m else (u,)
            right=target.nodes[v-2][1] if q==m else (v,)
            n=max(len(left),len(right))
            if w+n>max_work:return False,w
            w+=n
            for r in range(n):todo.append((left[(a*r+b)%len(left)],right[r%len(right)]))
        return True,w
    except (ValueError,TypeError,IndexError,OverflowError):return False,w

def verify_skill_expression(graph,vocabulary,source,skill_key,ordinal,packet,*,max_work=500000):
    from ground_network_verify import verify_selection
    try:
        if not valid(ordinal,1) or type(packet) is not dict or set(packet)!={'schema','source','skill','target','ordinal','time'}:return False
        if (packet['schema'],packet['source'],packet['skill'],packet['ordinal'])!=('pgi.skill-expression.v1',source,skill_key,str(ordinal)):return False
        s=next((s for s in vocabulary.skills.values() if s.key==skill_key),None)
        if not verify_skill(s):return False
        t=packet['time']
        if type(t) is not str or len(t)>1235:return False
        n=int(t)
        if str(n)!=t or not valid(n):return False
        a=graph.views[source];b=graph.views[packet['target']]
        return verify_pullback(a,b,s.form,max_work=max_work)[0] and verify_selection(b,ordinal,n,max_work=max_work)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False

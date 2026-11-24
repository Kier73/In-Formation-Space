"""CIG-011: costed, source-equivalent contraction architecture selection.

Uses CIG-010's actual source audit, receiver-owned proof memory and realization.
The objective is a cold table-cell upper bound, not elapsed time or optimal SAT.
"""
from collections import deque, Counter
from time import perf_counter_ns
from adaptive_ground import initial, leaf, balanced, flatten, annotate, realize, Memory
from composed_ground import canonical, extract
from verify_adaptive_ground import audit
from regional_memory import identity

MAX_JOIN = 12


def mask(scope):
    return sum(1 << (v-1) for v in scope)


def score(source, n, tree):
    """Source-audited cold producer cell bound (excludes reuse and proof work)."""
    root = annotate(tree)
    if not audit(source, n, tree, root):
        raise ValueError('unqualified architecture')
    def walk(node, depth):
        if node['children'] is None:
            r = node['region']
            _, residual = extract(canonical(r['clauses'], n))
            w = len(r['scope']) if residual else len(node['boundary'])
            return 1 << w, w, depth, 1
        l,r = node['children']
        a,b = walk(l,depth+1),walk(r,depth+1)
        w = len(set(l['boundary']) | set(r['boundary']))
        return a[0]+b[0]+(1<<w),max(a[1],b[1],w),max(a[2],b[2]),a[3]+b[3]+1
    cells,width,depth,nodes=walk(root,0)
    return dict(cells=cells,width=width,depth=depth,nodes=nodes)


def graph_order(rows,n,method):
    adj=[set() for _ in range(n+1)]
    for c in rows:
        s=set(map(abs,c))
        for v in s:adj[v].update(s-{v})
    remaining=set(range(1,n+1)); order=[]
    for start in sorted(remaining,key=lambda v:(len(adj[v]),v)):
        if start not in remaining:continue
        if method=='walk':
            # True depth-first traversal, preferentially visit low-degree neighbors.
            stack=[start]
            while stack:
                v=stack.pop()
                if v not in remaining:continue
                remaining.remove(v);order.append(v)
                stack.extend(sorted(adj[v]&remaining,key=lambda w:(len(adj[w]),w),reverse=True))
            continue
        q=deque([start]);remaining.remove(start)
        while q:
            v=q.popleft() if method=='bfs' else q.pop();order.append(v)
            for w in sorted(adj[v]&remaining,reverse=method=='dfs'):
                remaining.remove(w);q.append(w)
    return order


def packed(source,n,method,width=8):
    if type(width)is not int or not 1<=width<=10:raise ValueError('leaf budget')
    rows=canonical(source,n); order=graph_order(rows,n,method); pos={v:i for i,v in enumerate(order)}
    rows.sort(key=lambda c:(min((pos[abs(l)] for l in c),default=-1),max((pos[abs(l)] for l in c),default=-1),c))
    covered=set();scope=set();clauses=[];leaves=[]
    for c in rows:
        s=set(map(abs,c)); covered.update(s)
        if len(s)>width:raise OverflowError('clause width')
        if len(scope|s)>width:
            leaves.append(leaf(scope,clauses));scope=set();clauses=[]
        scope.update(s);clauses.append(c)
    for v in order:
        if v in covered:continue
        if len(scope)==width:leaves.append(leaf(scope,clauses));scope=set();clauses=[]
        scope.add(v)
    if scope or clauses:leaves.append(leaf(scope,clauses))
    return leaves


def optimize_order(leaves,window=16):
    """Exact ordered binary contraction DP for <=window leaves; otherwise
    hierarchical contiguous windows, charging every candidate split.
    Leaf partition is fixed. Only tree associations change.
    """
    if type(window)is not int or not 2<=window<=32:raise ValueError('window')
    if not leaves:raise ValueError('empty architecture')
    # Each item stores (tree, full scope, admitted cold cell cost, depth).
    scopes=[mask(t['scope']) for t in leaves];totals=Counter(v for t in leaves for v in t['scope'])
    items=[]
    for t,s in zip(leaves,scopes):
        b=mask(v for v in t['scope'] if totals[v]>1)
        _,r=extract([tuple(c) for c in t['clauses']]); w=len(t['scope']) if r else b.bit_count()
        items.append((t,s,1<<w,0))
    attempts=0; levels=0
    while len(items)>1:
        levels+=1; size=len(items);prefix=[0];suffix=[0]*(size+1)
        for _,s,_,_ in items:prefix.append(prefix[-1]|s)
        for i in range(size-1,-1,-1):suffix[i]=suffix[i+1]|items[i][1]
        output=[]
        for start in range(0,size,window):
            end=min(size,start+window);m=end-start;group=items[start:end]
            # A child interval's boundary is the intersection with ALL outside scopes.
            bounds={}; unions={}; dp={}
            for i in range(m):
                s=0
                for j in range(i+1,m+1):
                    s|=group[j-1][1];unions[i,j]=s
                    bounds[i,j]=s&(prefix[start+i]|suffix[start+j])
                dp[i,i+1]=group[i] if bounds[i,i+1].bit_count()<=MAX_JOIN else None
            for length in range(2,m+1):
                for i in range(m-length+1):
                    j=i+length;best=None
                    if bounds[i,j].bit_count()<=MAX_JOIN:
                        for k in range(i+1,j):
                            attempts+=1;a,b=dp[i,k],dp[k,j]
                            w=(bounds[i,k]|bounds[k,j]).bit_count()
                            if a is None or b is None or w>MAX_JOIN:continue
                            c=a[2]+b[2]+(1<<w);d=1+max(a[3],b[3]);rank=(c,d,k)
                            if best is None or rank<best[0]:best=(rank,([a[0],b[0]],unions[i,j],c,d))
                    dp[i,j]=None if best is None else best[1]
            result=dp[0,m]
            if result is None:raise OverflowError('no qualified ordered contraction in window')
            output.append(result)
        items=output
    return items[0][0],dict(split_attempts=attempts,levels=levels,estimated_cells=items[0][2])


def select(source,n,*,previous=None,width=8,window=16,message_weight=0):
    """Cost-select among finite alternatives without executing their results."""
    if type(message_weight)is not int or message_weight<0:raise ValueError('invalid message price')
    t=perf_counter_ns();source=canonical(source,n);ledger=[];best=None
    def consider(name,build):
        nonlocal best
        start=perf_counter_ns()
        try:
            tree,formation=build();s=score(source,n,tree)
            row=dict(name=name,status='ADMITTED',**s,**formation,plan=identity(tree))
            row['objective']=s['cells']+message_weight*s['nodes']
            rank=(row['objective'],s['cells'],s['depth'],s['width'],s['nodes'],name)
            if best is None or rank<best[0]:best=(rank,tree,row)
        except (OverflowError,RecursionError) as e:row=dict(name=name,status='REFUSED',reason=str(e))
        row['formation_ns']=perf_counter_ns()-start;ledger.append(row)
    if previous is not None:consider('previous',lambda:(previous,{}))
    consider('cig010',lambda:(initial(source,n,width),{}))
    for method in ('bfs','dfs','walk'):
        try:leaves=packed(source,n,method,width)
        except OverflowError as e:ledger.append(dict(name=method,status='REFUSED',reason=str(e)));continue
        consider(method+'-balanced',lambda:(balanced(leaves),{}))
        consider(method+'-optimized',lambda:optimize_order(leaves,window))
    if best is None:return dict(status='UNKNOWN',candidates=ledger,selection_ns=perf_counter_ns()-t)
    return dict(status='SELECTED',tree=best[1],selected=best[2]['name'],score=best[2],candidates=ledger,selection_ns=perf_counter_ns()-t)


def select_widths(source,n,*,previous=None,widths=(3,8),window=16,message_weight=0):
    """Select across alternative leaf partitions as well as tree associations."""
    t=perf_counter_ns();ledger=[];best=None
    if not widths or len(widths)>4:raise ValueError('width catalog budget')
    for w in widths:
        candidate=select(source,n,previous=previous,width=w,window=window,message_weight=message_weight)
        ledger.extend(dict(r,leaf_budget=w) for r in candidate['candidates'])
        if candidate['status']=='SELECTED':
            s=candidate['score'];rank=(s['objective'],s['cells'],s['depth'],s['width'],s['nodes'],w,s['name'])
            if best is None or rank<best[0]:best=(rank,candidate,w)
    elapsed=perf_counter_ns()-t
    if best is None:return dict(status='UNKNOWN',candidates=ledger,selection_ns=elapsed)
    return dict(best[1],leaf_budget=best[2],candidates=ledger,selection_ns=elapsed)


def pareto(candidates):
    """Nondominated cost pairs within the admitted finite catalog."""
    pairs=sorted(set((c['cells'],c['nodes']) for c in candidates if c['status']=='ADMITTED'))
    best=None;frontier=[]
    for cells,nodes in pairs:
        if best is None or nodes<best:
            frontier.append([cells,nodes]);best=nodes
    return frontier

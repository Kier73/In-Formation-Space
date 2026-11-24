"""Independent admission for learned observation-period Grounds."""
from math import gcd
from ground_network import View, Edge
from ground_network_verify import verify_edge


def admit_reduction(graph,key,cycles,new,*,max_work=500000):
    """Verify admitted cycle provenance, period/density and exact language.

    Independent full relation checking is deliberate: a proposed reduction
    is not accepted merely because a controller believes a cycle is valid.
    """
    try:
        old=graph.views[key]
        if type(new) is not View or type(cycles) is not tuple or not 1<=len(cycles)<=64:return False
        shifts=[]
        for eid in cycles:
            e=graph.edges[eid]
            if e.target!=key or e.source!=key or e.shift==0:return False
            if e.source_before-e.target_before != e.shift*old.total//old.period or e.shift*old.total%old.period:return False
            shifts.append(e.shift)
        g=gcd(old.period,*shifts)
        if new.period!=g or new.total*old.period!=old.total*g or (new.cutoff,new.prefix)!=(old.cutoff,old.prefix):return False
        if new.source!='pgi-cycle:'+key+':'+str(g):return False
        edge=Edge(new.key,key,0,0,0,0,0)
        views=graph.views;views[new.key]=new
        if not verify_edge(views,edge,max_work=max_work):return False
        graph.register(new)
        return graph.admit(edge,max_work=max_work)
    except (ValueError,KeyError,TypeError,IndexError,OverflowError):return False


def restore_checkpoint(packet,*,expected_views=None,max_work=500000):
    """Rebuild all native mathematical admissions; policy remains untrusted advice.

    expected_views, if supplied, is an independently known set of view keys.
    A matching digest alone cannot authorize physical source or host claims.
    """
    from ground_network import Network,digest,integer
    from ground_intelligence import Policy,Intelligence
    if type(packet) is not dict or set(packet)!={'payload','digest'}:raise ValueError('checkpoint')
    p=packet['payload']
    if type(p) is not dict or set(p)!={'schema','policy','views','edges','memories'} or p['schema']!='pgi.checkpoint.v1' or packet['digest']!=digest(p):raise ValueError('checkpoint identity')
    if any(type(p[x]) is not list for x in ('views','edges','memories')) or len(p['views'])>1024 or len(p['edges'])>4096:raise ValueError('checkpoint budget')
    def number(s):
        if type(s) is not str or len(s)>1235:raise ValueError('number')
        v=int(s);integer(v)
        if str(v)!=s:raise ValueError('noncanonical number')
        return v
    g=Network();agent=Intelligence(g,Policy.restore(p['policy']))
    for key,source,base,nodes,root,cutoff,prefix in p['views']:
        v=View(source,tuple(base),tuple((j,tuple(ks)) for j,ks in nodes),root,cutoff,number(prefix))
        if v.key!=key or key in g.views:raise ValueError('view identity')
        g.register(v)
    if expected_views is not None and set(g.views)!=set(expected_views):raise ValueError('expected views')
    for key,source,target,shift,start,sb,tb,cost,path in p['edges']:
        e=Edge(source,target,*map(number,(shift,start,sb,tb,cost)))
        if e.key!=key or key in g.edges or type(path) is not list:raise ValueError('edge identity')
        if not (g.admit_composite(e,tuple(path)) if path else g.admit(e,max_work=max_work)):raise ValueError('edge proof')
    if len(set(p['memories']))!=len(p['memories']) or not set(p['memories'])<=set(g.views):raise ValueError('memory identity')
    agent.memories.update(p['memories']);return agent


def verify_expression(graph,target,ordinal,packet,*,max_work=500000):
    """Check a definitive expression against the requested target and ordinal.

    UNKNOWN is not an accepted mathematical claim; return False for it.
    A route's cost is diagnostic and does not certify optimality.
    """
    from ground_network import Route,integer
    from ground_network_verify import verify_realization,verify_selection
    try:
        integer(ordinal,1);integer(max_work,1)
        if type(packet) is not dict or set(packet)!={'schema','target','ordinal','status','time','route'}:return False
        if packet['schema']!='pgi.expression.v1' or packet['target']!=target or packet['ordinal']!=str(ordinal) or packet['status']!='FOUND':return False
        def num(s):
            if type(s) is not str or len(s)>1235:raise ValueError('integer')
            v=int(s);integer(v)
            if str(v)!=s:raise ValueError('canonical integer')
            return v
        t=num(packet['time']);integer(t,0);r=packet['route']
        if r is None:return verify_selection(graph.views[target],ordinal,t,max_work=max_work)
        if type(r) is not dict or set(r)!={'edges','source','source_ordinal','shift','cost'} or type(r['edges']) is not list or len(r['edges'])>64:return False
        route=Route(target,ordinal,tuple(r['edges']),r['source'],num(r['source_ordinal']),num(r['shift']),num(r['cost']))
        integer(route.cost,0);st=t+route.shift;integer(st,0)
        return verify_realization(graph,target,ordinal,route,st,max_work=max_work)==t
    except (ValueError,TypeError,KeyError,IndexError,OverflowError):return False

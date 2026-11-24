"""Independent family admission and expression verification.
No discovery search or producer cofactor/sparse implementation is trusted.
"""
from math import gcd
from ground_network import View
from verify_skill_language import verify_pullback,valid
from ground_network_verify import verify_selection


def verify_example(a,b,f):return verify_pullback(a,b,f)[0]


def qualify_family(f,examples):
    try:
        from family_language import Family
        if type(f) is not Family or f.method not in ('sparse','cofactor') or type(f.examples) is not tuple or not 3<=len(f.examples)<=128 or len(set(f.examples))!=len(f.examples):return False
        strides=set();offsets=set()
        for key in f.examples:
            a,b,form=examples[key]
            if a.key!=key or not verify_example(a,b,form):return False
            x,y,c=form;strides.add(x);offsets.add(y)
            if f.method=='sparse':
                if a.period//gcd(x,a.period)!=b.period or min(a.total,a.period-a.total)>32:return False
            elif a.base!=b.base or gcd(x,a.period)!=1:return False
        return len(strides)>=2 and len(offsets)>=2
    except (TypeError,ValueError,KeyError,AttributeError):return False


def readint(s,lo=0):
    if type(s) is not str or len(s)>1235:raise ValueError('integer')
    n=int(s)
    if not valid(n,lo) or str(n)!=s:raise ValueError('integer')
    return n


def readform(f):
    if type(f) is not list or len(f)!=3 or type(f[2]) is not int or f[2] not in (0,1):raise ValueError('form')
    return readint(f[0],1),readint(f[1]),f[2]


def restore(packet,views):
    from family_language import Family,FamilyIntelligence
    if type(packet) is not dict or set(packet)!={'schema','examples','families'} or packet['schema']!='pgi.family-memory.v1' or type(packet['examples']) is not list or len(packet['examples'])>128 or type(packet['families']) is not list or len(packet['families'])>2:raise ValueError('memory')
    obj=FamilyIntelligence()
    for a,b,f in packet['examples']:
        x,y=views[a],views[b];form=readform(f)
        if type(x) is not View or type(y) is not View or x.key!=a or y.key!=b or a in obj.examples or not verify_example(x,y,form):raise ValueError('example')
        obj.examples[a]=x,y,form
    for key,method,examples in packet['families']:
        f=Family(method,tuple(examples))
        if f.key!=key or method in obj.families or not qualify_family(f,obj.examples):raise ValueError('family')
        obj.families[method]=f
    return obj


def verify_expression(source,target,form,ordinal,packet,*,max_work=500000):
    try:
        if type(packet) is not dict or set(packet)!={'schema','source','target','form','ordinal','time'}:return False
        if (packet['schema'],packet['source'],packet['target'])!=('pgi.family-expression.v1',source.key,target.key) or readform(packet['form'])!=form or readint(packet['ordinal'],1)!=ordinal:return False
        if not valid(ordinal,1):return False
        t=readint(packet['time'])
        return verify_pullback(source,target,form,max_work=max_work)[0] and verify_selection(target,ordinal,t,max_work=max_work)
    except (TypeError,ValueError,KeyError,AttributeError):return False

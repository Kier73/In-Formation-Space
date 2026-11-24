"""Independent finite policy audit: use gate truth tables, not producer ANFs."""
from itertools import combinations
from hashlib import sha256
import json
from verify_language_selector import verify as verify_language


def verify(source,language,intention,offers,identify,certificate):
    try:
        if not verify_language(source,language,intention=intention):return False
        cs=language['candidates'];n=len(language['source_model']['active_labels'])
        if not language['candidate_class']['complete_qualification'] or not 1<=len(cs)<=12:return False
        if type(identify) is not bool or type(offers) is not list or len(offers)>256:return False
        seen=set(); columns=[]
        for p in offers:
            if type(p) is not list or len(p)!=3 or any(type(v) is not int for v in p):return False
            x,b,cost=p
            if not 0<=x<2**n or not 0<=b<n or cost<0 or (x,b) in seen:return False
            seen.add((x,b));col=[]
            for c in cs:
                gate=next((g for g in c['gates'] if g['output']==b),None)
                if gate is None:col.append((x>>b)&1)
                else:
                    k=sum(((x>>v)&1)*2**j for j,v in enumerate(gate['inputs']))
                    col.append(gate['table'][k])
            columns.append(col)
        goals=[i if identify else tuple(c['conditional_observation']) for i,c in enumerate(cs)]
        ids=tuple(range(len(cs))); optimal={}
        for size in range(1,len(cs)+1):
            for subset in combinations(ids,size):
                if len({goals[i] for i in subset})==1:optimal[subset]=0;continue
                costs=[]
                for p,col in zip(offers,columns):
                    a=tuple(i for i in subset if not col[i]);b=tuple(i for i in subset if col[i])
                    if a and b and optimal[a] is not None and optimal[b] is not None:
                        costs.append(p[2]+max(optimal[a],optimal[b]))
                optimal[subset]=min(costs) if costs else None
        def audit(node,subset):
            if type(node) is not dict or node['candidates']!=list(subset):raise ValueError('wrong candidate fiber')
            if 'result' in node:
                value=goals[subset[0]]
                if set(node)!={'candidates','result'} or len({goals[i] for i in subset})!=1 or node['result']!=(value if identify else list(value)):raise ValueError('wrong leaf')
                return 0
            j=node['probe']
            if set(node)!={'candidates','probe','zero','one'} or type(j) is not int or not 0<=j<len(offers):raise ValueError('invalid probe')
            a=tuple(i for i in subset if not columns[j][i]);b=tuple(i for i in subset if columns[j][i])
            if not a or not b:raise ValueError('non-refining probe')
            return offers[j][2]+max(audit(node['zero'],a),audit(node['one'],b))
        digest=sha256(json.dumps(language,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if set(certificate)!={'schema','language_digest','offers','identify','status','worst_cost','tree','planning_states'}:return False
        if certificate['schema']!='ifs.cig007.evidence-policy.v1' or certificate['language_digest']!=digest or certificate['offers']!=offers or certificate['identify'] is not identify:return False
        # Replay producer-reachable subset count independently (including dead ends).
        reached=set();todo=[ids]
        while todo:
            sub=todo.pop()
            if sub in reached:continue
            reached.add(sub)
            if len({goals[i] for i in sub})==1:continue
            for col in columns:
                a=tuple(i for i in sub if not col[i]);b=tuple(i for i in sub if col[i])
                if a and b:todo.extend((a,b))
        # Producer may short-circuit after both branches have been evaluated; all are visited.
        if certificate['planning_states']!=len(reached):return False
        if optimal[ids] is None:return certificate['status']=='UNRESOLVED' and certificate['tree'] is None and certificate['worst_cost'] is None
        return certificate['status']=='RESOLVABLE' and certificate['worst_cost']==optimal[ids]==audit(certificate['tree'],ids)
    except (ValueError,TypeError,KeyError,IndexError,RecursionError):return False

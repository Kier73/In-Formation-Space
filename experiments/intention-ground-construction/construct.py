"""IGC-001: construct a minimal finite Ground from a declarative trace intention.

Brzozowski derivatives generate the state-space; partition refinement minimizes it.
Witnesses distinguish every reachable state pair. No execution rights are granted.
"""
from __future__ import annotations
from collections import deque
from hashlib import sha256
import json

INTENT_SCHEMA = 'ifs.igc001.trace-intention.v1'
RECEIPT_SCHEMA = 'ifs.igc001.construction-receipt.v1'
GROUND_SCHEMA = 'ifs.igc001.minimal-dfa-ground.v1'
EMPTY = ('empty',)
EPS = ('epsilon',)


class ConstructionError(ValueError):
    """Invalid intention or unverifiable mathematical construction."""


def canonical(value):
    """Canonical finite UTF-8 JSON, used for identity but not authentication."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf8')


def digest(value):
    """Content identity only, never an authorization or signature."""
    return sha256(canonical(value)).hexdigest()


def make_alt(terms):
    """Flatten, deduplicate, and canonically order alternatives."""
    flattened = []
    for term in terms:
        if term == EMPTY:
            continue
        flattened.extend(term[1:] if term[0] == 'alt' else [term])
    flattened = tuple(sorted(set(flattened), key=repr))
    if not flattened:
        return EMPTY
    if len(flattened) == 1:
        return flattened[0]
    return ('alt', *flattened)


def make_concat(terms):
    flattened = []
    for term in terms:
        if term == EMPTY:
            return EMPTY
        if term == EPS:
            continue
        flattened.extend(term[1:] if term[0] == 'concat' else [term])
    if not flattened:
        return EPS
    if len(flattened) == 1:
        return flattened[0]
    return ('concat', *flattened)


def make_star(term):
    if term in (EMPTY, EPS):
        return EPS
    return term if term[0] == 'star' else ('star', term)


def parse_language(node, alphabet, *, depth=0, counters=None):
    """Strict regular-language AST, with no predefined machine states."""
    if counters is None:
        counters = [0]
    counters[0] += 1
    if counters[0] > 64 or depth > 16:
        raise ConstructionError('language AST budget exceeded')
    if type(node) is not dict or type(node.get('op')) is not str:
        raise ConstructionError('invalid language node')
    op = node['op']
    if op in ('empty', 'epsilon'):
        if set(node) != {'op'}:
            raise ConstructionError('unexpected language fields')
        return (op,)
    if op == 'symbol':
        if set(node) != {'op', 'value'} or type(node['value']) is not str or node['value'] not in alphabet:
            raise ConstructionError('symbol outside alphabet')
        return ('symbol', node['value'])
    if op in ('alt', 'concat'):
        if set(node) != {'op', 'args'} or type(node['args']) is not list or not 1 <= len(node['args']) <= 32:
            raise ConstructionError('invalid language composition')
        children = [parse_language(x, alphabet, depth=depth+1, counters=counters) for x in node['args']]
        return make_alt(children) if op == 'alt' else make_concat(children)
    if op == 'star':
        if set(node) != {'op', 'arg'}:
            raise ConstructionError('invalid star')
        return make_star(parse_language(node['arg'], alphabet, depth=depth+1, counters=counters))
    raise ConstructionError('unknown language operation')


def normalize_intention(spec):
    """Validate source intention and capacity of a proposed finite host."""
    if type(spec) is not dict or set(spec) != {'schema','alphabet','language','required','forbidden','max_states'}:
        raise ConstructionError('unexpected intention shape')
    if spec['schema'] != INTENT_SCHEMA:
        raise ConstructionError('unsupported intention version')
    alphabet = spec['alphabet']
    if (type(alphabet) is not list or not 1 <= len(alphabet) <= 8
        or any(type(s) is not str or not 1 <= len(s) <= 32 or
               any(ord(c)<32 or ord(c)>126 for c in s) for s in alphabet)
        or sorted(set(alphabet)) != alphabet):
        raise ConstructionError('alphabet must be unique, sorted, finite printable tokens')
    cap = spec['max_states']
    if type(cap) is not int or not 1 <= cap <= 32:
        raise ConstructionError('invalid host state budget')
    parse_language(spec['language'], set(alphabet))
    for field in ('required','forbidden'):
        words = spec[field]
        if (type(words) is not list or len(words) > 32 or
            any(type(w) is not list or len(w)>128 or
                any(type(t) is not str or t not in alphabet for t in w) for w in words) or
            len({tuple(w) for w in words}) != len(words)):
            raise ConstructionError('invalid or repeated behavioral examples')
    return spec


def nullable(node):
    op=node[0]
    if op in ('epsilon','star'):
        return True
    if op in ('empty','symbol'):
        return False
    if op=='alt':
        return any(nullable(x) for x in node[1:])
    if op=='concat':
        return all(nullable(x) for x in node[1:])
    raise AssertionError(op)


def derivative(node, symbol):
    """One-token Brzozowski derivative of a regular-language expression."""
    op=node[0]
    if op in ('empty','epsilon'):
        return EMPTY
    if op=='symbol':
        return EPS if node[1]==symbol else EMPTY
    if op=='alt':
        return make_alt(derivative(x,symbol) for x in node[1:])
    if op=='star':
        return make_concat([derivative(node[1],symbol),node])
    if op=='concat':
        terms=[]
        for i,term in enumerate(node[1:]):
            terms.append(make_concat([derivative(term,symbol),*node[i+2:]]))
            if not nullable(term):
                break
        return make_alt(terms)
    raise AssertionError(op)


def matches(node, word):
    for x in word:
        node=derivative(node,x)
    return nullable(node)


def construct_derivative_dfa(node, alphabet, max_states=256):
    """Expand finite language residuals, never simulate a future input timeline."""
    queue=deque([node]); ids={node:0}; accepts=[]; transitions=[]
    while queue:
        current=queue.popleft()
        if len(repr(current))>20000:
            raise ConstructionError('derivative expression complexity budget exhausted')
        accepts.append(nullable(current)); row=[]
        for sym in alphabet:
            next_node=derivative(current,sym)
            if next_node not in ids:
                if len(ids)>=max_states:
                    raise ConstructionError('derivative state budget exhausted')
                ids[next_node]=len(ids); queue.append(next_node)
            row.append(ids[next_node])
        transitions.append(row)
    return accepts,transitions


def minimize(accepts, transitions):
    """Partition-refine observable behavior and relabel reachable classes by BFS."""
    n=len(accepts);classes=[int(x) for x in accepts]
    for _ in range(n+1):
        sigs=[(accepts[i],*(classes[k] for k in transitions[i])) for i in range(n)]
        lookup={signature:j for j,signature in enumerate(sorted(set(sigs)))}
        newer=[lookup[s] for s in sigs]
        if all((classes[i]==classes[j])==(newer[i]==newer[j]) for i in range(n) for j in range(n)):
            classes=newer;break
        classes=newer
    else:
        raise AssertionError('partition refinement failed')
    representatives={c:next(i for i in range(n) if classes[i]==c) for c in set(classes)}
    queue=deque([classes[0]]);mapping={classes[0]:0}
    out_accept=[];out_trans=[]
    while queue:
        klass=queue.popleft();ix=representatives[klass]
        out_accept.append(accepts[ix]);row=[]
        for state in transitions[ix]:
            other=classes[state]
            if other not in mapping:
                mapping[other]=len(mapping);queue.append(other)
            row.append(mapping[other])
        out_trans.append(row)
    return out_accept,out_trans


def execute(ground, word):
    """Interpret the constructed complete finite transition Ground."""
    alphabet=ground['alphabet'];state=0
    for symbol in word:
        if symbol not in alphabet:
            raise ConstructionError('input token outside Ground')
        state=ground['transitions'][state][alphabet.index(symbol)]
    return state,ground['accepting'][state]


def shortest_paths(transitions, alphabet):
    queue=deque([0]);paths={0:[]}
    while queue:
        current=queue.popleft()
        for symbol,nextstate in zip(alphabet,transitions[current]):
            if nextstate not in paths:
                paths[nextstate]=paths[current]+[symbol];queue.append(nextstate)
    return [paths[i] for i in range(len(transitions))] if len(paths)==len(transitions) else None


def distinguish(a,b,accepts,transitions,alphabet):
    """Shortest suffix separating two putative machine states, via pair BFS."""
    queue=deque([(a,b,[])]);seen={(a,b)}
    while queue:
        x,y,suffix=queue.popleft()
        if accepts[x]!=accepts[y]:
            return suffix
        for index,sym in enumerate(alphabet):
            pair=(transitions[x][index],transitions[y][index])
            if pair not in seen:
                seen.add(pair);queue.append((pair[0],pair[1],suffix+[sym]))
    raise AssertionError('not minimal: indistinguishable states survived')


def certificate(accepts,transitions,alphabet):
    prefixes=shortest_paths(transitions,alphabet)
    if prefixes is None:
        raise AssertionError('unreachable minimized state')
    return {'reachable_prefixes':prefixes,
            'distinguishing_suffixes':[
                {'left':i,'right':j,
                 'suffix':distinguish(i,j,accepts,transitions,alphabet)}
                for i in range(len(accepts)) for j in range(i+1,len(accepts))]}


def synthesize(intention):
    """Build a minimal state-space or witnessed intention/capacity obstruction."""
    intention=normalize_intention(intention)
    alpha=intention['alphabet'];regex=parse_language(intention['language'],set(alpha))
    for field, expected in (('required',True),('forbidden',False)):
        for word in intention[field]:
            actual=matches(regex,word)
            if actual != expected:
                payload={'schema':RECEIPT_SCHEMA,'intention':intention,
                         'intention_sha256':digest(intention),
                         'status':'incompatible_language_constraints',
                         'witness':{'word':word,'declared':field,
                                    'required_acceptance':expected,
                                    'language_acceptance':actual},
                         'authority':'none'}
                return {'payload':payload,'sha256':digest(payload)}
    try:
        raw_accepts,raw_trans=construct_derivative_dfa(regex,alpha)
    except ConstructionError as e:
        payload={'schema':RECEIPT_SCHEMA,'intention':intention,
                 'intention_sha256':digest(intention),'status':'budget_exhausted',
                 'reason':str(e),'authority':'none'}
        return {'payload':payload,'sha256':digest(payload)}
    accepts,trans=minimize(raw_accepts,raw_trans)
    if len(accepts)>64:
        payload={'schema':RECEIPT_SCHEMA,'intention':intention,
                 'intention_sha256':digest(intention),'status':'budget_exhausted',
                 'reason':'minimal-state certificate budget exhausted',
                 'authority':'none'}
        return {'payload':payload,'sha256':digest(payload)}
    ground={'schema':GROUND_SCHEMA,'alphabet':alpha,
            'initial_state':0,'state_count':len(accepts),
            'accepting':accepts,'transitions':trans}
    ground['ground_sha256']=digest(ground)
    proof=certificate(accepts,trans,alpha)
    status=('realized_under_declared_capacity' if len(accepts)<=intention['max_states']
            else 'insufficient_declared_state_capacity')
    payload={'schema':RECEIPT_SCHEMA,'intention':intention,
             'intention_sha256':digest(intention),
             'status':status,'ground':ground,'minimality_certificate':proof,
             'authority':'mathematical_only_no_host_execution_rights'}
    return {'payload':payload,'sha256':digest(payload)}


def navigate_repeat(ground, symbol, count, *, prefix=(), suffix=()):
    """Exact action repetition by binary function composition: O(n log count)."""
    if type(count) is not int or count<0:
        raise ConstructionError('repeat coordinate must be nonnegative integer')
    alpha=ground['alphabet']
    if symbol not in alpha:
        raise ConstructionError('unknown repeat symbol')
    state=execute(ground,prefix)[0]
    power=[row[alpha.index(symbol)] for row in ground['transitions']]
    while count:
        if count & 1:
            state=power[state]
        count>>=1
        if count:
            power=[power[x] for x in power]
    for x in suffix:
        if x not in alpha:
            raise ConstructionError('unknown suffix token')
        state=ground['transitions'][state][alpha.index(x)]
    return state,ground['accepting'][state]


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument('intention',type=Path)
    p.add_argument('--output',type=Path)
    opts=p.parse_args()
    receipt=synthesize(json.loads(opts.intention.read_text(encoding='utf8')))
    body=json.dumps(receipt,sort_keys=True,ensure_ascii=False,indent=2)+'\n'
    if opts.output:
        opts.output.write_text(body,encoding='utf8')
    print(body)


if __name__=='__main__':
    main()

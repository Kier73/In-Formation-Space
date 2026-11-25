"""VLM-001: exact word machine, demand evaluation and structural Grounds."""
from dataclasses import dataclass
import hashlib
import json
import shlex

MASK = (1 << 32) - 1
OPS = {"input": 0, "const": 0, "add": 2, "mul": 2, "xor": 2, "and": 2, "lt": 2, "select": 3}

def word(n):
    if type(n) is not int or not 0 <= n <= MASK:
        raise ValueError("expected unsigned 32-bit word")
    return n

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True)
class Node:
    op: str
    args: tuple = ()
    value: int = 0

@dataclass(frozen=True)
class Program:
    nodes: tuple
    output: int

    def __post_init__(self):
        if type(self.nodes) is not tuple or not self.nodes or len(self.nodes) > 65536:
            raise ValueError("invalid program size")
        if type(self.output) is not int or not 0 <= self.output < len(self.nodes):
            raise ValueError("invalid output")
        for i, n in enumerate(self.nodes):
            if type(n) is not Node or n.op not in OPS or type(n.args) is not tuple or len(n.args) != OPS[n.op]:
                raise ValueError("invalid operator")
            word(n.value)
            if n.op != "const" and n.value != 0:
                raise ValueError("unused literal")
            if any(type(j) is not int or not 0 <= j < i for j in n.args):
                raise ValueError("dependency must precede node")

    @property
    def identity(self):
        return digest(["vlm-word32-v1", [(n.op, n.args, n.value) for n in self.nodes], self.output])

    def needed(self):
        live = {self.output}
        for i in range(self.output, -1, -1):
            if i in live:
                live.update(self.nodes[i].args)
        return live

def apply(op, args):
    if op == "add": return (args[0] + args[1]) & MASK
    if op == "mul": return (args[0] * args[1]) & MASK
    if op == "xor": return args[0] ^ args[1]
    if op == "and": return args[0] & args[1]
    if op == "lt": return int(args[0] < args[1])
    if op == "select": return args[1] if args[0] else args[2]
    raise ValueError(op)

def reference(p, x):
    """Independent full-prefix interpreter; intentionally realizes dead nodes."""
    word(x)
    vals = []
    for n in p.nodes:
        vals.append(x if n.op == "input" else n.value if n.op == "const"
                    else apply(n.op, [vals[j] for j in n.args]))
    return vals[p.output]

def demand(p, x):
    word(x)
    live = p.needed()
    vals = {}
    count = 0
    for i in sorted(live):
        n = p.nodes[i]
        vals[i] = x if n.op == "input" else n.value if n.op == "const" else apply(n.op, [vals[j] for j in n.args])
        count += bool(n.args)
    return vals[p.output], count

@dataclass(frozen=True)
class Ground:
    program: str
    a: int
    b: int

def discover(p):
    """Symbolic affine closure over Z/(2**32); reject unsupported live nodes."""
    forms = {}
    for i in sorted(p.needed()):
        n = p.nodes[i]
        if n.op == "input": a, b = 1, 0
        elif n.op == "const": a, b = 0, n.value
        elif n.op in ("add", "mul"):
            u, v = (forms[j] for j in n.args)
            if n.op == "add": a, b = u[0] + v[0], u[1] + v[1]
            elif u[0] == 0: a, b = u[1]*v[0], u[1]*v[1]
            elif v[0] == 0: a, b = v[1]*u[0], v[1]*u[1]
            else: return None
        else: return None
        forms[i] = (a & MASK, b & MASK)
    return Ground(p.identity, *forms[p.output])

def verify(p, g):
    """Independent conservative polynomial checker, not sampling."""
    if type(g) is not Ground or g.program != p.identity:
        return False
    try: word(g.a); word(g.b)
    except ValueError: return False
    polys = {}
    for i in sorted(p.needed()):
        n = p.nodes[i]
        if n.op == "input": q = [0, 1]
        elif n.op == "const": q = [n.value]
        elif n.op in ("add", "mul"):
            a, b = (polys[j] for j in n.args)
            q = [0] * (max(len(a), len(b)) if n.op == "add" else len(a)+len(b)-1)
            if n.op == "add":
                for v in (a,b):
                    for k,c in enumerate(v): q[k] += c
            else:
                for j,c in enumerate(a):
                    for k,d in enumerate(b): q[j+k] += c*d
        else: return False
        q = [c & MASK for c in q]
        while len(q)>1 and q[-1] == 0: q.pop()
        if len(q)>2: return False
        polys[i] = q
    q = polys[p.output] + [0]
    return (q[1],q[0]) == (g.a,g.b)

def jump(a, b, x, steps):
    """Compose affine maps by squaring. Return value and composition count."""
    word(a); word(b); word(x)
    if type(steps) is not int or not 0 <= steps < 1 << 64:
        raise ValueError("invalid step count")
    c, d, count = 1, 0, 0
    while steps:
        if steps & 1:
            c, d = (a*c)&MASK, (a*d+b)&MASK
            count += 1
        a, b = (a*a)&MASK, (a*b+b)&MASK
        count += 1
        steps >>= 1
    return (c*x+d)&MASK, count

class Machine:
    """Trusted local authority. Callers submit data, not executable code."""
    def __init__(self):
        self._grounds = {}
        self._sessions = {}
        self.receipts = []

    def admit(self, p, g):
        if not verify(p,g): raise ValueError("unverified Ground")
        self._grounds[p.identity] = g

    def open(self, name, x):
        if not isinstance(name,str) or not name or name in self._sessions:
            raise ValueError("invalid or duplicate session")
        self._sessions[name] = (word(x),0)

    def observe(self, p, x):
        identity = p.identity
        g = self._grounds.get(identity)
        if g is None:
            y, cost = demand(p,x)
            route = "demand"
        else:
            y, cost, route = (g.a*word(x)+g.b)&MASK, 2, "ground"
        receipt = {"program":identity,"input":x,"output":y,"route":route,"word_ops":cost}
        receipt["digest"] = digest(receipt)
        self.receipts.append(receipt.copy())
        return receipt

    def advance(self, name, p, steps, budget=100000):
        x,t = self._sessions[name]
        if type(steps) is not int or not 0 <= steps < 1<<64: raise ValueError("invalid steps")
        g = self._grounds.get(p.identity)
        if g is not None:
            y,cost = jump(g.a,g.b,x,steps)
            route = "affine-jump"
        else:
            if steps > budget: raise ValueError("reference step budget exceeded")
            y,cost = x,0
            for _ in range(steps):
                y,k = demand(p,y)
                cost += k
            route = "iteration"
        self._sessions[name] = (y,t+steps)
        r = {"session":name,"program":p.identity,"start":x,"end":y,"from":t,"to":t+steps,
             "route":route,"work":cost}
        r["digest"] = digest(r)
        self.receipts.append(r.copy())
        return r

def affine(a,b):
    return Program((Node("input"),Node("const",value=word(a)),Node("mul",(0,1)),
                    Node("const",value=word(b)),Node("add",(2,3))),4)

def repl():
    m = Machine()
    p = affine(3,7)
    print("VLM-001 | open NAME X | use A B | discover | run X | step NAME N | inspect | quit")
    while True:
        try: cmd,*args = shlex.split(input("vl> "))
        except (EOFError,KeyboardInterrupt): break
        except ValueError: continue
        try:
            if cmd == "quit": break
            if cmd == "open" and len(args)==2: m.open(args[0],int(args[1]))
            elif cmd == "use" and len(args)==2: p = affine(*map(int,args))
            elif cmd == "discover" and not args:
                g = discover(p); m.admit(p,g); print(g)
            elif cmd == "run" and len(args)==1: print(m.observe(p,int(args[0])))
            elif cmd == "step" and len(args)==2: print(m.advance(args[0],p,int(args[1])))
            elif cmd == "inspect" and not args: print(m._sessions, m._grounds)
            else: print("invalid command")
        except (ValueError,KeyError) as exc: print("rejected:",exc)

if __name__ == "__main__":
    repl()

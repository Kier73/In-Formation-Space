#include "core.h"
/* Single authority, transactional replacement; no dynamic allocation. */
static Node banks[2][CAP];
static uint8_t live[CAP];
static uint32_t values[CAP], poly[CAP][2];
static uint32_t active, count, output, pending, target, used, staged;
static uint32_t ga,gb,ground;
static int valid(Node v,uint32_t i){
    if(v.op>SELECT || (v.op!=CONST && v.k)) return 0;
    if(v.op<=CONST) return !(v.a|v.b|v.c) && (v.op!=INPUT || !v.k);
    return v.a<i && v.b<i && (v.op==SELECT ? v.c<i : !v.c);
}
int begin(uint32_t n,uint32_t out){
    if(!n || n>CAP || out>=n) return 0;
    pending=n;target=out;used=0;staged=1;return 1;
}
int put(uint32_t i,Node v){
    if(!staged || i!=used || i>=pending || !valid(v,i)) {staged=0;return 0;}
    banks[active^1][used++]=v;return 1;
}
int commit(void){
    if(!staged || used!=pending) return 0;
    active^=1;count=pending;output=target;ground=0;staged=0;
    for(uint32_t i=0;i<count;i++) live[i]=0;
    live[output]=1;
    for(uint32_t i=count;i-->0;) if(live[i]){
        Node v=banks[active][i];
        if(v.op>=ADD){live[v.a]=live[v.b]=1;if(v.op==SELECT)live[v.c]=1;}
    }
    return 1;
}
int admit(uint32_t a,uint32_t b){
    if(!count)return 0;
    /* Exact coefficient verifier over Z/2^32; conservatively rejects
       any intermediate nonzero quadratic coefficient or other operator. */
    for(uint32_t i=0;i<count;i++)if(live[i]){
        Node v=banks[active][i];uint32_t u=0,w=0;
        if(v.op==INPUT)u=1;
        else if(v.op==CONST)w=v.k;
        else if(v.op==ADD){u=poly[v.a][0]+poly[v.b][0];w=poly[v.a][1]+poly[v.b][1];}
        else if(v.op==MUL){
            uint32_t p=poly[v.a][0],q=poly[v.a][1],r=poly[v.b][0],s=poly[v.b][1];
            if((uint32_t)(p*r)!=0)return 0;
            u=p*s+q*r;w=q*s;
        }else return 0;
        poly[i][0]=u;poly[i][1]=w;
    }
    if(poly[output][0]!=a || poly[output][1]!=b)return 0;
    ga=a;gb=b;ground=1;return 1;
}
/* A reversible nonlinear shear on packed 16-bit coordinates.
   E(x)=x+k*(x&65535)^3; D(x)=x-k*(x&65535)^3.
   k is a multiple of 65536, so E and D preserve the low word.
   Verify the actual graph is exactly D(translate_d(E(x))). */
int admit_chart(uint32_t k,uint32_t d){
    if((k&65535u)||count!=16||output!=15)return 0;
    const Node expected[16]={
        {INPUT,0,0,0,0},{CONST,0,0,0,65535},{AND,0,1,0,0},
        {MUL,2,2,0,0},{MUL,3,2,0,0},{CONST,0,0,0,k},
        {MUL,4,5,0,0},{ADD,0,6,0,0},{CONST,0,0,0,d},
        {ADD,7,8,0,0},{AND,9,1,0,0},{MUL,10,10,0,0},
        {MUL,11,10,0,0},{CONST,0,0,0,0u-k},{MUL,12,13,0,0},
        {ADD,9,14,0,0}
    };
    for(uint32_t i=0;i<16;i++){
        Node a=banks[active][i],b=expected[i];
        if(a.op!=b.op||a.a!=b.a||a.b!=b.b||a.c!=b.c||a.k!=b.k)return 0;
    }
    ga=k;gb=d;ground=2;return 1;
}
static uint32_t shear(uint32_t x,uint32_t k){uint32_t l=x&65535u;return x+k*l*l*l;}
static int evaluate(const Node *nodes,const uint8_t *needed,uint32_t n,uint32_t out,uint32_t kind,uint32_t a0,uint32_t b0,uint32_t x,uint32_t *y,uint32_t *work){
    if(!n)return 0;
    *work=0;
    if(kind==1){*y=a0*x+b0;*work=2;return 1;}
    for(uint32_t i=0;i<n;i++)if(needed[i]){
        Node v=nodes[i];uint32_t a=values[v.a],b=values[v.b];
        switch(v.op){
        case INPUT:values[i]=x;break;
        case CONST:values[i]=v.k;break;
        case ADD:values[i]=a+b;break;
        case MUL:values[i]=a*b;break;
        case XOR:values[i]=a^b;break;
        case AND:values[i]=a&b;break;
        case LT:values[i]=a<b;break;
        case SELECT:values[i]=a?b:values[v.c];break;
        }
        *work+=(v.op>=ADD);
    }
    *y=values[out];return 1;
}
static int nav(uint32_t kind,uint32_t a,uint32_t b,uint32_t x,uint64_t n,uint32_t *y,uint32_t *work){
    if(!kind)return 0;
    if(kind==2){*y=shear(shear(x,a)+(uint32_t)n*b,0u-a);*work=12;return 1;}
    *work=0;
    while(n){if(n&1){x=a*x+b;(*work)++;}b=a*b+b;a=a*a;n>>=1;(*work)++;}
    *y=x;return 1;
}

int run(uint32_t x,uint32_t *y,uint32_t *work){
    return evaluate(banks[active],live,count,output,ground,ga,gb,x,y,work);
}
int navigate(uint32_t x,uint64_t n,uint32_t *y,uint32_t *work){return nav(ground,ga,gb,x,n,y,work);}

/* Immutable published graph snapshots; serial authority, no concurrency. */
#define GRAPHS 8u
#define PROCS 64u
#define GEN_MAX 0xffffffu
#define STEP_LIMIT 1024u
typedef struct {Node nodes[CAP];uint8_t needed[CAP];uint32_t n,out,kind,a,b,gen,refs;} Graph;
typedef struct {uint64_t t;uint32_t graph,seed,current,gen;uint8_t used;} Proc;
static Graph graphs[GRAPHS];
static Proc procs[PROCS];
static Graph *graph_lookup(uint32_t h){
    uint32_t i=h&255u;
    if(i>=GRAPHS||!graphs[i].n||graphs[i].gen!=(h>>8))return 0;
    return &graphs[i];
}
static Proc *proc_lookup(uint32_t h){
    uint32_t i=h&255u;
    if(i>=PROCS||!procs[i].used||procs[i].gen!=(h>>8))return 0;
    return &procs[i];
}
uint32_t graph_publish(void){
    if(!count)return 0;
    for(uint32_t i=0;i<GRAPHS;i++)if(!graphs[i].n&&graphs[i].gen<GEN_MAX){
        Graph *g=&graphs[i];
        for(uint32_t j=0;j<count;j++){g->nodes[j]=banks[active][j];g->needed[j]=live[j];}
        g->n=count;g->out=output;g->kind=ground;g->a=ga;g->b=gb;g->refs=0;g->gen++;
        return (g->gen<<8)|i;
    }
    return 0;
}
int graph_release(uint32_t h){Graph *g=graph_lookup(h);if(!g||g->refs)return 0;g->n=0;return 1;}
uint32_t proc_spawn(uint32_t h,uint32_t seed){
    Graph *g=graph_lookup(h);if(!g)return 0;
    for(uint32_t i=0;i<PROCS;i++)if(!procs[i].used&&procs[i].gen<GEN_MAX){
        Proc *p=&procs[i];p->graph=h;p->seed=seed;p->current=g->kind?0:seed;p->t=0;p->gen++;p->used=1;g->refs++;
        return (p->gen<<8)|i;
    }
    return 0;
}
int proc_close(uint32_t h){Proc *p=proc_lookup(h);if(!p)return 0;Graph *g=graph_lookup(p->graph);if(!g)return 0;g->refs--;p->used=0;return 1;}
int proc_seek(uint32_t h,uint64_t t,uint32_t *work){
    Proc *p=proc_lookup(h);if(!p)return 0;Graph *g=graph_lookup(p->graph);if(!g)return 0;
    *work=0;
    if(g->kind){p->t=t;return 1;} /* Structural: no state realization. */
    if(t<p->t||t-p->t>STEP_LIMIT)return 0;
    uint32_t x=p->current,k;
    for(uint64_t i=p->t;i<t;i++){
        if(!evaluate(g->nodes,g->needed,g->n,g->out,0,0,0,x,&x,&k))return 0;
        *work+=k;
    }
    p->current=x;p->t=t;return 1;
}
int proc_read(uint32_t h,uint32_t *y,uint32_t *work){
    Proc *p=proc_lookup(h);if(!p)return 0;Graph *g=graph_lookup(p->graph);if(!g)return 0;
    if(g->kind)return nav(g->kind,g->a,g->b,p->seed,p->t,y,work);
    *y=p->current;*work=0;return 1;
}
/* Checkpoint is a local reconstruction recipe, not a signed claim. */
int proc_checkpoint(uint32_t h,uint32_t *graph,uint32_t *seed,uint64_t *t){
    Proc *p=proc_lookup(h);if(!p)return 0;Graph *g=graph_lookup(p->graph);if(!g||!g->kind)return 0;
    *graph=p->graph;*seed=p->seed;*t=p->t;return 1;
}
uint32_t proc_restore(uint32_t graph,uint32_t seed,uint64_t t){
    Graph *g=graph_lookup(graph);if(!g||!g->kind)return 0;
    uint32_t h=proc_spawn(graph,seed);if(h)proc_lookup(h)->t=t;return h;
}
/* Copy-only inspection, never expose an internal address. */
int graph_info(uint32_t h,uint32_t *n,uint32_t *out,uint32_t *kind,uint32_t *a,uint32_t *b){
    Graph *g=graph_lookup(h);if(!g)return 0;
    *n=g->n;*out=g->out;*kind=g->kind;*a=g->kind?g->a:0;*b=g->kind?g->b:0;return 1;
}
int graph_node(uint32_t h,uint32_t i,Node *node){
    Graph *g=graph_lookup(h);if(!g||i>=g->n)return 0;*node=g->nodes[i];return 1;
}

/* Candidate synthesis is not authority: original graph is checked by admit. */
uint32_t discover_active(void){
    uint32_t y0,y1,w;
    if(!count)return 0;
    if(ground)return ground;
    if(count==16 && admit_chart(banks[active][5].k,banks[active][8].k))return 2;
    if(!evaluate(banks[active],live,count,output,0,0,0,0,&y0,&w) ||
       !evaluate(banks[active],live,count,output,0,0,0,1,&y1,&w))return 0;
    return admit(y1-y0,y0)?1:0;
}

/* Bounded observer features, deliberately lossy; not a proof. */
int graph_features(int32_t *x){
    if(!count)return 0;
    for(uint32_t j=0;j<6;j++)x[j]=0;
    x[3]=(count==16&&output==15)?16:0;x[5]=16;
    for(uint32_t i=0;i<count;i++)if(live[i]){
        Node v=banks[active][i];
        if(v.op==XOR||v.op==AND)x[0]=16;
        if(v.op==LT||v.op==SELECT)x[1]=16;
        if(v.op==MUL){x[5]=0;if(banks[active][v.a].op!=CONST&&banks[active][v.b].op!=CONST)x[2]=16;}
        if(v.op==AND)x[4]=16;
    }return 1;
}
uint32_t try_ground_kind(uint32_t k){
    uint32_t y0,y1,w;
    if(!count||!k)return 0;
    if(k==2)return count==16&&admit_chart(banks[active][5].k,banks[active][8].k)?2:0;
    if(k!=1)return 0;
    if(!evaluate(banks[active],live,count,output,0,0,0,0,&y0,&w)||
       !evaluate(banks[active],live,count,output,0,0,0,1,&y1,&w))return 0;
    return admit(y1-y0,y0)?1:0;
}

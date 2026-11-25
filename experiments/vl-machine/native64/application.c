#include "core.h"
/* Typed bounded straight-line applications. Dependencies are write-once
   registers; no caller-supplied handles, addresses, or executable bytes. */
enum {EMPTY, WORD, GRAPH, PROCESS};
static AppInsn code[APP_CAP];
static uint32_t expected,used,ready;
int app_begin(uint32_t n){ready=0;used=0;expected=n;if(!n||n>APP_CAP)return 0;ready=1;return 1;}
int app_put(uint32_t i,AppInsn x){if(!ready||i!=used||i>=expected||x.op>A_POLICY){ready=0;return 0;}code[used++]=x;return 1;}
typedef AppInsn (*Reader)(uint32_t, const void *);
static AppInsn plain(uint32_t i,const void *ctx){(void)ctx;return code[i];}
static int check(Reader read,const void *ctx,uint32_t count,uint32_t capacity,uint32_t *emitted){
    uint8_t type[APP_REGS]={0};uint32_t emits=0;
    for(uint32_t i=0;i<count;i++){
        AppInsn x=read(i,ctx);uint32_t result=WORD;
        if(x.d>=APP_REGS||x.a>=APP_REGS||x.b>=APP_REGS)return 0;
        switch(x.op){
        case A_CONST:if(x.a||x.b||x.hi)return 0;break;
        case A_BUILD:if(x.d||type[x.a]!=WORD||type[x.b]!=WORD||!x.lo||x.lo>(CAP-3)/2||x.hi)return 0;continue;
        case A_POLICY:case A_LEARN:if(x.a||x.b||x.lo||x.hi)return 0;break;
        case A_PUBLISH:if(x.a||x.b||x.lo||x.hi)return 0;result=GRAPH;break;
        case A_SPAWN:if(type[x.a]!=GRAPH||type[x.b]!=WORD||x.lo||x.hi)return 0;result=PROCESS;break;
        case A_SEEK:if(type[x.a]!=PROCESS||x.b||x.d)return 0;continue;
        case A_READ:if(type[x.a]!=PROCESS||x.b||x.lo||x.hi)return 0;break;
        case A_ADD:case A_MUL:case A_XOR:if(type[x.a]!=WORD||type[x.b]!=WORD||x.lo||x.hi)return 0;break;
        case A_EMIT:if(type[x.a]!=WORD||x.d||x.b||x.lo||x.hi||++emits>capacity)return 0;continue;
        default:return 0;
        }
        if(type[x.d]!=EMPTY)return 0;
        type[x.d]=(uint8_t)result;
    }
    *emitted=emits;return 1;
}
static int build(uint32_t a,uint32_t b,uint32_t depth){
    if(!begin(3+2*depth,2+2*depth)||!put(0,(Node){INPUT,0,0,0,0})||
       !put(1,(Node){CONST,0,0,0,a})||!put(2,(Node){CONST,0,0,0,b}))return 0;
    uint32_t p=0;
    for(uint32_t i=3;i<3+2*depth;i+=2){
        if(!put(i,(Node){MUL,p,1,0,0})||!put(i+1,(Node){ADD,i,2,0,0}))return 0;
        p=i+1;
    }
    return commit();
}
static int execute(Reader read,const void *ctx,uint32_t count,uint32_t *outputs,uint32_t *written){
    uint32_t v[APP_REGS]={0},graphs[APP_REGS],procs[APP_REGS],out[APP_CAP];
    uint32_t ng=0,np=0,no=0,w=0;int ok=0;
    *written=0;
    for(uint32_t i=0;i<count;i++){
        AppInsn x=read(i,ctx);
        switch(x.op){
        case A_CONST:v[x.d]=x.lo;break;
        case A_BUILD:if(!build(v[x.a],v[x.b],x.lo))goto done;break;
        case A_LEARN:v[x.d]=discover_active();break;
        case A_POLICY:if(!nn_policy(&w,&v[x.d]))goto done;break;
        case A_PUBLISH:v[x.d]=graph_publish();if(!v[x.d])goto done;graphs[ng++]=v[x.d];break;
        case A_SPAWN:v[x.d]=proc_spawn(v[x.a],v[x.b]);if(!v[x.d])goto done;procs[np++]=v[x.d];break;
        case A_SEEK:if(!proc_seek(v[x.a],((uint64_t)x.hi<<32)|x.lo,&w))goto done;break;
        case A_READ:if(!proc_read(v[x.a],&v[x.d],&w))goto done;break;
        case A_ADD:v[x.d]=v[x.a]+v[x.b];break;
        case A_MUL:v[x.d]=v[x.a]*v[x.b];break;
        case A_XOR:v[x.d]=v[x.a]^v[x.b];break;
        case A_EMIT:out[no++]=v[x.a];break;
        default:goto done;
        }
    }
    for(uint32_t i=0;i<no;i++)outputs[i]=out[i];
    *written=no;ok=1;
done:
    while(np)proc_close(procs[--np]);
    while(ng)graph_release(graphs[--ng]);
    return ok;
}

int app_execute(uint32_t *outputs,uint32_t capacity,uint32_t *written){
    uint32_t emits;*written=0;
    if(!ready||used!=expected||!check(plain,0,used,capacity,&emits))return 0;
    return execute(plain,0,used,outputs,written);
}
/* A qualified template varies only unrestricted CONST/SEEK immediate bytes.
   All structural fields are statically checked once. No arbitrary code. */
#define T_BYTES 24u
#define T_NONE 255u
typedef struct {AppInsn base[APP_CAP];uint8_t slots[APP_CAP][8];uint32_t n,k,emits;} Template;
static Template templates[2];
static uint32_t tactive,tgen,tused,tstage;
static AppInsn fixed(uint32_t i,const void *ctx){return ((const Template*)ctx)->base[i];}
int tpl_begin(uint32_t n,uint32_t k){
    tstage=0;tused=0;
    if(!n||n>APP_CAP||k>TPL_PARAMS||tgen==0xffffffffu)return 0;
    Template *t=&templates[tactive^1];t->n=n;t->k=k;
    for(uint32_t i=0;i<n;i++)for(uint32_t j=0;j<8;j++)t->slots[i][j]=T_NONE;
    tstage=1;return 1;
}
int tpl_put(uint32_t i,AppInsn x){
    Template *t=&templates[tactive^1];
    if(!tstage||i!=tused||i>=t->n||x.op>A_POLICY){tstage=0;return 0;}
    t->base[tused++]=x;return 1;
}
int tpl_patch(uint32_t pos,uint32_t group){
    Template *t=&templates[tactive^1];uint32_t i=pos/T_BYTES,b=pos%T_BYTES;
    if(!tstage||tused!=t->n||i>=t->n||group>=t->k||b<16){tstage=0;return 0;}
    AppInsn x=t->base[i];uint32_t j=b-16;
    if((x.op!=A_SEEK&&(x.op!=A_CONST||j>=4))||t->slots[i][j]!=T_NONE||(((j<4?x.lo:x.hi)>>((j%4)*8))&255u)){tstage=0;return 0;}
    t->slots[i][j]=(uint8_t)group;return 1;
}
uint32_t tpl_commit(void){
    Template *t=&templates[tactive^1];uint8_t seen[TPL_PARAMS]={0};
    if(!tstage||tused!=t->n)return 0;
    for(uint32_t i=0;i<t->n;i++)for(uint32_t j=0;j<8;j++)if(t->slots[i][j]!=T_NONE)seen[t->slots[i][j]]=1;
    for(uint32_t j=0;j<t->k;j++)if(!seen[j]){tstage=0;return 0;}
    if(!check(fixed,t,t->n,APP_CAP,&t->emits)){tstage=0;return 0;}
    tactive^=1;tgen++;tstage=0;return tgen;
}
typedef struct {const Template *t;const uint8_t *values;} Binding;
static AppInsn bound(uint32_t i,const void *ctx){
    const Binding *b=ctx;AppInsn x=b->t->base[i];
    for(uint32_t j=0;j<8;j++){
        uint8_t g=b->t->slots[i][j];if(g==T_NONE)continue;
        uint32_t v=(uint32_t)b->values[g]<<((j%4)*8);
        if(j<4)x.lo|=v;else x.hi|=v;
    }return x;
}
int tpl_execute(uint32_t generation,const uint8_t *values,uint32_t n,uint32_t *outputs,uint32_t capacity,uint32_t *written){
    *written=0;const Template *t=&templates[tactive];
    if(!tgen||generation!=tgen||n!=t->k||capacity<t->emits||(!values&&n))return 0;
    Binding b={t,values};return execute(bound,&b,t->n,outputs,written);
}

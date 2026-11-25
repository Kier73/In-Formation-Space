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
int run(uint32_t x,uint32_t *y,uint32_t *work){
    if(!count)return 0;
    *work=0;
    if(ground==1){*y=ga*x+gb;*work=2;return 1;}
    for(uint32_t i=0;i<count;i++)if(live[i]){
        Node v=banks[active][i];uint32_t a=values[v.a],b=values[v.b];
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
    *y=values[output];return 1;
}
int navigate(uint32_t x,uint64_t n,uint32_t *y,uint32_t *work){
    if(!ground)return 0;
    if(ground==2){*y=shear(shear(x,ga)+(uint32_t)n*gb,0u-ga);*work=12;return 1;}
    uint32_t a=ga,b=gb;*work=0;
    while(n){if(n&1){x=a*x+b;(*work)++;}b=a*b+b;a=a*a;n>>=1;(*work)++;}
    *y=x;return 1;
}

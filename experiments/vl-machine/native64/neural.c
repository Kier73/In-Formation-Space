#include "core.h"
/* Exact fixed-point 6 -> 8 recurrent -> 3 model, Q4 parameters. */
static int32_t weights[NN_PARAMS],candidate[NN_PARAMS];
static uint32_t loaded,staging,used;
typedef struct {int32_t h[8];uint32_t gen,live;} Session;
static Session sessions[8];
int nn_begin(void){used=0;staging=1;return 1;}
int nn_put(uint32_t i,uint32_t encoded){
    if(!staging||i!=used||i>=NN_PARAMS||encoded>254){staging=0;return 0;}
    candidate[used++]=(int32_t)encoded-127;return 1;
}
int nn_commit(void){
    if(!staging||used!=NN_PARAMS)return 0;
    for(uint32_t i=0;i<8;i++)if(sessions[i].live)return 0;
    for(uint32_t i=0;i<NN_PARAMS;i++)weights[i]=candidate[i];
    staging=0;loaded=1;return 1;
}
static Session *lookup(uint32_t h){uint32_t i=h&255u;return i<8&&sessions[i].live&&sessions[i].gen==(h>>8)?&sessions[i]:0;}
uint32_t nn_open(void){
    if(!loaded)return 0;
    for(uint32_t i=0;i<8;i++)if(!sessions[i].live&&sessions[i].gen<0xffffffu){
        Session *s=&sessions[i];s->gen++;s->live=1;for(uint32_t j=0;j<8;j++)s->h[j]=0;return (s->gen<<8)|i;
    }return 0;
}
int nn_close(uint32_t h){Session *s=lookup(h);if(!s)return 0;s->live=0;return 1;}
static int forward(const int32_t *x,const int32_t *prev,int32_t *next,int32_t *logits){
    if(!loaded)return 0;
    for(uint32_t i=0;i<6;i++)if(x[i]<-127||x[i]>127)return 0;
    for(uint32_t i=0;i<8;i++){
        int32_t z=16*weights[112+i];
        for(uint32_t j=0;j<6;j++)z+=weights[6*i+j]*x[j];
        for(uint32_t j=0;j<8;j++)z+=weights[48+8*i+j]*prev[j];
        z=z/16;next[i]=z<0?0:z>127?127:z;
    }
    for(uint32_t i=0;i<3;i++){
        int32_t z=16*weights[144+i];
        for(uint32_t j=0;j<8;j++)z+=weights[120+8*i+j]*next[j];
        logits[i]=z;
    }return 1;
}
int nn_step(uint32_t h,const int32_t *x,int32_t *logits){
    Session *s=lookup(h);int32_t next[8];if(!s||!forward(x,s->h,next,logits))return 0;
    for(uint32_t i=0;i<8;i++)s->h[i]=next[i];
    return 1;
}
int nn_policy(uint32_t *proposal,uint32_t *admitted){
    int32_t x[6],prev[8]={0},next[8],logits[3];
    if(!graph_features(x)||!forward(x,prev,next,logits))return 0;
    uint32_t k=0;for(uint32_t i=1;i<3;i++)if(logits[i]>logits[k])k=i;
    *proposal=k;*admitted=try_ground_kind(k);return 1;
}

#ifndef VLM_CORE_H
#define VLM_CORE_H
#include <stdint.h>
#define CAP 1024u
enum {INPUT, CONST, ADD, MUL, XOR, AND, LT, SELECT};
typedef struct {uint32_t op,a,b,c,k;} Node;
int begin(uint32_t n,uint32_t out);
int put(uint32_t i,Node v);
int commit(void);
int admit(uint32_t a,uint32_t b);
int admit_chart(uint32_t k,uint32_t d);
int run(uint32_t x,uint32_t *y,uint32_t *work);
int navigate(uint32_t x,uint64_t n,uint32_t *y,uint32_t *work);
uint32_t graph_publish(void);
int graph_release(uint32_t h);
uint32_t proc_spawn(uint32_t graph,uint32_t seed);
int proc_close(uint32_t h);
int proc_seek(uint32_t h,uint64_t t,uint32_t *work);
int proc_read(uint32_t h,uint32_t *y,uint32_t *work);
int proc_checkpoint(uint32_t h,uint32_t *graph,uint32_t *seed,uint64_t *t);
uint32_t proc_restore(uint32_t graph,uint32_t seed,uint64_t t);
int graph_info(uint32_t h,uint32_t *n,uint32_t *out,uint32_t *kind,uint32_t *a,uint32_t *b);
int graph_node(uint32_t h,uint32_t i,Node *node);
uint32_t discover_active(void);
#define APP_CAP 128u
#define APP_REGS 32u
/* Six words: op,destination,source A,source B,immediate low,immediate high. */
typedef struct {uint32_t op,d,a,b,lo,hi;} AppInsn;
enum {A_CONST,A_BUILD,A_LEARN,A_PUBLISH,A_SPAWN,A_SEEK,A_READ,A_ADD,A_MUL,A_XOR,A_EMIT,A_POLICY};
int app_begin(uint32_t n);
int app_put(uint32_t i,AppInsn ins);
int app_execute(uint32_t *outputs,uint32_t capacity,uint32_t *written);
#define NN_PARAMS 147u
int nn_begin(void);
int nn_put(uint32_t i,uint32_t encoded);
int nn_commit(void);
uint32_t nn_open(void);
int nn_close(uint32_t h);
int nn_step(uint32_t h,const int32_t *x,int32_t *logits);
int nn_policy(uint32_t *proposal,uint32_t *admitted);
int graph_features(int32_t *x);
uint32_t try_ground_kind(uint32_t k);
#endif

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
#endif

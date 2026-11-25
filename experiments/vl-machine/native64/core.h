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
int run(uint32_t x,uint32_t *y,uint32_t *work);
int navigate(uint32_t x,uint64_t n,uint32_t *y,uint32_t *work);
#endif

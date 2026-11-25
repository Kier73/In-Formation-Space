#include "core.h"
static void out(uint16_t p,uint8_t v){__asm__ volatile("outb %0,%1"::"a"(v),"Nd"(p));}
static uint8_t in(uint16_t p){uint8_t v;__asm__ volatile("inb %1,%0":"=a"(v):"Nd"(p));return v;}
static void tx(char c){while(!(in(0x3fd)&32)){}out(0x3f8,(uint8_t)c);}
static char rx(void){while(!(in(0x3fd)&1)){}return (char)in(0x3f8);}
static void str(const char *s){while(*s)tx(*s++);}
static void hex(uint32_t x){for(int i=28;i>=0;i-=4)tx("0123456789abcdef"[(x>>i)&15]);}
static int digit(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;return -1;}
static int parse(const char *s,uint32_t *v,unsigned n){
    for(unsigned i=0;i<n;i++){
        uint32_t x=0;
        for(unsigned j=0;j<8;j++){int d=digit(*s);if(d<0)return 0;s++;x=(x<<4)|(unsigned)d;}
        v[i]=x;
    }
    return !*s;
}
void kernel_main(void){
    out(0x3f9,0);out(0x3fb,128);out(0x3f8,1);out(0x3f9,0);out(0x3fb,3);out(0x3fa,199);out(0x3fc,3);
    str("VLM-002 x86-64\n");
    for(;;){
        char buf[64];unsigned n=0;int overflow=0;uint32_t v[6],y,w;int ok=0,res=0;
        str("vl64> ");
        for(;;){char c=rx();if(c=='\n')break;if(n<sizeof(buf)-1)buf[n++]=c;else overflow=1;}
        buf[n]=0;
        if(overflow||!n){str("REJECT\n");continue;}
        switch(buf[0]){
        case 'b':if(parse(buf+1,v,2))ok=begin(v[0],v[1]);break;
        case 'p':if(parse(buf+1,v,6))ok=put(v[0],(Node){v[1],v[2],v[3],v[4],v[5]});break;
        case 'c':if(!buf[1])ok=commit();break;
        case 'g':if(parse(buf+1,v,2))ok=admit(v[0],v[1]);break;
        case 'h':if(parse(buf+1,v,2))ok=admit_chart(v[0],v[1]);break;
        case 'r':if(parse(buf+1,v,1))res=ok=run(v[0],&y,&w);break;
        case 'j':if(parse(buf+1,v,3))res=ok=navigate(v[0],((uint64_t)v[1]<<32)|v[2],&y,&w);break;
        case 'q':if(!buf[1]){out(0xf4,16);for(;;)__asm__ volatile("hlt");}break;
        }
        if(res){str("RESULT ");hex(y);tx(' ');hex(w);tx('\n');}
        else str(ok?"OK\n":"REJECT\n");
    }
}

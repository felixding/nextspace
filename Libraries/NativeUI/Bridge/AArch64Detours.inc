/* Exact-build ARM64 instruction transport, shared by engine adapters.
 * The includer supplies base and writable(). GPL-2.0-or-later. */
struct Detour {uintptr_t offset;const unsigned char *expected;void *replacement;void **original;};
static void immediate(uint32_t **out,unsigned reg,uintptr_t value) {
  *(*out)++=0xd2800000u|((value&65535)<<5)|reg;
  for(unsigned i=1;i<4;i++)*(*out)++=0xf2800000u|(i<<21)|(((value>>(i*16))&65535)<<5)|reg;
}
static void jump(uint32_t **out,uintptr_t destination) {
  immediate(out,17,destination);*(*out)++=0xd65f0220u; /* RET x17 preserves LR. */
}
static int prepare_detours(struct Detour *detours,size_t count) {
  for(unsigned i=0;i<count;i++) {
    struct Detour *d=&detours[i];unsigned char *target=(void *)(base+d->offset);
    if(memcmp(target,d->expected,20))return 0;
    uint32_t *memory=mmap(NULL,getpagesize(),PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(memory==MAP_FAILED)return 0;
    uint32_t *out=memory;*out++=0xd503245f;int terminal=0;
    for(int j=0;j<5;j++) {
      uint32_t instruction;memcpy(&instruction,target+j*4,4);uintptr_t pc=(uintptr_t)target+j*4;
      if((instruction&0x9f000000u)==0x90000000u||(instruction&0x9f000000u)==0x10000000u) {
        int64_t imm=((instruction>>29)&3)|(((instruction>>5)&0x7ffff)<<2);imm=(imm<<43)>>43;
        uintptr_t address=instruction&0x80000000u?(pc&~4095ul)+(imm<<12):pc+imm;
        immediate(&out,instruction&31,address);
      } else if((instruction&0xfc000000u)==0x14000000u) {
        int64_t relative=(int64_t)(instruction&0x3ffffffu)<<38;relative>>=36;
        uintptr_t address=pc+relative;if(address>=(uintptr_t)target&&address<(uintptr_t)target+20)return 0;
        jump(&out,address);terminal=1;break;
      } else if((instruction&0xff000010u)==0x54000000u||
                (instruction&0x7e000000u)==0x34000000u||
                (instruction&0x7e000000u)==0x36000000u) {
        /* Invert the original condition over an absolute jump. Keep the
         * condition/register test intact; no engine behavior is reimplemented. */
        int test_bit=(instruction&0x7e000000u)==0x36000000u;
        if((instruction&0xff000010u)==0x54000000u&&(instruction&15)>=14)return 0;
        uint32_t mask=test_bit?0x3fff:0x7ffff,sign=test_bit?0x2000:0x40000;
        int64_t relative=((int64_t)(((instruction>>5)&mask)^sign)-sign)*4;
        uintptr_t address=pc+relative;
        if(address>=(uintptr_t)target&&address<(uintptr_t)target+20)return 0;
        uint32_t inverted=instruction^((instruction&0xff000010u)==0x54000000u?1u:0x01000000u);
        *out++=(inverted&~(mask<<5))|(6u<<5);
        jump(&out,address);
      } else {
        if((instruction&0x7c000000u)==0x14000000u||(instruction&0xff000010u)==0x54000000u||(instruction&0x7e000000u)==0x34000000u||(instruction&0x7e000000u)==0x36000000u||(instruction&0x3b000000u)==0x18000000u)return 0;
        *out++=instruction;
      }
    }
    if(!terminal)jump(&out,(uintptr_t)target+20);
    __builtin___clear_cache((char *)memory,(char *)out);
    if(mprotect(memory,getpagesize(),PROT_READ|PROT_EXEC))return 0;
    *d->original=memory;
  }
  return 1;
}
static void activate_detours(struct Detour *detours,size_t count) {
  for(unsigned i=0;i<count;i++) {
    struct Detour *d=&detours[i];unsigned char *target=(void *)(base+d->offset);
    const uint32_t instructions[]={0xd503245f,0x58000050,0xd61f0200};
    writable(target,20,PROT_READ|PROT_WRITE|PROT_EXEC);memcpy(target,instructions,12);memcpy(target+12,&d->replacement,8);
    __builtin___clear_cache((char *)target,(char *)target+20);writable(target,20,PROT_READ|PROT_EXEC);
  }
}

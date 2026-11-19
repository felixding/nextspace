/* Dirty-view receipt validation and coalescing. No widget implementation. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../Libraries/NativeUI/Bridge/Protocol.h"
#include "../../Libraries/NativeUI/Bridge/Invalidations.inc"
struct Packet {struct NXSResponse response;uint32_t magic,count;struct NXSDirtyControl rows[NXS_INVALIDATION_LIMIT];};
int main(void)
{
  struct Packet p={.magic=NXS_INVALIDATION_MAGIC};struct NXSInvalidations batch={0};unsigned checks=0;
  p.response.size=sizeof(p.response);
  assert(!native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  batch=(struct NXSInvalidations){0};p.count=UINT32_MAX;p.response.size=sizeof(p.response)+8;
  assert(native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  batch=(struct NXSInvalidations){0};p.count=0;
  assert(native_invalidation_read(&p.response,&batch)&&!batch.all&&!batch.count);checks++;
  p.count=2;p.response.size=sizeof(p.response)+8+2*sizeof(*p.rows);
  p.rows[0]=(struct NXSDirtyControl){.control=10,.kind=7};p.rows[1]=(struct NXSDirtyControl){.control=20,.kind=5};
  assert(native_invalidation_read(&p.response,&batch)&&batch.count==2);checks++;
  assert(native_invalidation_contains(&batch,7,10)&&!native_invalidation_contains(&batch,7,20));checks++;
  p.rows[1]=(struct NXSDirtyControl){.control=30,.kind=2};
  assert(native_invalidation_read(&p.response,&batch)&&batch.count==3);checks++;
  batch=(struct NXSInvalidations){0};p.response.size--;
  assert(!native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  p.response.size++;p.magic=0;batch=(struct NXSInvalidations){0};
  assert(!native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  p.magic=NXS_INVALIDATION_MAGIC;p.rows[0].reserved=1;batch=(struct NXSInvalidations){0};
  assert(!native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  p.rows[0].reserved=0;p.rows[0].control=0;batch=(struct NXSInvalidations){0};
  assert(!native_invalidation_read(&p.response,&batch)&&batch.all);checks++;
  p.count=NXS_INVALIDATION_LIMIT;p.response.size=sizeof(p);
  for(unsigned i=0;i<p.count;i++)p.rows[i]=(struct NXSDirtyControl){.control=i+1,.kind=7};
  batch=(struct NXSInvalidations){0};assert(native_invalidation_read(&p.response,&batch)&&batch.count==p.count);checks++;
  p.count=1;p.response.size=sizeof(p.response)+8+sizeof(*p.rows);p.rows[0].control=NXS_INVALIDATION_LIMIT+1;
  assert(native_invalidation_read(&p.response,&batch)&&batch.all&&!batch.count);checks++;
  printf("{\"checks\":%u,\"legacy_fallback\":true,\"coalescing\":true,\"overflow_resync\":true}\n",checks);
  return 0;
}

/* Native dirty-view receipts, shared by toolkit adapters. No drawing or input
 * policy: the UI library remains the only source of display invalidation. */
#define NXS_INVALIDATION_MAGIC 0x4e584449u
#define NXS_INVALIDATION_LIMIT 1024u
struct NXSDirtyControl {uint64_t control;uint32_t kind,reserved;};
struct NXSInvalidations {unsigned count;int all;struct NXSDirtyControl controls[NXS_INVALIDATION_LIMIT];};
static int native_invalidation_contains(const struct NXSInvalidations *batch,unsigned kind,uint64_t control)
{
  if(batch->all)return 1;
  for(unsigned i=0;i<batch->count;i++)if(batch->controls[i].kind==kind&&batch->controls[i].control==control)return 1;
  return 0;
}
static void native_invalidation_merge(const struct NXSInvalidations *source,struct NXSInvalidations *target)
{
  if(source->all){target->all=1;target->count=0;return;}
  for(unsigned i=0;!target->all&&i<source->count;i++) {
    const struct NXSDirtyControl *item=&source->controls[i];
    if(native_invalidation_contains(target,item->kind,item->control))continue;
    if(target->count==NXS_INVALIDATION_LIMIT){target->all=1;target->count=0;break;}
    target->controls[target->count++]=*item;
  }
}
static int native_invalidation_read(const struct NXSResponse *response,struct NXSInvalidations *target)
{
  if(!response||response->size<sizeof(*response)+8)goto fallback;
  uint32_t header[2];memcpy(header,response+1,sizeof(header));
  if(header[0]!=NXS_INVALIDATION_MAGIC)goto fallback;
  if(header[1]==UINT32_MAX&&response->size==sizeof(*response)+8)goto fallback_supported;
  if(header[1]>NXS_INVALIDATION_LIMIT||response->size!=sizeof(*response)+8+header[1]*sizeof(struct NXSDirtyControl))goto fallback;
  struct NXSInvalidations parsed={0};parsed.count=header[1];
  memcpy(parsed.controls,(const char *)(response+1)+8,parsed.count*sizeof(*parsed.controls));
  for(unsigned i=0;i<parsed.count;i++)if(!parsed.controls[i].control||!parsed.controls[i].kind||parsed.controls[i].kind>64||parsed.controls[i].reserved)goto fallback;
  native_invalidation_merge(&parsed,target);return 1;
 fallback:target->all=1;target->count=0;return 0;
 fallback_supported:target->all=1;target->count=0;return 1;
}

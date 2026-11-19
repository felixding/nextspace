/* Shared application hierarchy serialization. All control behavior stays in
 * the separately loaded native UI provider. GPL-2.0-or-later. */
static char *native_outline_packet(uint64_t control,const NXSOutlineItem *items,unsigned count,double scale,size_t *size_out,unsigned flag_mask)
{
 if(count>4096||(!items&&count))return NULL;
 size_t body=0;
 for(unsigned i=0;i<count;i++) {
  size_t title=items[i].title?strlen(items[i].title):0;
  if(title>65536||sizeof(struct NXSOutlineWireItem)+title>65536-body)return NULL;
  body+=sizeof(struct NXSOutlineWireItem)+title;
 }
 size_t size=sizeof(struct NXSControlListRequest)+body;char *packet=malloc(size);if(!packet)return NULL;
 struct NXSControlListRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=71,.process=identity(),.kind=NXS_OUTLINE,.control=control,.text_size=body,.count=count,.scale=scale};
 memcpy(packet,&request,sizeof(request));size_t offset=sizeof(request);
 for(unsigned i=0;i<count;i++) {
  struct NXSOutlineWireItem item={items[i].identifier,items[i].parent,(items[i].flags&flag_mask),items[i].title?strlen(items[i].title):0};
  memcpy(packet+offset,&item,sizeof(item));offset+=sizeof(item);
  if(item.title_size)memcpy(packet+offset,items[i].title,item.title_size);offset+=item.title_size;
 }
 *size_out=size;return packet;
}

static struct NXSResponse *native_outline_model(uint64_t control,const NXSOutlineItem *items,unsigned count,double scale)
{
 size_t size;char *packet=native_outline_packet(control,items,count,scale,&size,15);if(!packet)return NULL;
 struct NXSResponse *response=exchange_bytes(packet,size);free(packet);
 return response&&response->parts[3].x==1?response:NULL;
}

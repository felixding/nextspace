/* Native item identity transport, shared by engine/toolkit adapters.
 * Hit testing and coordinate policy stay in the UI library. GPL-2.0-or-later. */
static int native_control_item_at_point(unsigned kind,uint64_t control,double x,double y,uint64_t *identifier)
{
  if(!identifier)return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=53,
    .process=identity(),.kind=kind,.control=control,.x=x,.y=y};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1||response->width||response->height||response->stride||
     response->size!=sizeof(*response)+sizeof(*identifier))return 0;
  memcpy(identifier,response+1,sizeof(*identifier));return 1;
}

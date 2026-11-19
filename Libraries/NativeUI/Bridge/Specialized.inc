/* Shared typed models for existing native controls; no UI behavior.
 * Include NativeUI.h, Protocol.h and Transport.inc first. GPL-2.0-or-later. */
static int native_color_sync(uint64_t control,const NXSColorModel *model)
{
  if(!model||model->size<sizeof(*model))return 0;
  struct NXSControlColorRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=55,
    .process=identity(),.kind=NXS_COLORWELL,.control=control,
    .red=model->red,.green=model->green,.blue=model->blue,.alpha=model->alpha};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1;
}
static struct NXSResponse *native_color_get_reply(uint64_t control,NXSColorModel *model)
{
  if(!model||model->size<sizeof(*model))return NULL;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=56,
    .process=identity(),.kind=NXS_COLORWELL,.control=control};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1||response->size!=sizeof(*response)+sizeof(*model))return NULL;
  memcpy(model,response+1,sizeof(*model));return model->size==sizeof(*model)?response:NULL;
}
static int native_color_get(uint64_t control,NXSColorModel *model)
{return native_color_get_reply(control,model)!=NULL;}
static int native_date_sync(uint64_t control,const NXSDateModel *model)
{
  if(!model||model->size<sizeof(*model))return 0;
  struct NXSControlDateRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=57,
    .process=identity(),.kind=NXS_DATEPICKER,.control=control,.flags=model->flags,
    .elements=model->elements,.style=model->style,.value=model->value,.minimum=model->minimum,.maximum=model->maximum};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1;
}
static int native_date_get(uint64_t control,NXSDateModel *model)
{
  if(!model||model->size<sizeof(*model))return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=58,
    .process=identity(),.kind=NXS_DATEPICKER,.control=control};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1||response->size!=sizeof(*response)+sizeof(*model))return 0;
  memcpy(model,response+1,sizeof(*model));return model->size==sizeof(*model);
}

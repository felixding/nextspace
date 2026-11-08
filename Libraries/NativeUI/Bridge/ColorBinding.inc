/* Shared native picker session/model lifetime. Engines keep their original
 * parsing, application events and callbacks. No color UI is implemented here.
 * Include after Specialized.inc. GPL-2.0-or-later. */
struct NXSColorBinding {uint64_t control;uint32_t epoch;NXSColorModel color;int open;};
static int native_color_panel(uint64_t control,int open)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=59,
    .process=identity(),.kind=NXS_COLORWELL,.control=control,.state=!!open};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));return response&&response->parts[3].x==1;
}
static int native_color_binding_open(struct NXSColorBinding *binding,uint64_t control,const NXSColorModel *model)
{
  if(!binding||!control||!native_color_sync(control,model)||!native_color_panel(control,1))return 0;
  *binding=(struct NXSColorBinding){.control=control,.epoch=atomic_load(&native_host_epoch),.color=*model,.open=1};return 1;
}
/* Returns -1 for a lost session, 0 for no change, 1 for new native data.
 * open is sampled with the original native state before engine callbacks. */
static int native_color_binding_poll(struct NXSColorBinding *binding,NXSColorModel *model,int *open)
{
  if(!binding||!binding->open)return -1;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=5,
    .process=identity(),.kind=NXS_COLORWELL,.control=binding->control};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||binding->epoch!=atomic_load(&native_host_epoch)||!response->width)return -1;
  *open=!!response->parts[0].height;*model=(NXSColorModel){.size=sizeof(*model)};
  if(!native_color_get(binding->control,model))return -1;
  int changed=model->red!=binding->color.red||model->green!=binding->color.green||
    model->blue!=binding->color.blue||model->alpha!=binding->color.alpha;
  binding->color=*model;return changed;
}
static void native_color_binding_end(struct NXSColorBinding *binding)
{
  if(!binding||!binding->open)return;
  uint64_t control=binding->control;*binding=(struct NXSColorBinding){0};native_color_panel(control,0);
}

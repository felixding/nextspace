/* Native popup ownership/visibility transport. Placement, windows, input and
 * controls stay in the UI provider. No application model is implemented here.
 * Include after Protocol.h/Transport.inc. GPL-2.0-or-later. */
struct NXSPopupBinding {uint64_t control;uint32_t epoch,kind;int open;};
static int native_popup_binding_bounds(uint32_t kind,uint64_t control,struct NXSRectD bounds)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=13,
    .process=identity(),.kind=kind,.control=control,.x=bounds.x,.y=bounds.y,
    .width=bounds.width,.height=bounds.height};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1;
}
static int native_popup_binding_origin(uint32_t kind,uint64_t control,double x,double y)
{return native_popup_binding_bounds(kind,control,(struct NXSRectD){x,y,0,0});}
static struct NXSResponse *native_popup_visibility(uint32_t kind,uint64_t control,int open)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=14,
    .process=identity(),.kind=kind,.control=control,.state=!!open};
  return exchange_bytes(&request,sizeof(request));
}
static int native_popup_binding_open(struct NXSPopupBinding *binding,uint32_t kind,uint64_t control)
{
  struct NXSResponse *response=native_popup_visibility(kind,control,1);
  if((!response||response->parts[3].x!=1)&&!native_presentation_uncertain(kind,control,14))return 0;
  *binding=(struct NXSPopupBinding){control,atomic_load(&native_host_epoch),kind,1};return 1;
}
static int native_popup_binding_current(const struct NXSPopupBinding *binding)
{return binding&&binding->open&&binding->epoch==atomic_load(&native_host_epoch);}
static int native_popup_binding_poll(struct NXSPopupBinding *binding)
{
  if(!native_popup_binding_current(binding))return -1;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=0,
    .process=identity(),.kind=binding->kind,.control=binding->control};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!native_popup_binding_current(binding))return -1;
  /* A lost read is not a closed native window or a retired source. Retain
   * the acknowledged open session until a real state reply or owner change. */
  if(!response)return 1;
  if(response->parts[3].x!=1)return -1;
  return response->parts[6].width>0&&response->parts[6].height>0;
}
static void native_popup_binding_end(struct NXSPopupBinding *binding)
{
  if(!binding||!binding->open)return;
  struct NXSPopupBinding old=*binding;*binding=(struct NXSPopupBinding){0};
  if(old.epoch==atomic_load(&native_host_epoch))native_popup_visibility(old.kind,old.control,0);
}

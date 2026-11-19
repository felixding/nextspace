/* Shared original-scroller model/input serialization, independent of engines
 * and the GNUstep provider. Include after Protocol.h and Transport.inc. */
struct NXSScrollerBinding {
  uint64_t control;
  double scale;
  uint32_t epoch;
  int horizontal;
};
static int native_scroller_layout(double width,double height,struct NXSRectD *clip)
{
  struct NXSRequest request={.magic=NXS_CHROMIUM_MAGIC,.operation=9,.process=identity(),
    .length=width,.total=height};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[0].width<=0||response->parts[0].height<=0)return 0;
  *clip=response->parts[0];return 1;
}
static int native_scroller_prepare(struct NXSScrollerBinding *binding,double scale)
{
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(binding->epoch==epoch&&binding->scale==scale)return 1;
  struct NXSRequest request={.magic=NXS_CHROMIUM_MAGIC,.operation=8,.process=identity(),
    .control=binding->control,.horizontal=binding->horizontal,.length=scale};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[0].height!=1)return 0;
  binding->scale=scale;binding->epoch=atomic_load(&native_host_epoch);return 1;
}
static struct NXSResponse *native_scroller_model(struct NXSScrollerBinding *binding,
    double length,double total,double page,double value,int pixels)
{
  struct NXSRequest request={.magic=NXS_CHROMIUM_MAGIC,.operation=1,.process=identity(),
    .control=binding->control,.horizontal=binding->horizontal,.layer=!!pixels,
    .length=length,.total=total,.page=page,.value=value};
  return exchange_bytes(&request,sizeof(request));
}
static struct NXSResponse *native_scroller_input(struct NXSScrollerBinding *binding,
    unsigned operation,double x,double y,unsigned modifiers)
{
  struct NXSRequest request={.magic=NXS_CHROMIUM_MAGIC,.operation=operation,.process=identity(),
    .control=binding->control,.horizontal=binding->horizontal,.length=x,.total=y,.page=modifiers};
  return exchange_bytes(&request,sizeof(request));
}
static void native_scroller_retire(struct NXSScrollerBinding *binding)
{
  if(binding->control&&binding->epoch==atomic_load(&native_host_epoch))
    native_scroller_input(binding,6,0,0,0);
  memset(binding,0,sizeof(*binding));
}

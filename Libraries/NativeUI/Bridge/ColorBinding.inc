/* Shared native picker session/model lifetime. Engines keep their original
 * parsing, application events and callbacks. No color UI is implemented here.
 * Include after Specialized.inc. GPL-2.0-or-later. */
struct NXSColorBinding {uint64_t control;uint32_t epoch,token;NXSColorModel color;int open,deferred,borrowed;double actions;};
static int native_color_owner(uint64_t control,uint32_t token,unsigned operation,int publish)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_COLORWELL,.control=control,.x=token,.state=publish};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));return response&&response->parts[3].x==1;
}
static struct NXSResponse *native_color_panel_reply(uint64_t control,int open)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=59,
    .process=identity(),.kind=NXS_COLORWELL,.control=control,.state=!!open};
  return exchange_bytes(&request,sizeof(request));
}
static int native_color_panel(uint64_t control,int open)
{
  struct NXSResponse *response=native_color_panel_reply(control,open);
  return response&&response->parts[3].x==1;
}
static int native_color_panel_reveal(uint64_t control)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=59,
    .process=identity(),.kind=NXS_COLORWELL,.control=control,.state=2};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return (response&&response->parts[3].x==1)||native_presentation_uncertain(NXS_COLORWELL,control,59);
}
static int native_color_binding_open(struct NXSColorBinding *binding,uint64_t control,const NXSColorModel *model)
{
  if(!binding||!control||!native_color_sync(control,model))return 0;
  static _Atomic uint32_t serial;
  uint32_t token;do token=atomic_fetch_add(&serial,1)+1;while(!token);
  int deferred=native_color_owner(control,token,60,2);
  struct NXSResponse *response=native_color_panel_reply(control,1);
  int uncertain=!response&&native_presentation_uncertain(NXS_COLORWELL,control,59);
  if(!uncertain&&(!response||response->parts[3].x!=1)) {
    if(deferred)native_color_owner(control,token,60,0);
    return 0;
  }
  /* The successful presentation reply already contains its original state
   * and action baseline. A later unavailable read cannot undo that success. */
  if(!uncertain&&!response->parts[2].x){native_color_panel(control,0);return 0;}
  *binding=(struct NXSColorBinding){.control=control,.epoch=atomic_load(&native_host_epoch),.token=token,
    .color=*model,.open=1,.deferred=deferred,.actions=response?response->parts[0].width:0};return 1;
}
/* Returns -1 for a lost session, 0 for no change, 1 for new native data.
 * open is sampled with the original native state before engine callbacks. */
static int native_color_binding_poll(struct NXSColorBinding *binding,NXSColorModel *model,int *open)
{
  if(!binding||!binding->open)return -1;
  /* Picker lifetime and actions are native state, independent of whether a
   * new inline-well bitmap is available during an auxiliary-window change. */
  /* Model and action receipt must come from the same native reply. Reading
   * state first can pair an old action count with a newer colour and consume
   * that change without ever forwarding it to the application's model. */
  *model=(NXSColorModel){.size=sizeof(*model)};
  struct NXSResponse *response=native_color_get_reply(binding->control,model);
  if(!response||binding->epoch!=atomic_load(&native_host_epoch)||response->parts[3].x!=1)return -1;
  *open=!!response->parts[0].height;double actions=response->parts[0].width,model_actions=response->parts[2].height;
  int changed=model->red!=binding->color.red||model->green!=binding->color.green||
    model->blue!=binding->color.blue||model->alpha!=binding->color.alpha;
  int native_change=changed&&actions>binding->actions&&actions>model_actions;
  binding->color=*model;binding->actions=actions;return native_change;
}
static void native_color_binding_end(struct NXSColorBinding *binding)
{
  if(!binding||!binding->open)return;
  uint64_t control=binding->control;uint32_t token=binding->token;
  int deferred=binding->deferred&&!binding->borrowed;*binding=(struct NXSColorBinding){0};
  if(deferred) {
    if(!native_color_owner(control,token,67,0))native_color_owner(control,token,60,0);
  }
  else native_color_panel(control,0);
}

/* Shared cross-process references to an existing native color well.
 * The application supplies its own IPC correlation token. No UI is created.
 * Include after ColorBinding.inc. GPL-2.0-or-later. */
static int native_color_binding_borrow(struct NXSColorBinding *binding,uint64_t control,uint32_t token)
{
  if(!native_color_owner(control,token,61,0))return 0;
  NXSColorModel model={.size=sizeof(model)};
  if(!native_color_get(control,&model)){
    native_color_owner(control,0,62,0);return 0;
  }
  struct NXSResponse *response=native_color_panel_reply(control,1);
  if((!response||response->parts[3].x!=1)&&!native_presentation_uncertain(NXS_COLORWELL,control,59)){native_color_owner(control,0,62,0);return 0;}
  *binding=(struct NXSColorBinding){.control=control,.epoch=atomic_load(&native_host_epoch),.color=model,.open=1,.borrowed=1,.actions=response?response->parts[0].width:0};return 1;
}
static void native_color_binding_return(struct NXSColorBinding *binding)
{
  uint64_t control=binding->control;native_color_binding_end(binding);
  if(control)native_color_owner(control,0,62,0);
}

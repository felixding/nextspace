/* Original Ozone input metadata to shared standard activation transport. */
#include "pinned-wayland-input.h"
struct OzoneActivationToken {
  struct OzoneActivationToken *next;
  struct OzoneGeometryWindow *entry;
  uint32_t serial;
  uint32_t ticket;
  uint64_t generation;
};
struct OzoneActivationFocus {
  struct OzoneActivationFocus *next;
  void *device,*window;
  int keyboard;
};
static struct OzoneActivationFocus *ozone_activation_focus;
static struct OzoneGeometryWindow *ozone_activation_source;
static uint32_t ozone_activation_serial;
static uint64_t ozone_activation_generation;
static int ozone_activation_fd=-1;
static unsigned ozone_activation_watch;
static uint32_t ozone_activation_epoch;
static void (*original_wayland_pointer_enter)(void *,void *,uint32_t,void *,int32_t,int32_t);
static void (*original_wayland_pointer_leave)(void *,void *,uint32_t,void *);
static void (*original_wayland_pointer_button)(void *,void *,uint32_t,uint32_t,uint32_t,uint32_t);
static void (*original_wayland_keyboard_enter)(void *,void *,uint32_t,void *,void *);
static void (*original_wayland_keyboard_leave)(void *,void *,uint32_t,void *);
static void (*original_wayland_keyboard_key)(void *,void *,uint32_t,uint32_t,uint32_t,uint32_t);
static int wayland_activation_prepared;
static void ozone_activation_focus_leave(void *device,int keyboard)
{
  struct OzoneActivationFocus **link=&ozone_activation_focus;
  while(*link) {
    struct OzoneActivationFocus *entry=*link;
    if(entry->device==device&&entry->keyboard==keyboard){*link=entry->next;free(entry);return;}
    link=&entry->next;
  }
}
static void ozone_activation_focus_enter(void *device,int keyboard,void *surface)
{
  ozone_activation_focus_leave(device,keyboard);
  /* Same pinned original wl::RootWindowFromWlSurface metadata loads. No
   * widget layout, focus decision or input interpretation is copied. */
  void *native_surface=surface?ozone_field(surface,48):NULL;
  void *window=native_surface?ozone_field(native_surface,824):NULL;
  if(!window)return;
  struct OzoneGeometryWindow *owner=ozone_geometry_windows;
  while(owner&&owner->window!=window)owner=owner->next;
  if(!owner)return;
  struct OzoneActivationFocus *entry=calloc(1,sizeof(*entry));if(!entry)return;
  *entry=(struct OzoneActivationFocus){ozone_activation_focus,device,window,keyboard};ozone_activation_focus=entry;
}
static void ozone_activation_ready(void *context,const char *token)
{
  struct OzoneActivationToken *request=context;
  struct OzoneGeometryWindow *entry=request->entry;
  struct OzoneActivationToken **link=&entry->tokens;
  while(*link&&*link!=request)link=&(*link)->next;
  if(*link)*link=request->next;
  uint32_t serial=request->serial,ticket=request->ticket;
  int current=request->generation==ozone_activation_generation&&entry==ozone_activation_source;
  free(request);
  entry->depth++;
  int accepted=current&&native_auxiliary_token_publish_query((uintptr_t)entry->window,serial,token,
    wayland_surface_parent?wayland_surface_parent(entry->observation):NULL,ticket);
  if(log_fd>=0)dprintf(log_fd,"%d original Wayland activation token queued=%d serial=%u request=%u\n",getpid(),accepted,serial,ticket);
  if(!--entry->depth&&entry->retired)free(entry);
}
/* Reuse the shared broker's presentation request. Ozone still owns the real
 * source/serial and the shared Wayland transport creates the original token.
 * Minting at input caches an expiring grant while rendering can be delayed. */
static int ozone_activation_requested(int descriptor,unsigned condition,void *unused)
{
  if(descriptor!=ozone_activation_fd)return 0;
  if(condition&(8|16|32)) {close(ozone_activation_fd);ozone_activation_fd=-1;ozone_activation_watch=0;return 0;}
  uint64_t ticket=0;
  if(recv(descriptor,&ticket,sizeof(ticket),MSG_DONTWAIT)!=sizeof(ticket)||!ticket||ticket>UINT32_MAX)return 1;
  struct OzoneGeometryWindow *entry=ozone_activation_source;
  if(!entry||entry->retired||!entry->observation)return 1;
  struct OzoneActivationToken *request=calloc(1,sizeof(*request));if(!request)return 1;
  *request=(struct OzoneActivationToken){.entry=entry,.serial=ozone_activation_serial,
    .ticket=ticket,.generation=ozone_activation_generation};
  if(!wayland_request_activation(entry->observation,NULL,request->serial,ozone_activation_ready,request)){free(request);return 1;}
  request->next=entry->tokens;entry->tokens=request;
  return 1;
}
static int ozone_activation_ensure_watch(void)
{
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(ozone_activation_watch&&ozone_activation_epoch==epoch)return 1;
  unsigned (*add)(int,unsigned,int (*)(int,unsigned,void *),void *)=dlsym(RTLD_DEFAULT,"g_unix_fd_add");
  int (*remove)(unsigned)=dlsym(RTLD_DEFAULT,"g_source_remove");
  if(!add||!remove)return 0;
  if(ozone_activation_watch)remove(ozone_activation_watch);
  ozone_activation_watch=0;
  if(ozone_activation_fd>=0)close(ozone_activation_fd);
  ozone_activation_fd=native_auxiliary_source_watch();ozone_activation_epoch=epoch;
  if(ozone_activation_fd<0)return 0;
  ozone_activation_watch=add(ozone_activation_fd,1|8|16,ozone_activation_requested,NULL);
  if(!ozone_activation_watch){close(ozone_activation_fd);ozone_activation_fd=-1;return 0;}
  return 1;
}
static void ozone_activation_input(void *device,int keyboard,uint32_t serial,uint32_t state)
{
  if(state!=1)return;
  struct OzoneActivationFocus *focus=ozone_activation_focus;
  while(focus&&!(focus->device==device&&focus->keyboard==keyboard))focus=focus->next;
  if(!focus)return;
  struct OzoneGeometryWindow *entry=ozone_geometry_windows;
  while(entry&&entry->window!=focus->window)entry=entry->next;
  if(!entry||!entry->observation)return;
  if(!keyboard)native_auxiliary_source_pointer((uintptr_t)entry->window);
  ozone_activation_source=entry;ozone_activation_serial=serial;ozone_activation_generation++;
  if(ozone_activation_ensure_watch())
    native_auxiliary_token_publish((uintptr_t)entry->window,0,NULL,NULL);
}
static void ozone_activation_retire(struct OzoneGeometryWindow *entry)
{
  if(ozone_activation_source==entry){ozone_activation_source=NULL;ozone_activation_generation++;}
  while(entry->tokens){struct OzoneActivationToken *token=entry->tokens;entry->tokens=token->next;free(token);}
  struct OzoneActivationFocus **link=&ozone_activation_focus;
  while(*link) {
    struct OzoneActivationFocus *focus=*link;
    if(focus->window==entry->window){*link=focus->next;free(focus);}else link=&focus->next;
  }
}
static void native_wayland_pointer_enter(void *data,void *pointer,uint32_t serial,void *surface,int32_t x,int32_t y)
{ozone_activation_focus_enter(data,0,surface);original_wayland_pointer_enter(data,pointer,serial,surface,x,y);}
static void native_wayland_pointer_leave(void *data,void *pointer,uint32_t serial,void *surface)
{ozone_activation_focus_leave(data,0);original_wayland_pointer_leave(data,pointer,serial,surface);}
static void native_wayland_pointer_button(void *data,void *pointer,uint32_t serial,uint32_t time,uint32_t button,uint32_t state)
{ozone_activation_input(data,0,serial,state);original_wayland_pointer_button(data,pointer,serial,time,button,state);}
static void native_wayland_keyboard_enter(void *data,void *keyboard,uint32_t serial,void *surface,void *keys)
{ozone_activation_focus_enter(data,1,surface);original_wayland_keyboard_enter(data,keyboard,serial,surface,keys);}
static void native_wayland_keyboard_leave(void *data,void *keyboard,uint32_t serial,void *surface)
{ozone_activation_focus_leave(data,1);original_wayland_keyboard_leave(data,keyboard,serial,surface);}
static void native_wayland_keyboard_key(void *data,void *keyboard,uint32_t serial,uint32_t time,uint32_t key,uint32_t state)
{ozone_activation_input(data,1,serial,state);original_wayland_keyboard_key(data,keyboard,serial,time,key,state);}
static struct Detour wayland_activation_detours[]={
 {NXS_WAYLAND_POINTER_ENTER,wayland_pointer_enter_bytes,native_wayland_pointer_enter,(void **)&original_wayland_pointer_enter},
 {NXS_WAYLAND_POINTER_LEAVE,wayland_pointer_leave_bytes,native_wayland_pointer_leave,(void **)&original_wayland_pointer_leave},
 {NXS_WAYLAND_POINTER_BUTTON,wayland_pointer_button_bytes,native_wayland_pointer_button,(void **)&original_wayland_pointer_button},
 {NXS_WAYLAND_KEYBOARD_ENTER,wayland_keyboard_enter_bytes,native_wayland_keyboard_enter,(void **)&original_wayland_keyboard_enter},
 {NXS_WAYLAND_KEYBOARD_LEAVE,wayland_keyboard_leave_bytes,native_wayland_keyboard_leave,(void **)&original_wayland_keyboard_leave},
 {NXS_WAYLAND_KEYBOARD_KEY,wayland_keyboard_key_bytes,native_wayland_keyboard_key,(void **)&original_wayland_keyboard_key}
};
static void prepare_wayland_activation(void)
{
  if(!wayland_auxiliary_capabilities||!wayland_request_activation)return;
  if(memcmp((void *)(base+NXS_WAYLAND_INPUT_SURFACE_FIELDS),wayland_input_surface_fields_bytes,20)||
     !prepare_detours(wayland_activation_detours,sizeof(wayland_activation_detours)/sizeof(*wayland_activation_detours))) {
    note("Wayland input metadata guard failed; no activation tokens published");return;
  }
  wayland_activation_prepared=1;
}
static void activate_wayland_activation(void)
{
  if(!wayland_activation_prepared)return;
  activate_detours(wayland_activation_detours,sizeof(wayland_activation_detours)/sizeof(*wayland_activation_detours));
  note("original Wayland input activation handoff enabled");
}

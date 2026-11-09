/* Ozone object lifetime and original bounds adaptation only. The shared
 * transport owns all Wayland protocol/queue work. No browser UI is replaced. */
#include "pinned-wayland-geometry.h"
#include "../../Libraries/NativeUI/Bridge/WaylandGeometry.h"
static NXSGeometryDisplay *(*wayland_connect)(struct wl_display *,struct wl_display *,const NXSWaylandClientAPI *);
static void (*wayland_disconnect)(NXSGeometryDisplay *,int);
static NXSGeometrySurface *(*wayland_observe)(NXSGeometryDisplay *,struct wl_surface *,NXSGeometryChanged,void *);
static void (*wayland_rebind)(NXSGeometrySurface *,struct wl_surface *);
static void (*wayland_unobserve)(NXSGeometrySurface *);
static int (*wayland_read)(NXSGeometrySurface *,NXSWaylandSurfaceGeometry *);
static int (*wayland_request_activation)(NXSGeometrySurface *,struct wl_seat *,uint32_t,NXSWaylandActivationToken,void *);
static unsigned wayland_auxiliary_capabilities;
struct OzoneActivationToken;
static void (*original_wayland_show)(void *,int);
static void (*original_wayland_destroy)(void *);
static void (*original_wayland_connection_destroy)(void *);
struct OzoneGeometryDisplay {
  struct OzoneGeometryDisplay *next;
  void *connection;
  NXSGeometryDisplay *transport;
};
struct OzoneGeometryWindow {
  struct OzoneGeometryWindow *next;
  struct OzoneGeometryDisplay *display;
  void *window;
  NXSGeometrySurface *observation;
  unsigned depth;
  int retired;
  struct OzoneActivationToken *tokens;
};
static struct OzoneGeometryDisplay *ozone_geometry_displays;
static struct OzoneGeometryWindow *ozone_geometry_windows;
static void *ozone_field(void *object,size_t offset) {return *(void **)((char *)object+offset);}
#include "wayland-activation.inc"
static void ozone_geometry_changed(void *context)
{
  struct OzoneGeometryWindow *entry=context;
  NXSWaylandSurfaceGeometry geometry;
  if(entry->retired||!wayland_read(entry->observation,&geometry)||!geometry.mapped)return;
  typedef struct Rect (*GetBounds)(const void *);
  struct Rect bounds=((GetBounds)(base+NXS_WAYLAND_GET_BOUNDS))(entry->window);
  if(bounds.x==geometry.x&&bounds.y==geometry.y)return;
  bounds.x=geometry.x;bounds.y=geometry.y;
  entry->depth++;
  if(log_fd>=0)dprintf(log_fd,"%d native Wayland origin %p %d,%d %dx%d\n",getpid(),entry->window,bounds.x,bounds.y,bounds.width,bounds.height);
  /* Preserve original requested/applied-state sequencing and notifications to
   * the browser/renderer, including the original delegate's weak lifetime. */
  ((void (*)(void *,const struct Rect *))(base+NXS_WAYLAND_SET_BOUNDS))(entry->window,&bounds);
  if(!--entry->depth&&entry->retired)free(entry);
}
static void ozone_geometry_retire(struct OzoneGeometryWindow *entry)
{
  struct OzoneGeometryWindow **link=&ozone_geometry_windows;
  while(*link&&*link!=entry)link=&(*link)->next;
  if(*link)*link=entry->next;
  if(entry->observation)wayland_unobserve(entry->observation);
  ozone_activation_retire(entry);
  entry->observation=NULL;entry->retired=1;
  if(!entry->depth)free(entry);
}
static void ozone_geometry_attach(struct OzoneGeometryWindow *entry)
{
  void *window=entry->window;
  if(*(uintptr_t *)window!=base+NXS_WAYLAND_TOPLEVEL_VTABLE) {
    if(log_fd>=0)dprintf(log_fd,"%d native Wayland non-toplevel vtable %#lx\n",getpid(),*(uintptr_t *)window-base);
    return;
  }
  void *connection=ozone_field(window,NXS_WAYLAND_WINDOW_CONNECTION);
  void *surface=ozone_field(window,NXS_WAYLAND_WINDOW_SURFACE);
  struct wl_surface *proxy=surface?ozone_field(surface,NXS_WAYLAND_SURFACE_PROXY):NULL;
  if(log_fd>=0)dprintf(log_fd,"%d native Wayland attach window=%p connection=%p surface=%p proxy=%p\n",getpid(),window,connection,surface,proxy);
  if(!connection||!proxy)return;
  struct OzoneGeometryDisplay *display=ozone_geometry_displays;
  while(display&&display->connection!=connection)display=display->next;
  if(!display) {
    struct wl_display *raw=ozone_field(connection,NXS_WAYLAND_CONNECTION_DISPLAY);
    struct wl_display *wrapper=ozone_field(connection,NXS_WAYLAND_CONNECTION_WRAPPER);
    if(!raw||!wrapper)return;
    display=calloc(1,sizeof(*display));if(!display)return;
    const NXSWaylandClientAPI api={sizeof(api),
      (void *)(base+NXS_WAYLAND_MARSHAL),(void *)(base+NXS_WAYLAND_ADD_LISTENER),
      (void *)(base+NXS_WAYLAND_PROXY_DESTROY),(void *)(base+NXS_WAYLAND_FLUSH)};
    display->transport=wayland_connect(raw,wrapper,&api);
    if(!display->transport){free(display);return;}
    display->connection=connection;display->next=ozone_geometry_displays;ozone_geometry_displays=display;
  }
  entry->display=display;
  if(entry->observation)wayland_rebind(entry->observation,proxy);
  else entry->observation=wayland_observe(display->transport,proxy,ozone_geometry_changed,entry);
}
static void native_wayland_show(void *window,int inactive)
{
  note("native Wayland toplevel Show");
  struct OzoneGeometryWindow *entry=ozone_geometry_windows;
  while(entry&&entry->window!=window)entry=entry->next;
  if(!entry) {
    entry=calloc(1,sizeof(*entry));
    if(!entry){original_wayland_show(window,inactive);return;}
    entry->window=window;entry->next=ozone_geometry_windows;ozone_geometry_windows=entry;
  }
  entry->depth++;
  /* The original Show creates the xdg_toplevel role before observation. Its
   * delegate may synchronously destroy the window, which retires this entry. */
  original_wayland_show(window,inactive);
  if(!entry->retired)ozone_geometry_attach(entry);
  if(!--entry->depth&&entry->retired)free(entry);
}
static void native_wayland_destroy(void *window)
{
  struct OzoneGeometryWindow *entry=ozone_geometry_windows;
  while(entry&&entry->window!=window)entry=entry->next;
  if(entry)ozone_geometry_retire(entry);
  original_wayland_destroy(window);
}
static void native_wayland_connection_destroy(void *connection)
{
  struct OzoneGeometryDisplay **link=&ozone_geometry_displays;
  while(*link&&(*link)->connection!=connection)link=&(*link)->next;
  if(*link) {
    struct OzoneGeometryDisplay *display=*link;*link=display->next;
    struct OzoneGeometryWindow *entry=ozone_geometry_windows;
    while(entry) {
      struct OzoneGeometryWindow *next=entry->next;
      if(entry->display==display)ozone_geometry_retire(entry);
      entry=next;
    }
    wayland_disconnect(display->transport,1);free(display);
  }
  original_wayland_connection_destroy(connection);
}
static struct Detour wayland_geometry_detours[]={
  {NXS_WAYLAND_SHOW,wayland_show_bytes,native_wayland_show,(void **)&original_wayland_show},
  {NXS_WAYLAND_DESTROY,wayland_destroy_bytes,native_wayland_destroy,(void **)&original_wayland_destroy},
  {NXS_WAYLAND_CONNECTION_DESTROY,wayland_connection_destroy_bytes,native_wayland_connection_destroy,(void **)&original_wayland_connection_destroy}
};
static int prepare_wayland_geometry(void)
{
  const char *path=getenv("NEXTSPACE_WAYLAND_GEOMETRY_LIBRARY");
  if(!path||!*path)return 0;
  if(memcmp((void *)(base+NXS_WAYLAND_GET_BOUNDS),wayland_get_bounds_bytes,16)||
     memcmp((void *)(base+NXS_WAYLAND_SET_BOUNDS),wayland_set_bounds_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_WINDOW_FIELDS),wayland_window_fields_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_SURFACE_FIELDS),wayland_surface_fields_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_DISPLAY_FIELDS),wayland_display_fields_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_MARSHAL),wayland_marshal_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_ADD_LISTENER),wayland_add_listener_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_PROXY_DESTROY),wayland_proxy_destroy_bytes,20)||
     memcmp((void *)(base+NXS_WAYLAND_FLUSH),wayland_flush_bytes,20)) {
    note("Wayland geometry field guard failed; ordinary origin retained");return 0;
  }
  void *library=dlopen(path,RTLD_NOW|RTLD_LOCAL);
  if(!library){note("Wayland geometry transport unavailable; ordinary origin retained");return 0;}
  wayland_connect=dlsym(library,"nxs_wayland_geometry_connect_with_api");
  wayland_disconnect=dlsym(library,"nxs_wayland_geometry_disconnect");
  wayland_observe=dlsym(library,"nxs_wayland_geometry_observe");
  wayland_rebind=dlsym(library,"nxs_wayland_geometry_rebind");
  wayland_unobserve=dlsym(library,"nxs_wayland_geometry_unobserve");
  wayland_read=dlsym(library,"nxs_wayland_geometry_read");
  if(!wayland_connect||!wayland_disconnect||!wayland_observe||!wayland_rebind||!wayland_unobserve||!wayland_read||
     !prepare_detours(wayland_geometry_detours,sizeof(wayland_geometry_detours)/sizeof(*wayland_geometry_detours))) {
    note("Wayland geometry lifetime guard failed; ordinary origin retained");return 0;
  }
  wayland_request_activation=dlsym(library,"nxs_wayland_activation_request");
  prepare_wayland_activation();
  return 1;
}

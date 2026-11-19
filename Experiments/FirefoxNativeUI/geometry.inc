/* Compositor geometry supplies the origin; Gecko retains bounds/margin logic,
 * lifecycle notifications and parent-to-content-process dimension transport. */
#include "../../Libraries/NativeUI/Bridge/Gtk3Geometry.h"
#include "pinned-geometry.h"
/* Nontrivial nsRect has the original indirect-result ABI. */
__attribute__((naked)) static void geometry_client_rect(void *function,void *frame,void *output)
{__asm__("mov x16,x0\nmov x0,x1\nmov x8,x2\nbr x16");}
static int gecko_frame_device_origin(void *frame,double *x,double *y)
{
  if(!frame||!guard_frame_geometry_calls())return 0;
  void *root=((void *(*)(void *))(base+NXS_GECKO_GEOMETRY_ROOT_FRAME))(frame);
  if(!root)return 0;
  /* GetScreenRect returns rounded CSS pixels. Use the original full-precision
   * app-unit getter so screen and client bounds share a unit before transport. */
  int screen[4]={0};geometry_client_rect((void *)(base+NXS_GECKO_GEOMETRY_SCREEN_APP_UNITS),root,screen);
  int bounds[4]={0};geometry_client_rect((void *)(base+NXS_GECKO_GEOMETRY_CLIENT_RECT),frame,bounds);
  *x=(screen[0]+(double)bounds[0])/frame_units(frame);*y=(screen[1]+(double)bounds[1])/frame_units(frame);
  return isfinite(*x)&&isfinite(*y);
}
static int gecko_frame_screen_origin(void *frame,double *x,double *y)
{
  if(!gecko_frame_device_origin(frame,x,y))return 0;
  double device=60./frame_units(frame);*x/=device;*y/=device;return 1;
}
static int gecko_frame_screen_bounds(void *frame,struct NXSRectD *bounds)
{
  if(!frame||!bounds||!guard_projected_geometry_calls())return 0;
  void *context=*(void **)((char *)frame+40);
  void *device=context?*(void **)((char *)context+48):NULL;
  int units=device?((int (*)(const void *))(base+NXS_GECKO_CHROME_PIXEL_UNITS))(device):0;
  if(units<=0)return 0;
  void *node=*(void **)((char *)frame+24);if(!node)return 0;
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  double desktop=0;void *inner=gecko_node_owner_inner(node);
  if(inner) {
    ptrdiff_t offset=((const ptrdiff_t *)*(uintptr_t **)inner)[-2];
    if(offset<=0&&offset>=-1024) {
      struct GeckoError error={0};
      desktop=((double (*)(void *,struct GeckoError *))(base+NXS_GECKO_DESKTOP_SCALE))((char *)inner+offset,&error);
      if(error.result){clear_text_error(&error);desktop=0;}
    }
    gecko_release_window(inner);
  }
  void *window=gecko_node_owner_window(node),*rect=NULL;int okay=0;
  if(window&&isfinite(desktop)&&desktop>0) {
    /* nsPIDOMWindowOuter is a secondary base. Use its original Itanium ABI
     * offset-to-top; WindowUtils belongs to the complete EventTarget object. */
    ptrdiff_t offset=((const ptrdiff_t *)*(uintptr_t **)window)[-2];
    if(offset<=0&&offset>=-1024) {
      void *outer=(char *)window+offset;
      if(((const ptrdiff_t *)*(uintptr_t **)outer)[-2]==0) {
        void *utils=((void *(*)(void *))(base+NXS_GECKO_WINDOW_UTILS))(outer);
        if(utils) {
          uint32_t result=((uint32_t (*)(void *,void *,void **))(base+NXS_GECKO_ELEMENT_SCREEN_RECT))(utils,node,&rect);
          if(!(result&0x80000000u)&&rect) {
            memcpy(bounds,(char *)rect+48,sizeof(*bounds));
            /* Original screen rects use quantized chrome CSS units. Native
             * windows use desktop units. Their original platform scales are
             * independent, even with no page zoom (e.g. app-unit rounding). */
            double factor=60./units/desktop;
            bounds->x*=factor;bounds->y*=factor;bounds->width*=factor;bounds->height*=factor;
            okay=isfinite(bounds->x)&&isfinite(bounds->y)&&isfinite(bounds->width)&&isfinite(bounds->height)&&
              bounds->width>0&&bounds->height>0;
          }
        }
      }
    }
  }
  if(rect)((unsigned (*)(void *))(base+NXS_GECKO_DOM_RECT_RELEASE))(rect);
  gecko_release_window(window);((unsigned (*)(void *))(base+0x47ba6b8))(node);
  return okay;
}
static int gecko_frame_pixel_rect(void *frame,struct NXSRectD *rect)
{
  double x,y;if(!gecko_frame_device_origin(frame,&x,&y))return 0;
  double left=floor(x+rect->x+.5),top=floor(y+rect->y+.5);
  double right=floor(x+rect->x+rect->width+.5),bottom=floor(y+rect->y+rect->height+.5);
  *rect=(struct NXSRectD){left-floor(x+.5),top-floor(y+.5),right-left,bottom-top};
  return 1;
}
struct GeckoWindowBounds {int32_t client[4], margin[4];};
_Static_assert(sizeof(struct GeckoWindowBounds)==32,"Pinned Gecko Bounds ABI");
static struct GeckoWindowBounds (*original_geometry_compute)(const void *);
static int (*gtk_surface_geometry)(void *,NXSGtk3SurfaceGeometry *,NXSGtk3GeometryChanged);
static const char *(*gtk_surface_parent)(uintptr_t);
static int (*gtk_activation_request)(void);
static uint32_t gtk_activation_query;
static int gtk_activation_descriptor=-1,gtk_activation_requested_mode;
static unsigned (*gtk_activation_watch)(int,int,unsigned,int (*)(int,unsigned,void *),void *,void (*)(void *));
static int gtk_activation_source_attach(void);
static void gtk_source_pointer(uintptr_t surface,void *context)
{(void)context;native_auxiliary_source_pointer(surface);}
static void gtk_activation_token(uintptr_t surface,const char *token,void *context)
{
  if(!token) {
    gtk_activation_query=0;
    /* Session recovery keeps the browser connection. Re-register the private
     * request endpoint on the next real gesture after its old host exits. */
    if(gtk_activation_requested_mode&&gtk_activation_descriptor<0)gtk_activation_source_attach();
  }
  int accepted=native_auxiliary_token_publish_query(surface,0,token,token&&gtk_surface_parent?gtk_surface_parent(surface):NULL,token?gtk_activation_query:0);
  if(token)gtk_activation_query=0;
  if(log_fd>=0)dprintf(log_fd,"%d original GTK activation %s queued=%d\n",getpid(),token?"token":"reset",accepted);
  if(log_fd>=0&&getenv("NEXTSPACE_TRACE_NATIVE_RPC")) {
    struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
    dprintf(log_fd,"%d native activation publish %s at=%ld.%09ld\n",getpid(),token?"token":"reset",now.tv_sec,now.tv_nsec);
  }
}
static int gtk_activation_source_ready(int descriptor,unsigned condition,void *unused)
{
  if(condition&~1u){close(descriptor);gtk_activation_descriptor=-1;gtk_activation_query=0;return 0;}
  uint64_t query=0;ssize_t size;
  while((size=recv(descriptor,&query,sizeof(query),MSG_DONTWAIT|MSG_TRUNC))>0) {
    if(size!=sizeof(query)||!query||query>UINT32_MAX)continue;
    gtk_activation_query=query;
    if(!gtk_activation_request())gtk_activation_query=0;
  }
  if(!size){close(descriptor);gtk_activation_descriptor=-1;gtk_activation_query=0;return 0;}
  return 1;
}
static int gtk_activation_source_attach(void)
{
  int descriptor=native_auxiliary_source_watch();if(descriptor<0)return 0;
  if(!gtk_activation_watch(0,descriptor,1u|8u|16u|32u,gtk_activation_source_ready,NULL,NULL)) {
    close(descriptor);return 0;
  }
  gtk_activation_descriptor=descriptor;return 1;
}
static void geometry_changed(void *gdk_window) {
  void *window=((void *(*)(void *))(base+NXS_GECKO_GEOMETRY_FROM_WINDOW))(gdk_window);
  if(!window)return;
  ((unsigned (*)(void *))(base+NXS_GECKO_GEOMETRY_ADDREF))(window);
  ((void (*)(void *,int))(base+NXS_GECKO_GEOMETRY_RECOMPUTE))(window,0);
  ((unsigned (*)(void *))(base+NXS_GECKO_GEOMETRY_RELEASE))(window);
}
static struct GeckoWindowBounds geometry_compute(const void *window) {
  struct GeckoWindowBounds result=original_geometry_compute(window);
  void *gdk=((void *(*)(const void *))(base+NXS_GECKO_GEOMETRY_TOPLEVEL))(window);
  NXSGtk3SurfaceGeometry geometry;
  if(gdk&&gtk_surface_geometry(gdk,&geometry,geometry_changed)&&geometry.mapped) {
    result.client[0]+=geometry.x;result.client[1]+=geometry.y;
    if(log_fd>=0)dprintf(log_fd,"surface-geometry origin=%d,%d client=%d,%d %dx%d\n",
      geometry.x,geometry.y,result.client[0],result.client[1],result.client[2],result.client[3]);
  }
  return result;
}
static struct Detour geometry_detours[]={
 {NXS_GECKO_GEOMETRY_COMPUTE,gecko_geometry_compute_bytes,geometry_compute,(void **)&original_geometry_compute}
};
static void activate_popup_geometry(void)
{
  /* Remove only the original zero-origin shortcuts. All parent discovery and
   * coordinate arithmetic remains in Gecko, for every popup and density. */
  unsigned char *begin=(void *)(base+NXS_GECKO_POPUP_ANCHOR_PARENT);
  size_t size=NXS_GECKO_POPUP_PARENT_POSITION+sizeof(gecko_popup_parent_position_words)-NXS_GECKO_POPUP_ANCHOR_PARENT;
  writable(begin,size,PROT_READ|PROT_WRITE|PROT_EXEC);
  for(unsigned i=3;i<=5;i++)
    ((uint32_t *)begin)[i]=0xd503201f; /* NOP: always subtract the real parent. */
  ((uint32_t *)(base+NXS_GECKO_POPUP_PARENT_POSITION))[2]=0xd503201f;
  __builtin___clear_cache((char *)begin,(char *)begin+size);
  writable(begin,size,PROT_READ|PROT_EXEC);
}
static int prepare_geometry(void) {
  const char *path=getenv("NEXTSPACE_GTK3_GEOMETRY_LIBRARY");if(!path||!*path)return 1;
  void *library=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!library)return 0;
  gtk_surface_geometry=dlsym(library,"nxs_gtk3_surface_geometry");
  gtk_surface_parent=dlsym(library,"nxs_gtk3_surface_parent");
  int (*requested_observe)(NXSGtk3ActivationToken,void *)=dlsym(library,"nxs_gtk3_activation_observe_requests");
  gtk_activation_request=dlsym(library,"nxs_gtk3_activation_request");
  gtk_activation_watch=dlsym(RTLD_DEFAULT,"g_unix_fd_add_full");
  int (*observe)(NXSGtk3ActivationToken,void *)=dlsym(library,"nxs_gtk3_activation_observe_input");
  int ordered=!!observe;
  if(!observe)observe=dlsym(library,"nxs_gtk3_activation_observe");
  if(observe&&((int (*)(void))(base+0x7546c5c))()) {
    if(requested_observe&&gtk_activation_request&&gtk_activation_watch&&gtk_activation_source_attach()) {
      observe=requested_observe;gtk_activation_requested_mode=1;
    }
    int accepted=observe(gtk_activation_token,NULL);
    int (*pointer_observe)(NXSGtk3SourcePointer,void *)=dlsym(library,"nxs_gtk3_source_pointer_observe");
    if(accepted&&pointer_observe)pointer_observe(gtk_source_pointer,NULL);
    note(accepted?"original GTK activation handoff enabled":"GTK activation observation unavailable");
    if(accepted&&ordered)note("original GTK activation input ordering enabled");
    if(accepted&&observe==requested_observe)note("original GTK activation tokens requested at presentation");
  }
  return gtk_surface_geometry&&guard_geometry_calls()&&guard_popup_geometry_calls()&&prepare_detours(geometry_detours,1);
}

/* Compositor geometry supplies the origin; Gecko retains bounds/margin logic,
 * lifecycle notifications and parent-to-content-process dimension transport. */
#include "../../Libraries/NativeUI/Bridge/Gtk3Geometry.h"
#include "pinned-geometry.h"
/* Nontrivial nsRect has the original indirect-result ABI. */
__attribute__((naked)) static void geometry_client_rect(void *function,void *frame,void *output)
{__asm__("mov x16,x0\nmov x0,x1\nmov x8,x2\nbr x16");}
static int gecko_frame_screen_origin(void *frame,double *x,double *y)
{
  if(!frame||!guard_frame_geometry_calls())return 0;
  void *root=((void *(*)(void *))(base+NXS_GECKO_GEOMETRY_ROOT_FRAME))(frame);
  if(!root)return 0;
  struct {int x,y,width,height;} screen;
  screen=((typeof(screen) (*)(const void *))(base+NXS_GECKO_GEOMETRY_SCREEN_RECT))(root);
  int bounds[4]={0};geometry_client_rect((void *)(base+NXS_GECKO_GEOMETRY_CLIENT_RECT),frame,bounds);
  *x=screen.x+bounds[0]/60.;*y=screen.y+bounds[1]/60.;
  return isfinite(*x)&&isfinite(*y);
}
static int gecko_frame_pixel_rect(void *frame,struct NXSRectD *rect)
{
  double x,y;if(!gecko_frame_screen_origin(frame,&x,&y))return 0;
  double left=floor(x+rect->x+.5),top=floor(y+rect->y+.5);
  double right=floor(x+rect->x+rect->width+.5),bottom=floor(y+rect->y+rect->height+.5);
  *rect=(struct NXSRectD){left-floor(x+.5),top-floor(y+.5),right-left,bottom-top};
  return 1;
}
struct GeckoWindowBounds {int32_t client[4], margin[4];};
_Static_assert(sizeof(struct GeckoWindowBounds)==32,"Pinned Gecko Bounds ABI");
static struct GeckoWindowBounds (*original_geometry_compute)(const void *);
static int (*gtk_surface_geometry)(void *,NXSGtk3SurfaceGeometry *,NXSGtk3GeometryChanged);
static void gtk_activation_token(uintptr_t surface,const char *token,void *context)
{
  int accepted=native_auxiliary_token_publish(surface,0,token);
  if(log_fd>=0)dprintf(log_fd,"%d original GTK activation token queued=%d\n",getpid(),accepted);
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
static int prepare_geometry(void) {
  const char *path=getenv("NEXTSPACE_GTK3_GEOMETRY_LIBRARY");if(!path||!*path)return 1;
  void *library=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!library)return 0;
  gtk_surface_geometry=dlsym(library,"nxs_gtk3_surface_geometry");
  int (*observe)(NXSGtk3ActivationToken,void *)=dlsym(library,"nxs_gtk3_activation_observe");
  if(observe && ((int (*)(void))(base+0x7546c5c))())
    note(observe(gtk_activation_token,NULL)?"original GTK activation handoff enabled":"GTK activation observation unavailable");
  return gtk_surface_geometry&&guard_geometry_calls()&&prepare_detours(geometry_detours,1);
}

/* Compositor geometry supplies the origin; Gecko retains bounds/margin logic,
 * lifecycle notifications and parent-to-content-process dimension transport. */
#include "../../Libraries/NativeUI/Bridge/Gtk3Geometry.h"
#include "pinned-geometry.h"
struct GeckoWindowBounds {int32_t client[4], margin[4];};
_Static_assert(sizeof(struct GeckoWindowBounds)==32,"Pinned Gecko Bounds ABI");
static struct GeckoWindowBounds (*original_geometry_compute)(const void *);
static int (*gtk_surface_geometry)(void *,NXSGtk3SurfaceGeometry *,NXSGtk3GeometryChanged);
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
  return gtk_surface_geometry&&guard_geometry_calls()&&prepare_detours(geometry_detours,1);
}

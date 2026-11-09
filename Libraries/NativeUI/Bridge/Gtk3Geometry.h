/* Optional GTK3/Wayland surface geometry transport. MIT license. */
#ifndef NXS_GTK3_GEOMETRY_H
#define NXS_GTK3_GEOMETRY_H
#include "WaylandGeometry.h"
typedef NXSWaylandSurfaceGeometry NXSGtk3SurfaceGeometry;
typedef void (*NXSGtk3GeometryChanged)(void *gdk_window);
/* UI-thread only. window must be an actual toplevel GdkWindow. The optional
 * callback runs on the GLib idle queue after a changed compositor snapshot.
 * Zero means unavailable/not received; preserve the toolkit's ordinary path.
 * An unmapped snapshot is not a usable anchor for visible native controls.
 * This observes geometry only; it changes no GDK or compositor window policy. */
int nxs_gtk3_surface_geometry(void *gdk_window, NXSGtk3SurfaceGeometry *geometry,
                            NXSGtk3GeometryChanged changed);
#endif

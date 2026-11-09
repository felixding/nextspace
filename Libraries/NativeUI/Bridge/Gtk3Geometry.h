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
/* Forward original GTK startup-notification tokens generated for actual input.
 * GTK owns serial/seat selection and protocol requests; callback borrows token.
 * UI-thread only; one subscriber per process. NULL disables observation. */
typedef void (*NXSGtk3ActivationToken)(uintptr_t surface, const char *token, void *context);
int nxs_gtk3_activation_observe(NXSGtk3ActivationToken callback, void *context);
#endif

/* Optional GTK3/Wayland surface geometry transport. MIT license. */
#ifndef NXS_GTK3_GEOMETRY_H
#define NXS_GTK3_GEOMETRY_H
#include "WaylandGeometry.h"
typedef NXSWaylandSurfaceGeometry NXSGtk3SurfaceGeometry;
typedef void (*NXSGtk3GeometryChanged)(void *gdk_window);
/* UI-thread only. window must be an actual toplevel GdkWindow. The optional
 * callback runs on the GLib idle queue after a changed compositor snapshot.
 * A NULL callback reads geometry without replacing an existing observer.
 * Zero means unavailable/not received; preserve the toolkit's ordinary path.
 * An unmapped snapshot is not a usable anchor for visible native controls.
 * This observes geometry only; it changes no GDK or compositor window policy. */
int nxs_gtk3_surface_geometry(void *gdk_window, NXSGtk3SurfaceGeometry *geometry,
                            NXSGtk3GeometryChanged changed);
/* Forward original GTK startup-notification tokens generated for actual input.
 * GTK owns serial/seat selection and protocol requests; callback borrows token.
 * UI-thread only; one subscriber per process. NULL callback disables observation.
 * The legacy observer receives nonempty tokens only. */
typedef void (*NXSGtk3ActivationToken)(uintptr_t surface, const char *token, void *context);
int nxs_gtk3_activation_observe(NXSGtk3ActivationToken callback, void *context);
/* Opt in to NULL-token notifications that invalidate the preceding input grant.
 * Token creation runs after GTK handles the event; newer input supersedes old
 * work. This shares the same observer and preserves the legacy callback ABI. */
int nxs_gtk3_activation_observe_input(NXSGtk3ActivationToken callback, void *context);
/* Request mode retains real input metadata and mints through GDK only when
 * the native host is ready to present. No token is eagerly generated. */
int nxs_gtk3_activation_observe_requests(NXSGtk3ActivationToken callback, void *context);
int nxs_gtk3_activation_request(void);
/* Observe original pointer presses through the same already registered GTK
 * event hook. No key interpretation, pointer capture or new event reader. */
typedef void (*NXSGtk3SourcePointer)(uintptr_t surface,void *context);
int nxs_gtk3_source_pointer_observe(NXSGtk3SourcePointer callback,void *context);
/* Borrowed xdg-foreign handle for an already observed owned surface. */
const char *nxs_gtk3_surface_parent(uintptr_t surface);
#endif

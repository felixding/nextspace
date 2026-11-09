/* Owned Wayland surface geometry transport. MIT license. */
#ifndef NXS_WAYLAND_GEOMETRY_H
#define NXS_WAYLAND_GEOMETRY_H
#include <stdint.h>
struct wl_display;
struct wl_surface;
struct wl_seat;
struct wl_proxy;
struct wl_interface;
typedef struct NXSGeometryDisplay NXSGeometryDisplay;
typedef struct NXSGeometrySurface NXSGeometrySurface;
typedef struct {
  int32_t x, y, width, height;
  uint32_t mapped;
} NXSWaylandSurfaceGeometry;
typedef void (*NXSGeometryChanged)(void *context);
/* A host with a private/static Wayland client supplies its original public C
 * functions. Never operate on its proxy/queue internals through another copy
 * of libwayland-client. Interface descriptors are ordinary protocol data. */
typedef struct {
  uint32_t bytes;
  struct wl_proxy *(*marshal_flags)(struct wl_proxy *, uint32_t,
      const struct wl_interface *, uint32_t, uint32_t, ...);
  int (*add_listener)(struct wl_proxy *, void (**)(void), void *);
  void (*destroy)(struct wl_proxy *);
  int (*flush)(struct wl_display *);
} NXSWaylandClientAPI;
/* All calls and callbacks use the caller's Wayland dispatch thread. There is
 * no event reader, roundtrip, layout, placement or rendering in this library.
 * creation_display must be the caller's display wrapper when it uses a private
 * event queue; new proxies inherit that queue. display is used only to flush.
 * NULL means unavailable/allocation failure; retain the ordinary toolkit path. */
NXSGeometryDisplay *nxs_wayland_geometry_connect(struct wl_display *display,
                                                struct wl_display *creation_display);
NXSGeometryDisplay *nxs_wayland_geometry_connect_with_api(struct wl_display *display,
    struct wl_display *creation_display, const NXSWaylandClientAPI *);
/* Disconnect invalidates and frees all observations. proxies_valid must be
 * zero after the owner has already disconnected its wl_display. */
void nxs_wayland_geometry_disconnect(NXSGeometryDisplay *, int proxies_valid);
/* The caller must supply its own live toplevel surface, and release/rebind the
 * observation before destroying/replacing that surface. */
NXSGeometrySurface *nxs_wayland_geometry_observe(NXSGeometryDisplay *, struct wl_surface *,
                                               NXSGeometryChanged, void *context);
void nxs_wayland_geometry_rebind(NXSGeometrySurface *, struct wl_surface *);
void nxs_wayland_geometry_unobserve(NXSGeometrySurface *);
/* Zero means no compositor snapshot yet. An unmapped snapshot cannot anchor a
 * visible control. Notifications may destroy the observation or connection. */
int nxs_wayland_geometry_read(NXSGeometrySurface *, NXSWaylandSurfaceGeometry *);
/* Standard xdg-activation transport on the same owning connection/queue.
 * The source must be mapped and serial must come from original user input.
 * A NULL seat uses the connection's sole advertised seat; multiple seats
 * require an explicit original seat. The compositor validates provenance.
 * A successful request calls back once, with borrowed UTF8 valid during the
 * callback. Rebinding/releasing the observation cancels pending requests.
 * Zero reports unavailable; it never fabricates a token or grants focus. */
typedef void (*NXSWaylandActivationToken)(void *context,const char *token);
int nxs_wayland_activation_request(NXSGeometrySurface *, struct wl_seat *, uint32_t serial,
                                   NXSWaylandActivationToken, void *context);
int nxs_wayland_activation_apply(NXSGeometryDisplay *, struct wl_surface *, const char *token);
#endif

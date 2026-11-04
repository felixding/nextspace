/* Thin C boundary to the existing AppKit control. GPL-2.0-or-later. */
#ifndef NEXTSPACE_NATIVE_SCROLLER_H
#define NEXTSPACE_NATIVE_SCROLLER_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct NXSScroller NXSScroller;
typedef struct { double x, y, width, height; } NXSRect;
typedef struct { int width, height, stride; const unsigned char *pixels; } NXSBitmap;
typedef void (*NXSChanged)(void *context, double value);
typedef void (*NXSPump)(void *context);
/* Physical host modifier families; the bridge applies GNUstep's own defaults. */
enum { NXS_SHIFT = 1, NXS_ALT = 2, NXS_CONTROL = 4, NXS_SUPER = 8 };
enum { NXS_MOVE, NXS_RELEASE };
NXSScroller *nxs_scroller_create(int horizontal, NXSChanged changed, NXSPump pump, void *context);
void nxs_scroller_destroy(NXSScroller *scroller);
double nxs_scroller_width(void);
void nxs_scroller_sync(NXSScroller *scroller, double length, double lower, double upper,
                       double page, double step, double page_step, double value, int enabled);
NXSBitmap nxs_scroller_draw(NXSScroller *scroller, double scale);
NXSRect nxs_scroller_part(NXSScroller *scroller, int part);
/* These execute NSScroller's own mouseDown:/tracking loop. Pump dispatches host
 * toolkit events on the same thread; forward motion/release with send(). */
void nxs_scroller_track(NXSScroller *scroller, double x, double y, unsigned modifiers);
void nxs_scroller_send(NXSScroller *scroller, int event, double x, double y, unsigned modifiers);
int nxs_scroller_tracking(NXSScroller *scroller);
int nxs_scroller_hit_part(NXSScroller *scroller);
#ifdef __cplusplus
}
#endif
#endif

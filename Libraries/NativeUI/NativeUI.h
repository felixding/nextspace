/* Toolkit-independent contract for the native UI provider. GPL-2.0-or-later. */
#ifndef NEXTSPACE_NATIVE_UI_H
#define NEXTSPACE_NATIVE_UI_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct NXSScroller NXSScroller;
typedef struct NXSControl NXSControl;
typedef struct { double x, y, width, height; } NXSRect;
typedef struct { double width, height; } NXSSize;
typedef struct { int width, height, stride; const unsigned char *pixels; } NXSBitmap;
typedef void (*NXSChanged)(void *context, double value);
typedef void (*NXSPump)(void *context);
enum { NXS_SHIFT = 1, NXS_ALT = 2, NXS_CONTROL = 4, NXS_SUPER = 8 };
enum { NXS_MOVE, NXS_RELEASE };

enum NXSControlKind {
  NXS_BUTTON = 1, NXS_CHECKBOX, NXS_RADIO, NXS_SLIDER, NXS_PROGRESS
};
enum NXSControlEvent { NXS_ACTIVATE = 1, NXS_VALUE_CHANGED };
typedef struct {
  uint32_t size;
  double width, height, minimum, maximum, value;
  int enabled, state, indeterminate;
  const char *title;
} NXSControlConfig;
typedef struct {
  uint32_t size;
  double value;
  int state, enabled, tracking;
} NXSControlState;
typedef void (*NXSControlChanged)(void *context, int event, const NXSControlState *state);

/* The provider owns all native objects, metrics, drawing and interaction.
 * Consumers own application models and translate events through this C ABI.
 * Coordinates are logical units from the top-left of the returned bitmap.
 * A provider is selected once per process; no toolkit headers cross this API. */
#define NXS_NATIVE_UI_ABI 1u
typedef struct {
  uint32_t version, size;
  NXSScroller *(*scroller_create)(int, NXSChanged, NXSPump, void *);
  void (*scroller_destroy)(NXSScroller *);
  double (*scroller_width)(void);
  void (*scroller_sync)(NXSScroller *, double, double, double, double, double, double, double, int);
  NXSBitmap (*scroller_draw)(NXSScroller *, double);
  NXSRect (*scroller_part)(NXSScroller *, int);
  void (*scroller_track)(NXSScroller *, double, double, unsigned);
  void (*scroller_send)(NXSScroller *, int, double, double, unsigned);
  int (*scroller_tracking)(NXSScroller *);
  int (*scroller_hit_part)(NXSScroller *);
  NXSControl *(*control_create)(int, NXSControlChanged, NXSPump, void *);
  int (*control_destroy)(NXSControl *);
  int (*control_sync)(NXSControl *, const NXSControlConfig *);
  NXSControlState (*control_state)(NXSControl *);
  NXSSize (*control_size)(NXSControl *);
  NXSBitmap (*control_draw)(NXSControl *, double);
  void (*control_track)(NXSControl *, double, double, unsigned);
  void (*control_send)(NXSControl *, int, double, double, unsigned);
} NXSNativeUIAPI;

/* Loader API. The GNUstep provider is the default. An alternate provider may
 * implement nxs_native_ui_provider(version) and be selected by
 * NEXTSPACE_NATIVE_UI_PROVIDER before the first call. */
const NXSNativeUIAPI *nxs_native_ui_api(void);
const char *nxs_native_ui_error(void);
NXSControl *nxs_control_create(int kind, NXSControlChanged changed, NXSPump pump, void *context);
int nxs_control_destroy(NXSControl *control);
int nxs_control_sync(NXSControl *control, const NXSControlConfig *config);
NXSControlState nxs_control_state(NXSControl *control);
NXSSize nxs_control_size(NXSControl *control);
NXSBitmap nxs_control_draw(NXSControl *control, double scale);
void nxs_control_track(NXSControl *control, double x, double y, unsigned modifiers);
void nxs_control_send(NXSControl *control, int event, double x, double y, unsigned modifiers);

#ifdef __cplusplus
}
#endif
#endif

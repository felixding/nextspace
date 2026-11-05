/* Toolkit-independent contract for the native UI provider. GPL-2.0-or-later. */
#ifndef NEXTSPACE_NATIVE_UI_H
#define NEXTSPACE_NATIVE_UI_H
#include <stdint.h>
#include <stddef.h>
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

enum NXSInputCapability { NXS_INPUT_FOCUS = 1, NXS_INPUT_KEYBOARD = 2 };
enum NXSEventCapability { NXS_EVENTS = 1 };
enum NXSKeyType { NXS_KEY_DOWN, NXS_KEY_UP, NXS_KEY_MODIFIERS };
enum NXSKey {
  NXS_KEY_TEXT, NXS_KEY_ENTER, NXS_KEY_TAB, NXS_KEY_BACKSPACE, NXS_KEY_DELETE,
  NXS_KEY_ESCAPE, NXS_KEY_LEFT, NXS_KEY_RIGHT, NXS_KEY_UP_ARROW, NXS_KEY_DOWN_ARROW,
  NXS_KEY_HOME, NXS_KEY_END, NXS_KEY_PAGE_UP, NXS_KEY_PAGE_DOWN, NXS_KEY_INSERT,
  NXS_KEY_F1 = 32, NXS_KEY_F24 = NXS_KEY_F1 + 23
};
enum NXSInputResult { NXS_INPUT_UNHANDLED, NXS_INPUT_HANDLED, NXS_INPUT_NEXT, NXS_INPUT_PREVIOUS };
typedef struct {
  uint32_t size, type, modifiers, key, repeat;
  /* NUL-terminated UTF-8. NULL text is empty; NULL unmodified_text uses text. */
  const char *text, *unmodified_text;
} NXSKeyEvent;

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
  /* Optional append-only input extension. Check size before reading fields. */
  int (*control_focus)(NXSControl *, int);
  int (*control_focused)(NXSControl *);
  int (*control_key)(NXSControl *, const NXSKeyEvent *);
  /* Optional native event-loop extension; timing and invalidation stay native. */
  double (*dispatch_events)(double maximum_wait);
  int (*control_needs_display)(NXSControl *);
} NXSNativeUIAPI;
#define NXS_NATIVE_UI_CORE_SIZE offsetof(NXSNativeUIAPI, control_focus)

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
unsigned nxs_control_input_capabilities(void);
int nxs_control_focus(NXSControl *control, int focused);
int nxs_control_focused(NXSControl *control);
int nxs_control_key(NXSControl *control, const NXSKeyEvent *event);
unsigned nxs_native_ui_event_capabilities(void);
/* Service native events on the owning UI thread. maximum_wait is in seconds;
 * zero is nonblocking. Return seconds until the next native deadline, or -1
 * when none is available. This does not advance or draw controls itself. */
double nxs_native_ui_dispatch_events(double maximum_wait);
int nxs_control_needs_display(NXSControl *control);

#ifdef __cplusplus
}
#endif
#endif

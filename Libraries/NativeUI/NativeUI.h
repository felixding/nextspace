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
typedef struct NXSEventSource NXSEventSource;
typedef struct { double x, y, width, height; } NXSRect;
typedef struct { double width, height; } NXSSize;
typedef struct { int width, height, stride; const unsigned char *pixels; } NXSBitmap;
typedef void (*NXSChanged)(void *context, double value);
typedef void (*NXSPump)(void *context);
enum { NXS_SHIFT = 1, NXS_ALT = 2, NXS_CONTROL = 4, NXS_SUPER = 8 };
enum { NXS_MOVE, NXS_RELEASE };

enum NXSControlKind {
  NXS_BUTTON = 1, NXS_CHECKBOX, NXS_RADIO, NXS_SLIDER, NXS_PROGRESS, NXS_POPUP,
  NXS_TEXTFIELD, NXS_PASSWORD
};
enum NXSControlEvent { NXS_ACTIVATE = 1, NXS_VALUE_CHANGED, NXS_TEXT_CHANGED };
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
enum NXSPointerCapability { NXS_POINTER_CLICK_COUNT = 1 };
enum NXSEventCapability { NXS_EVENTS = 1 };
enum NXSRangeCapability { NXS_RANGE_STEP = 1 };
enum NXSPopupCapability { NXS_POPUP_ITEMS = 1 };
typedef struct {
  uint32_t size;
  const char *title;
  int enabled, separator;
} NXSPopupItem;
typedef struct {
  uint32_t size;
  int visible, highlighted;
  NXSRect frame;
} NXSPopupState;
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
enum NXSTextCapability { NXS_TEXT_EDITING = 1, NXS_TEXT_FILTER = 2, NXS_TEXT_COMMAND = 4 };
#define NXS_TEXT_NO_SELECTION UINT64_MAX
/* Selection and marked ranges use native NSString/UTF16 code units. A model
 * with NO_SELECTION leaves initial selection to the native responder. */
typedef struct {
  uint32_t size;
  const char *text;
  uint64_t selection_start, selection_length;
  int editable;
} NXSTextModel;
typedef struct {
  uint32_t size;
  uint64_t selection_start, selection_length, marked_start, marked_length;
  int editing, editable, secure;
} NXSTextState;
/* Borrowed proposal from the actual native editor before mutation/undo
 * registration. Ranges use UTF-16. command is its interpreted selector, or
 * NULL for direct insertion. Returning zero vetoes the edit. */
typedef struct {
  uint32_t size;
  uint64_t range_start,range_length,selection_start,selection_length;
  const char *replacement,*command;
} NXSTextEdit;
typedef int (*NXSTextShouldChange)(void *context,const NXSTextEdit *edit);
enum NXSCommandPhase { NXS_COMMAND_VALIDATE, NXS_COMMAND_EXECUTE };
/* -1 leaves the native action/validation unchanged. Zero owns a disabled or
 * rejected command; one enables/executes it. Selectors come from the native
 * responder/menu, never from a consumer shortcut table. */
typedef int (*NXSCommandFilter)(void *context,const char *selector,unsigned phase);

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
  int (*control_set_step)(NXSControl *, double);
  int (*control_popup_items)(NXSControl *, const NXSPopupItem *, uint32_t, int);
  NXSPopupState (*control_popup_state)(NXSControl *);
  NXSRect (*control_popup_item_rect)(NXSControl *, int);
  int (*control_set_screen_origin)(NXSControl *, double, double);
  NXSEventSource *(*event_source_create)(int descriptor);
  int (*event_source_destroy)(NXSEventSource *);
  int (*control_popup_open)(NXSControl *, int);
  int (*control_text_sync)(NXSControl *, const NXSTextModel *);
  size_t (*control_text_get)(NXSControl *, char *, size_t, NXSTextState *);
  int (*control_text_filter)(NXSControl *,NXSTextShouldChange,void *);
  const char *(*control_text_command)(NXSControl *);
  int (*control_track_clicks)(NXSControl *,double,double,unsigned,unsigned);
  int (*control_command_filter)(NXSControl *,NXSCommandFilter,void *);
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
unsigned nxs_control_pointer_capabilities(void);
/* Forward the embedding application's positive click count to the actual
 * native mouse event. The UI library owns word/line selection and tracking.
 * Returns zero for unsupported metadata or rejected input. Legacy providers
 * retain single-click tracking through the original entry point. */
int nxs_control_track_clicks(NXSControl *,double x,double y,unsigned modifiers,unsigned click_count);
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
unsigned nxs_control_range_capabilities(void);
/* Positive data quantum; zero denotes a continuous range. The provider maps
 * small discrete domains to native slider ticks; widget behavior stays native. */
int nxs_control_set_step(NXSControl *control, double step);
unsigned nxs_control_popup_capabilities(void);
/* The application supplies ordered item data, including separators. Selection
 * is an array index, or -1. The native control owns layout and navigation. */
int nxs_control_popup_items(NXSControl *, const NXSPopupItem *, uint32_t count, int selected);
/* Native menu geometry uses control bitmap coordinates, including positions
 * outside that bitmap. A hidden menu returns a zero frame/item rectangle. */
NXSPopupState nxs_control_popup_state(NXSControl *);
NXSRect nxs_control_popup_item_rect(NXSControl *, int index);
/* Request the control's top-left relative to the native main screen's top-left,
 * in logical units. The backend/compositor determines actual window placement. */
int nxs_control_set_screen_origin(NXSControl *, double x, double y);
/* Optional native-loop integration for an embedding application's readable
 * descriptors. The source wakes dispatch_events; the caller still reads the
 * descriptor and retains ownership of it. Create/destroy on the UI thread. */
unsigned nxs_native_ui_source_capabilities(void);
NXSEventSource *nxs_native_ui_source_create(int descriptor);
int nxs_native_ui_source_destroy(NXSEventSource *);
unsigned nxs_control_popup_open_capabilities(void);
/* Change popup visibility through the native control's methods, without
 * assuming a keyboard binding. Busy native tracking rejects this request. */
int nxs_control_popup_open(NXSControl *, int open);
unsigned nxs_control_text_capabilities(void);
/* Application model updates do not emit user-edit events. Native editing
 * emits NXS_TEXT_CHANGED; the application reads the actual native text/range.
 * NXS_ACTIVATE retains the text field's native action (for example Return). */
int nxs_control_text_sync(NXSControl *, const NXSTextModel *);
/* Returns required UTF8 buffer bytes including NUL, or 0 on failure. A NULL
 * or insufficient buffer does not copy partial text. State is optional. */
size_t nxs_control_text_get(NXSControl *, char *buffer, size_t capacity, NXSTextState *);
/* Install/remove a pre-edit delegate on the owning UI thread. The callback
 * may read state; mutation/destruction remain deferred while busy. */
int nxs_control_text_filter(NXSControl *,NXSTextShouldChange,void *);
/* Last selector interpreted by the actual editor (for example copy:), or NULL.
 * Borrowed until the next key/menu command; no key-binding resolution is copied
 * into an embedding application. The application can perform its semantic
 * action after interpretation. Disabled native menu items do not dispatch a
 * selector; this getter does not supply external command availability. */
const char *nxs_control_text_command(NXSControl *);
unsigned nxs_control_command_capabilities(void);
int nxs_control_command_filter(NXSControl *,NXSCommandFilter,void *);

#ifdef __cplusplus
}
#endif
#endif

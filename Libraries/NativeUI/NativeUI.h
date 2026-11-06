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
typedef struct NXSMenu NXSMenu;
typedef struct { double x, y, width, height; } NXSRect;
typedef struct { double width, height; } NXSSize;
typedef struct { double x, y; } NXSPoint;
typedef struct { int width, height, stride; const unsigned char *pixels; } NXSBitmap;
typedef void (*NXSChanged)(void *context, double value);
typedef void (*NXSPump)(void *context);
enum { NXS_SHIFT = 1, NXS_ALT = 2, NXS_CONTROL = 4, NXS_SUPER = 8 };
enum { NXS_MOVE, NXS_RELEASE };

enum NXSControlKind {
  NXS_BUTTON = 1, NXS_CHECKBOX, NXS_RADIO, NXS_SLIDER, NXS_PROGRESS, NXS_POPUP,
  NXS_TEXTFIELD, NXS_PASSWORD, NXS_TEXTAREA, NXS_TABVIEW
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

enum NXSTabCapability { NXS_TAB_ITEMS = 1 };
typedef struct {
  uint32_t size;
  uint64_t identifier; /* Nonzero application identity, independent of order. */
  const char *title,*tooltip;
} NXSTabItem;
typedef struct {
  uint32_t size,count;
  int32_t selected_index;
  uint32_t reserved;
  uint64_t selected;
  NXSRect content; /* Native logical content rectangle, with a top-left origin. */
} NXSTabState;

enum NXSInputCapability { NXS_INPUT_FOCUS = 1, NXS_INPUT_KEYBOARD = 2 };
enum NXSPointerCapability { NXS_POINTER_CLICK_COUNT = 1 };
enum NXSWheelCapability { NXS_WHEEL_EVENTS = 1 };
typedef struct {
  uint32_t size, modifiers;
  double x, y;
  /* Unaccelerated surface-coordinate axis distance, positive right/down.
   * The provider applies native input preferences and scrolling behavior. */
  double delta_x, delta_y;
} NXSWheelEvent;
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
enum NXSTextCapability { NXS_TEXT_EDITING = 1, NXS_TEXT_FILTER = 2, NXS_TEXT_COMMAND = 4,
  NXS_TEXT_MULTILINE = 8, NXS_TEXT_VIEWPORT = 16, NXS_TEXT_GEOMETRY = 32 };
typedef struct {
  uint32_t size;
  NXSRect visible;
  NXSSize content;
} NXSTextViewport;
/* Native clip frame within the control, client size before scrollers, and
 * scroll limits from the native clip view. All coordinates are top-left. */
typedef struct {
  uint32_t size;
  NXSRect clip;
  NXSSize client;
  NXSPoint minimum, maximum;
} NXSTextGeometry;
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

enum NXSMenuFlag {
  NXS_MENU_SEPARATOR=1, NXS_MENU_DISABLED=2, NXS_MENU_CHECKED=4,
  NXS_MENU_MIXED=8, NXS_MENU_SUBMENU=16
};
/* Menu key equivalents name native modifier roles, independently of the
 * physical event modifiers. The UI library applies the user's key preferences. */
enum NXSMenuModifier {
  NXS_MENU_COMMAND=1, NXS_MENU_SHIFT=2, NXS_MENU_CONTROL=4, NXS_MENU_ALTERNATE=8
};
enum NXSMenuCapability { NXS_MENU_MODELS=1, NXS_MENU_CANCEL=2, NXS_MENU_LIFECYCLE=4, NXS_MENU_KEY_QUERY=8 };
enum NXSMenuLifecyclePhase { NXS_MENU_WILL_OPEN, NXS_MENU_DID_CLOSE };
typedef struct {
  uint32_t size;
  int32_t parent; /* -1 for root; otherwise an earlier SUBMENU item index. */
  uint64_t command;
  const char *title,*key_equivalent;
  uint32_t modifiers,flags;
} NXSMenuItem;
typedef struct {
  uint32_t size;
  int visible,tracking,highlighted,enabled;
  NXSRect frame,item_frame; /* Native main-screen top-left logical coordinates. */
} NXSMenuState;
/* Return one for enabled/executed, zero for rejected. Commands are opaque
 * application IDs; native menus own matching, validation and action dispatch. */
typedef int (*NXSMenuCommand)(void *context,uint64_t command,unsigned phase);
/* WILL_OPEN may refresh this branch before native layout/tracking enters it.
 * Return zero to cancel opening. DID_CLOSE balances each WILL_OPEN, including
 * rejected/cancelled preparation; its return value is ignored. */
typedef int (*NXSMenuLifecycle)(void *context,uint64_t branch,unsigned phase);

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
  NXSMenu *(*menu_create)(const char *,NXSMenuCommand,NXSPump,void *);
  int (*menu_destroy)(NXSMenu *);
  int (*menu_items)(NXSMenu *,const NXSMenuItem *,uint32_t);
  int (*menu_show)(NXSMenu *,int);
  int (*menu_key)(NXSMenu *,const NXSKeyEvent *);
  NXSMenuState (*menu_state)(NXSMenu *,int);
  int (*menu_cancel)(NXSMenu *);
  int (*menu_lifecycle)(NXSMenu *,NXSMenuLifecycle,void *);
  int (*menu_branch_items)(NXSMenu *,uint64_t,const NXSMenuItem *,uint32_t);
  int (*menu_key_query)(NXSMenu *,const NXSKeyEvent *);
  unsigned (*control_text_capabilities)(void);
  NXSTextViewport (*control_text_viewport)(NXSControl *);
  int (*control_text_scroll)(NXSControl *,double,double);
  int (*control_text_geometry)(NXSControl *,NXSTextGeometry *);
  int (*control_wheel)(NXSControl *,const NXSWheelEvent *);
  int (*control_tab_items)(NXSControl *,const NXSTabItem *,uint32_t,uint64_t);
  NXSTabState (*control_tab_state)(NXSControl *);
  NXSRect (*control_tab_item_rect)(NXSControl *,uint64_t);
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
unsigned nxs_control_wheel_capabilities(void);
/* Native hit testing/responder dispatch, independent of keyboard focus.
 * Returns one for accepted input, zero for unsupported/busy/invalid input. */
int nxs_control_wheel(NXSControl *,const NXSWheelEvent *);
unsigned nxs_control_tab_capabilities(void);
/* Replace application tab data without emitting a user selection action.
 * Identifiers must be unique/nonzero; selected names an item, or zero for an
 * empty model. Native items are retained across reorder and title changes.
 * User selection emits VALUE_CHANGED with the selected index in state.value.
 * Drawing, hit testing and selection behavior remain native. */
int nxs_control_tab_items(NXSControl *,const NXSTabItem *,uint32_t count,uint64_t selected);
NXSTabState nxs_control_tab_state(NXSControl *);
/* Native cached item geometry from the latest native draw; no layout algorithm
 * is reproduced. Unknown/undrawn items return an empty rectangle. */
NXSRect nxs_control_tab_item_rect(NXSControl *,uint64_t identifier);
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
/* Multiline native document geometry. Logical coordinates run from the
 * document's top left. Native clipping supplies scrolling and bounds. */
NXSTextViewport nxs_control_text_viewport(NXSControl *);
int nxs_control_text_scroll(NXSControl *,double x,double y);
/* Caller initializes size. Returns zero when unsupported or too small. The
 * earlier by-value viewport struct is unchanged for existing consumers. */
int nxs_control_text_geometry(NXSControl *,NXSTextGeometry *);
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

/* Optional native application menus. Model strings are copied on success.
 * Mutations/destruction are rejected during native tracking or callbacks.
 * Show installs one menu as the native application's main menu; hide releases
 * that role. An existing unrelated main menu is never replaced. Key dispatch
 * also works while hidden. State index -1 describes the root; other indices
 * address the flattened model. Submenu frames are empty until mapped.
 * Call on the owning UI thread and service dispatch_events for real input. */
unsigned nxs_native_ui_menu_capabilities(void);
NXSMenu *nxs_menu_create(const char *title,NXSMenuCommand,NXSPump,void *context);
int nxs_menu_destroy(NXSMenu *);
int nxs_menu_items(NXSMenu *,const NXSMenuItem *,uint32_t count);
int nxs_menu_show(NXSMenu *,int visible);
int nxs_menu_key(NXSMenu *,const NXSKeyEvent *);
/* Native key matching/validation without highlighting or command execution.
 * Like NSMenu itself, a matching disabled command still consumes its key. */
int nxs_menu_key_query(NXSMenu *,const NXSKeyEvent *);
NXSMenuState nxs_menu_state(NXSMenu *,int index);
/* Explicit cancellation also works during tracking/callbacks. It suppresses
 * command execution, ends the native tracking loop and hides owned menus;
 * destruction remains deferred until dispatch returns. */
int nxs_menu_cancel(NXSMenu *);
/* Optional native submenu lifecycle. Register while hidden and idle. With a
 * lifecycle handler, every non-separator item, including SUBMENU, needs a
 * unique nonzero opaque command ID. Root ID zero is reserved. */
int nxs_menu_lifecycle(NXSMenu *,NXSMenuLifecycle,void *);
/* Replace only an invisible branch's children. Parent indices are relative
 * to the supplied branch model, with -1 for direct children. During tracking
 * this is allowed only for the branch's own WILL_OPEN callback. Other model
 * mutation remains rejected. Successful replacement invalidates flattened
 * item indices, but preserves the branch object and surrounding native menus. */
int nxs_menu_branch_items(NXSMenu *,uint64_t,const NXSMenuItem *,uint32_t);

#ifdef __cplusplus
}
#endif
#endif

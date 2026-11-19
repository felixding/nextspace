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
typedef struct NXSFilePanel NXSFilePanel;
typedef struct NXSEditBindings NXSEditBindings;
typedef struct { double x, y, width, height; } NXSRect;
typedef struct { double width, height; } NXSSize;
typedef struct { double x, y; } NXSPoint;
typedef struct { int width, height, stride; const unsigned char *pixels; } NXSBitmap;
typedef void (*NXSChanged)(void *context, double value);
typedef void (*NXSPump)(void *context);
enum { NXS_SHIFT = 1, NXS_ALT = 2, NXS_CONTROL = 4, NXS_SUPER = 8 };
enum { NXS_MOVE, NXS_RELEASE };

/* Native file-panel data only; the provider owns every visible control. */
enum NXSFilePanelMode { NXS_FILE_OPEN, NXS_FILE_SAVE };
enum NXSFilePanelFlag { NXS_FILE_MULTIPLE=1, NXS_FILE_DIRECTORY=2, NXS_FILE_HIDDEN=4 };
typedef int (*NXSFileAllows)(void *,const char *,uint32_t);
typedef struct {
  uint32_t size,count,selected,reserved;
  const char *label;
  const char *const *options; /* No options means an original checkbox. */
} NXSFileChoice;
typedef struct {
  uint32_t size,flags,filter_count,selected_filter,choice_count,batch_count;
  const char *title,*directory,*name,*accept_label;
  const char *const *filter_titles;
  const NXSFileChoice *choices;
  const char *const *batch_names; /* SaveFiles: names within one chosen folder. */
  const char *parent_window; /* Optional appended field: portal window identifier. */
} NXSFilePanelConfig;
typedef struct { uint32_t size;int32_t result;uint32_t count,selected_filter; } NXSFilePanelState;

enum NXSControlKind {
  NXS_BUTTON = 1, NXS_CHECKBOX, NXS_RADIO, NXS_SLIDER, NXS_PROGRESS, NXS_POPUP,
  NXS_TEXTFIELD, NXS_PASSWORD, NXS_TEXTAREA, NXS_TABVIEW, NXS_TOOLBAR, NXS_RADIOGROUP,
  NXS_LISTBOX, NXS_SEARCHFIELD, NXS_STEPPER, NXS_COLORWELL, NXS_DATEPICKER,
  NXS_OUTLINE
};
/* Application hierarchy only. NSOutlineView owns disclosure, selection,
 * keyboard navigation, layout, scrolling and drawing. Parents precede children.
 * Native actions expose the model index in value and select/expand/collapse
 * in state (0/1/-1), through the existing ordered action receipt channel. */
enum NXSOutlineFlag { NXS_OUTLINE_ENABLED=1, NXS_OUTLINE_SELECTED=2,
  NXS_OUTLINE_EXPANDABLE=4, NXS_OUTLINE_EXPANDED=8 };
typedef struct {
  uint32_t size,flags;
  uint64_t identifier,parent;
  const char *title;
} NXSOutlineItem;
enum NXSSpecializedCapability { NXS_SPECIAL_STEPPER=1, NXS_SPECIAL_COLOR=2, NXS_SPECIAL_DATE=4,
  NXS_SPECIAL_DATE_NULLABLE=8, NXS_SPECIAL_TIME_OF_DAY=16, NXS_SPECIAL_MONTH_START=32,
  NXS_SPECIAL_DATE_PROLEPTIC=64, NXS_SPECIAL_WEEK_START=128, NXS_SPECIAL_DATE_PANEL=256 };
typedef struct { uint32_t size; double red,green,blue,alpha; } NXSColorModel;
enum NXSDateElements { NXS_DATE_YEAR_MONTH=1, NXS_DATE_YEAR_MONTH_DAY,
  NXS_DATE_HOUR_MINUTE, NXS_DATE_HOUR_MINUTE_SECOND, NXS_DATE_DATE_AND_TIME, NXS_DATE_YEAR_WEEK };
enum NXSDateStyle { NXS_DATE_TEXT_AND_STEPPER, NXS_DATE_CALENDAR, NXS_DATE_TEXT };
enum NXSDateFlag { NXS_DATE_MINIMUM=1, NXS_DATE_MAXIMUM=2, NXS_DATE_UTC=4,
  NXS_DATE_EMPTY=8, NXS_DATE_ALLOW_EMPTY=16, NXS_DATE_TIME_OF_DAY=32, NXS_DATE_MONTH_START=64,
  NXS_DATE_PROLEPTIC_GREGORIAN=128, NXS_DATE_WEEK_START=256 };
/* Date values are Unix seconds. App-specific parsing/validation stays with
 * the application; the original native date control owns its UI and input.
 * Opt-in TIME_OF_DAY uses millisecond-precise UTC seconds since midnight;
 * Foundation projects native dates into that domain, including day rollover.
 * Opt-in MONTH_START uses UTC Unix seconds at the first day of a proleptic
 * Gregorian month. PROLEPTIC_GREGORIAN selects that calendar for other dates.
 * WEEK_START uses UTC Unix seconds at Monday of an ISO week, with YEAR_WEEK. */
typedef struct { uint32_t size,flags,elements,style; double value,minimum,maximum; } NXSDateModel;
enum NXSControlEvent { NXS_ACTIVATE = 1, NXS_VALUE_CHANGED, NXS_TEXT_CHANGED };
/* Original native cell rectangles in control top-left coordinates. */
enum NXSSearchPart { NXS_SEARCH_BUTTON=1, NXS_SEARCH_CANCEL, NXS_SEARCH_TEXT };
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

enum NXSRadioCapability { NXS_RADIO_GROUP = 1, NXS_RADIO_CELL_SIZE = 2 };
typedef struct {
  uint32_t size;
  uint64_t identifier;
  const char *title;
  int enabled;
} NXSRadioItem;
typedef struct {
  uint32_t size,count,rows,columns;
  uint64_t selected,key_cell,actions;
} NXSRadioState;

enum NXSListCapability { NXS_LIST_ITEMS = 1 };
enum NXSListFlag { NXS_LIST_MULTIPLE = 1 };
typedef struct {
  uint32_t size;
  uint64_t identifier;
  const char *title;
  int enabled,selected;
} NXSListItem;
typedef struct {
  uint32_t size,count,selected_count,flags;
  uint64_t primary,key_cell,actions;
  NXSRect visible; /* Original native document coordinates. */
  NXSSize content;
} NXSListState;

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

enum NXSToolbarCapability { NXS_TOOLBAR_ITEMS = 1 };
enum NXSToolbarItemType { NXS_TOOLBAR_ACTION, NXS_TOOLBAR_SPACE,
  NXS_TOOLBAR_FLEXIBLE_SPACE, NXS_TOOLBAR_SEPARATOR };
enum NXSToolbarDisplay { NXS_TOOLBAR_DEFAULT_DISPLAY, NXS_TOOLBAR_IMAGE_AND_LABEL,
  NXS_TOOLBAR_IMAGE_ONLY, NXS_TOOLBAR_LABEL_ONLY };
enum NXSToolbarSize { NXS_TOOLBAR_DEFAULT_SIZE, NXS_TOOLBAR_REGULAR, NXS_TOOLBAR_SMALL };
enum NXSToolbarFlag { NXS_TOOLBAR_MENU_VISIBLE=1, NXS_TOOLBAR_TRACKING=2 };
typedef struct {
  uint32_t size,type;
  uint64_t identifier;
  const char *title,*tooltip,*image_name;
  int32_t enabled;
  uint32_t reserved;
} NXSToolbarItem;
typedef struct {
  uint32_t size,count,visible_count,flags;
  uint64_t command; /* Last native activation; zero before any action. */
  NXSSize preferred; /* Configured width and native layout height. */
  NXSRect overflow,menu; /* Native rectangles in control top-left coordinates. */
  int32_t highlighted;
  uint32_t reserved;
} NXSToolbarState;

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
typedef void (*NXSEditCommand)(void *context,const char *selector);
enum NXSEditBindingResult {
  NXS_EDIT_UNBOUND, NXS_EDIT_COMMANDS, NXS_EDIT_SEQUENCE
};
enum NXSTextCapability { NXS_TEXT_EDITING = 1, NXS_TEXT_FILTER = 2, NXS_TEXT_COMMAND = 4,
  NXS_TEXT_MULTILINE = 8, NXS_TEXT_VIEWPORT = 16, NXS_TEXT_GEOMETRY = 32,
  NXS_TEXT_SEARCH = 64, NXS_TEXT_SEARCH_ACTION = 128, NXS_TEXT_SEARCH_CLEAR_COMMAND = 256,
  NXS_TEXT_PLACEHOLDER = 512 };
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
/* The same native scroll-view measurement applies to text and list controls.
 * Keep the original text spelling and layout for existing callers. */
typedef NXSTextGeometry NXSScrollGeometry;
enum NXSScrollCapability { NXS_SCROLL_GEOMETRY = 1 };
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
  NXS_MENU_MIXED=8, NXS_MENU_SUBMENU=16,
  /* An application's command registry can contain actions absent from its
   * visible menu. Bind their key equivalents through the same native menu;
   * no displayed item or second key-matching implementation is required.
   * Root bindings also work with lifecycle menus and survive branch updates. */
  NXS_MENU_KEY_ONLY=32,
  /* Transported models supply enabled state for passive display. Commands,
   * key queries and explicit item-state reads still validate with the owner. */
  NXS_MENU_ENABLED_SNAPSHOT=64
};
/* Menu key equivalents name native modifier roles, independently of the
 * physical event modifiers. The UI library applies the user's key preferences. */
enum NXSMenuModifier {
  NXS_MENU_COMMAND=1, NXS_MENU_SHIFT=2, NXS_MENU_CONTROL=4, NXS_MENU_ALTERNATE=8
};
enum NXSMenuCapability { NXS_MENU_MODELS=1, NXS_MENU_CANCEL=2, NXS_MENU_LIFECYCLE=4, NXS_MENU_KEY_QUERY=8, NXS_MENU_STATE_SNAPSHOTS=16, NXS_MENU_CONTEXT_POPUPS=32 };
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
  int (*control_toolbar_items)(NXSControl *,const NXSToolbarItem *,uint32_t,uint32_t,uint32_t);
  NXSToolbarState (*control_toolbar_state)(NXSControl *);
  NXSRect (*control_toolbar_item_rect)(NXSControl *,uint64_t);
  int (*control_popup_title)(NXSControl *,const char *);
  int (*control_radio_items)(NXSControl *,const NXSRadioItem *,uint32_t,uint32_t,uint64_t,uint64_t);
  NXSRadioState (*control_radio_state)(NXSControl *);
  NXSRect (*control_radio_item_rect)(NXSControl *,uint64_t);
  int (*control_radio_cell_size)(NXSControl *,double,double);
  double (*control_backing_scale)(NXSControl *);
  int (*control_perform_click)(NXSControl *,uint64_t);
  int (*control_list_items)(NXSControl *,const NXSListItem *,uint32_t,unsigned,uint64_t);
  NXSListState (*control_list_state)(NXSControl *);
  size_t (*control_list_selection)(NXSControl *,uint64_t *,size_t);
  NXSRect (*control_list_item_rect)(NXSControl *,uint64_t);
  int (*control_list_scroll)(NXSControl *,double,double);
  int (*control_scroll_geometry)(NXSControl *,NXSScrollGeometry *);
  int (*control_item_at_point)(NXSControl *,double,double,uint64_t *);
  NXSRect (*control_search_part)(NXSControl *,int);
  int (*control_text_placeholder)(NXSControl *,const char *);
  unsigned (*control_specialized_capabilities)(void);
  int (*control_color_sync)(NXSControl *,const NXSColorModel *);
  int (*control_color_get)(NXSControl *,NXSColorModel *);
  int (*control_date_sync)(NXSControl *,const NXSDateModel *);
  int (*control_date_get)(NXSControl *,NXSDateModel *);
  int (*control_color_open)(NXSControl *,int);
  NXSEventSource *(*event_source_callback)(int,NXSPump,void *);
  NXSFilePanel *(*file_panel_create)(int,NXSFileAllows,void *);
  int (*file_panel_configure)(NXSFilePanel *,const NXSFilePanelConfig *);
  int (*file_panel_run)(NXSFilePanel *);
  int (*file_panel_cancel)(NXSFilePanel *);
  NXSFilePanelState (*file_panel_state)(NXSFilePanel *);
  size_t (*file_panel_result)(NXSFilePanel *,uint32_t,char *,size_t);
  int (*file_panel_choice)(NXSFilePanel *,uint32_t);
  int (*file_panel_destroy)(NXSFilePanel *);
  unsigned (*control_auxiliary_capabilities)(void);
  int (*control_auxiliary_activate)(NXSControl *,const char *);
  unsigned (*file_panel_parent_capabilities)(void);
  int (*scroller_layout)(NXSSize,NXSRect *);
  int (*control_auxiliary_parent)(NXSControl *,const char *);
  uint32_t menu_model_flags; /* Optional supported NXSMenuFlag extensions. */
  int (*control_color_lifecycle)(NXSControl *,unsigned);
  int (*menu_popup)(NXSMenu *,double,double);
  int (*menu_auxiliary_parent)(NXSMenu *,const char *);
  int (*menu_auxiliary_activate)(NXSMenu *,const char *);
  int (*control_set_screen_bounds)(NXSControl *,NXSRect);
  int (*control_outline_items)(NXSControl *,const NXSOutlineItem *,uint32_t);
  NXSEditBindings *(*edit_bindings_create)(void);
  void (*edit_bindings_destroy)(NXSEditBindings *);
  void (*edit_bindings_reset)(NXSEditBindings *);
  int (*edit_bindings_resolve)(NXSEditBindings *,const NXSKeyEvent *,NXSEditCommand,void *);
} NXSNativeUIAPI;
#define NXS_NATIVE_UI_CORE_SIZE offsetof(NXSNativeUIAPI, control_focus)
/* Optional original NSScrollView content rectangle with both scrollers.
 * Consumers derive placement from this rectangle, rather than copying the
 * UI library's left/right or inset policy. Coordinates are top-left points. */
int nxs_scroller_layout(NXSSize,NXSRect *);

/* Optional standard activation-token handoff for a visible native auxiliary
 * window owned by this control. Bit 1 reports backend support. This does not
 * grant focus by itself; the native backend/compositor validates the token.
 * No window is created, shown or selected by this call. */
unsigned nxs_control_auxiliary_capabilities(void);
int nxs_control_auxiliary_activate(NXSControl *,const char *token);
/* Optional xdg-foreign association for the control's existing visible native
 * auxiliary window. NULL clears it. Bit 2 of auxiliary capabilities reports
 * backend support; the compositor authenticates the exported parent. */
int nxs_control_auxiliary_parent(NXSControl *,const char *handle);

/* Loader API. The GNUstep provider is the default. An alternate provider may
 * implement nxs_native_ui_provider(version) and be selected by
 * NEXTSPACE_NATIVE_UI_PROVIDER before the first call. */
const NXSNativeUIAPI *nxs_native_ui_api(void);
const char *nxs_native_ui_error(void);
unsigned nxs_control_specialized_capabilities(void);
unsigned nxs_control_color_panel_capabilities(void);
enum NXSColorPanelCapability {NXS_COLOR_PANEL=1,NXS_COLOR_PANEL_CLOSE_ACK=2};
enum NXSColorClosePhase {
  NXS_COLOR_CLOSE_IMMEDIATE=0,NXS_COLOR_CLOSE_REQUIRE_ACK=1,
  NXS_COLOR_CLOSE_COMPLETE=2,NXS_COLOR_CLOSE_REQUEST=3
};
/* Explicit native color-panel lifecycle. Closing only hides the panel when
 * this well owns it; another well's original native ownership is preserved. */
int nxs_control_color_open(NXSControl *,int open);
/* Enable REQUIRE_ACK before opening for asynchronous model completion.
 * A requested close deactivates the
 * original well, but its panel stays visible until CLOSE_COMPLETE. Completion
 * only closes this well's pending panel; a later native owner is preserved. */
int nxs_control_color_lifecycle(NXSControl *,unsigned phase);
/* File panels are UI-thread objects. Only one may exist at a time. Configure
 * before run; run calls the original native modal method and returns 0/1/2
 * for accepted/cancelled/failed. Cancellation is allowed from a callback source
 * serviced by that modal loop. Configure/destroy reject during run or filter
 * callbacks. The caller retains callback/context ownership until destroy.
 * Results are file URIs; result() returns required bytes including the NUL and
 * copies only if capacity is sufficient. state.result is -1 while running. */
/* Bit 0: native file panels. Bit 1: optional appended portal parent_window. */
unsigned nxs_file_panel_capabilities(void);
/* Read the descriptor in this UI-thread callback. It is also serviced during
 * native modal/tracking loops; descriptor and callback remain caller-owned. */
unsigned nxs_native_ui_callback_source_capabilities(void);
NXSEventSource *nxs_native_ui_source_callback(int,NXSPump,void *);
NXSFilePanel *nxs_file_panel_create(int,NXSFileAllows,void *);
int nxs_file_panel_configure(NXSFilePanel *,const NXSFilePanelConfig *);
int nxs_file_panel_run(NXSFilePanel *);
int nxs_file_panel_cancel(NXSFilePanel *);
NXSFilePanelState nxs_file_panel_state(NXSFilePanel *);
size_t nxs_file_panel_result(NXSFilePanel *,uint32_t,char *,size_t);
int nxs_file_panel_choice(NXSFilePanel *,uint32_t);
int nxs_file_panel_destroy(NXSFilePanel *);
/* Optional typed models for the original native color and date controls.
 * All strings/formatters, drawing, field layout and tracking remain native.
 * Mutations reject tracking/reentry. Getters remain available in callbacks.
 * NSStepper uses control_sync and control_set_step; native input preferences
 * and default wrapping/repeat behavior remain in NSStepper itself. */
int nxs_control_color_sync(NXSControl *,const NXSColorModel *);
int nxs_control_color_get(NXSControl *,NXSColorModel *);
int nxs_control_date_sync(NXSControl *,const NXSDateModel *);
int nxs_control_date_get(NXSControl *,NXSDateModel *);
unsigned nxs_control_list_capabilities(void);
/* Supply flat application rows to the original native list control. Unique,
 * nonzero identifiers and selection are data; native controls own navigation,
 * multi-selection, tracking and scrollbars. No action is emitted by sync.
 * key_cell is zero for native selection-derived focus, or a supplied row ID.
 * Model/scroll mutation during native tracking is rejected. */
int nxs_control_list_items(NXSControl *,const NXSListItem *,uint32_t count,unsigned flags,uint64_t key_cell);
NXSListState nxs_control_list_state(NXSControl *);
/* Returns required capacity; writes the complete selection only when it fits.
 * NULL with zero capacity queries the count. IDs retain all 64 bits. */
size_t nxs_control_list_selection(NXSControl *,uint64_t *,size_t capacity);
NXSRect nxs_control_list_item_rect(NXSControl *,uint64_t identifier);
int nxs_control_list_scroll(NXSControl *,double x,double y);
/* Actual clip frame, unscrolled client size and native scroll limits.
 * Returns unsupported for providers predating this optional extension. */
int nxs_control_scroll_geometry(NXSControl *,NXSScrollGeometry *);
unsigned nxs_control_scroll_capabilities(void);
/* Query the actual native view/cell hit test in top-left control coordinates.
 * A successful query writes a stable model ID, or zero for non-item areas.
 * Unsupported controls/providers and invalid input leave the output intact.
 * This read-only query does not change selection, focus or actions. */
int nxs_control_item_at_point(NXSControl *,double x,double y,uint64_t *identifier);
unsigned nxs_control_outline_capabilities(void);
int nxs_control_outline_items(NXSControl *,const NXSOutlineItem *,uint32_t);
NXSRect nxs_control_search_part(NXSControl *,int part);
unsigned nxs_control_item_hit_capabilities(void);
NXSControl *nxs_control_create(int kind, NXSControlChanged changed, NXSPump pump, void *context);
int nxs_control_destroy(NXSControl *control);
int nxs_control_sync(NXSControl *control, const NXSControlConfig *config);
NXSControlState nxs_control_state(NXSControl *control);
NXSSize nxs_control_size(NXSControl *control);
NXSBitmap nxs_control_draw(NXSControl *control, double scale);
/* Actual native backing density, or zero when unsupported/unavailable. */
double nxs_control_backing_scale(NXSControl *);
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
unsigned nxs_control_toolbar_capabilities(void);
/* Item data uses unique nonzero opaque IDs. Native NSToolbar owns buttons,
 * layout, sizing, images and overflow menus; model updates emit no action.
 * Native activation emits ACTIVATE with the current ordered index in value;
 * toolbar_state.command preserves its exact 64-bit application identity. */
int nxs_control_toolbar_items(NXSControl *,const NXSToolbarItem *,uint32_t count,
  uint32_t display_mode,uint32_t size_mode);
NXSToolbarState nxs_control_toolbar_state(NXSControl *);
/* Return the native visible item rectangle, including an open overflow menu.
 * Unknown or currently hidden items return an empty rectangle. */
NXSRect nxs_control_toolbar_item_rect(NXSControl *,uint64_t identifier);
unsigned nxs_control_input_capabilities(void);
int nxs_control_focus(NXSControl *control, int focused);
int nxs_control_focused(NXSControl *control);
int nxs_control_key(NXSControl *control, const NXSKeyEvent *event);
/* Interpret editing keys for an application-owned editor. The provider uses
 * its actual edit menu and bindings. It emits selectors synchronously, in
 * order. The caller owns insertion, the editor model and command execution.
 * Reset the UI-thread interpreter when its focused editing context changes. */
unsigned nxs_edit_bindings_capabilities(void);
NXSEditBindings *nxs_edit_bindings_create(void);
void nxs_edit_bindings_destroy(NXSEditBindings *);
void nxs_edit_bindings_reset(NXSEditBindings *);
int nxs_edit_bindings_resolve(NXSEditBindings *,const NXSKeyEvent *,NXSEditCommand,void *);
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
unsigned nxs_control_popup_title_capabilities(void);
/* An independent native display title, for application selection that is not
 * a visible menu item. NULL restores the native selected-item title. An empty
 * string is a real override. This does not change menu data or selection and
 * emits no action. Visible menus and native tracking reject title changes. */
int nxs_control_popup_title(NXSControl *, const char *title);
unsigned nxs_control_radio_capabilities(void);
/* One native matrix owns the group's actual radio cells. IDs are unique and
 * nonzero; selected/key_cell name members or zero. Rows follow application
 * order with positive columns. An incomplete last row has disabled native cells
 * in its empty positions; those positions have no application identifiers.
 * Model replacement emits no action, retains cells by identity, and sizes the
 * group to its native preferred size. control_sync may then resize the group.
 * A zero key_cell leaves the new matrix's native selection-derived focus.
 * Native enabled state applies when setting key_cell; configure enabled before
 * requesting a newly enabled key cell. key_cell remains native group context
 * even while the host is unfocused; control_focused reports actual focus.
 * Native ACTIVATE reports the selected index in state.value; radio_state keeps
 * exact selected/key identities and the native action counter separately.
 * Tracking/dispatch reject model replacement and destruction. */
int nxs_control_radio_items(NXSControl *,const NXSRadioItem *,uint32_t count,uint32_t columns,
  uint64_t selected,uint64_t key_cell);
NXSRadioState nxs_control_radio_state(NXSControl *);
/* Native logical cell geometry in the group's bitmap coordinates. */
NXSRect nxs_control_radio_item_rect(NXSControl *,uint64_t identifier);
/* Application cell bounds; native NSMatrix owns layout of the grid. This
 * emits no action and preserves native cell, selection and key identities.
 * Native preferred sizes remain available through control_size. */
int nxs_control_radio_cell_size(NXSControl *,double width,double height);
/* Optional semantic activation for associated labels/accessibility adapters.
 * Native buttons and color wells take item=0; native radio matrices take an existing member ID.
 * Selection, state changes and action dispatch use original native methods.
 * Disabled controls/members, unsupported kinds, tracking and reentry reject it.
 * No mouse or keyboard event is invented; this does not move input focus. */
unsigned nxs_control_activation_capabilities(void);
int nxs_control_perform_click(NXSControl *,uint64_t item);
/* Native menu geometry uses control bitmap coordinates, including positions
 * outside that bitmap. A hidden menu returns a zero frame/item rectangle. */
NXSPopupState nxs_control_popup_state(NXSControl *);
NXSRect nxs_control_popup_item_rect(NXSControl *, int index);
/* Request the control's top-left relative to the native main screen's top-left,
 * in logical units. The backend/compositor determines actual window placement. */
int nxs_control_set_screen_origin(NXSControl *, double x, double y);
/* Project the hosted view's complete bounds into a foreign application's
 * top-left screen rectangle. Native drawing and local input stay unchanged;
 * original window conversions position native menus and auxiliary panels. */
int nxs_control_set_screen_bounds(NXSControl *,NXSRect);
/* Optional native-loop integration for an embedding application's readable
 * descriptors. The source wakes dispatch_events; the caller still reads the
 * descriptor and retains ownership of it. Create/destroy on the UI thread. */
unsigned nxs_native_ui_source_capabilities(void);
NXSEventSource *nxs_native_ui_source_create(int descriptor);
int nxs_native_ui_source_destroy(NXSEventSource *);
unsigned nxs_control_popup_open_capabilities(void);
/* Date controls advertise NXS_SPECIAL_DATE_PANEL for a native calendar/clock
 * panel through this same popup API. No indexed menu items are exposed.
 * Change popup visibility through the native control's methods, without
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
/* Optional plain/secure/search field placeholder. NULL removes it. The
 * original native cell owns display, layout and visibility; value/selection
 * and edit notifications are unaffected. Multiline controls reject it. */
int nxs_control_text_placeholder(NXSControl *,const char *);
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
/* Transient context menu at a top-left logical screen point. Native NSMenu
 * owns placement and tracking; the call returns when native tracking ends. */
int nxs_menu_popup(NXSMenu *,double x,double y);
int nxs_menu_auxiliary_parent(NXSMenu *,const char *);
int nxs_menu_auxiliary_activate(NXSMenu *,const char *);
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

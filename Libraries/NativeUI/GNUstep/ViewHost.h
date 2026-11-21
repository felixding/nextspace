/* Shared native view hosting, not control implementations. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "../NativeUI.h"
typedef struct NXSViewHost NXSViewHost;
typedef struct NXSMenuLoop {
  NXSPump pump;
  void *context;
  struct NXSMenuLoop *previous;
  BOOL tracking;
} NXSMenuLoop;
void nxs_host_menu_begin(NXSMenuLoop *);
void nxs_host_menu_end(NXSMenuLoop *);
int nxs_host_initialize(void);
NXSViewHost *nxs_host_create(NSView *view,NXSPump pump,void *context);
int nxs_host_destroy(NXSViewHost *host);
/* Replace a native view without replacing the host's input, command or screen
 * association. The incoming view supplies its own native size. */
int nxs_host_replace_view(NXSViewHost *,NSView *);
void nxs_host_resize(NXSViewHost *host,NSSize size);
NSArray *nxs_host_document_positions(NXSViewHost *);
void nxs_host_restore_document_positions(NXSViewHost *,NSArray *);
NXSBitmap nxs_host_draw(NXSViewHost *host,double scale);
void nxs_host_track(NXSViewHost *host,double x,double y,unsigned modifiers);
int nxs_host_track_clicks(NXSViewHost *host,double x,double y,unsigned modifiers,unsigned click_count);
void nxs_host_send(NXSViewHost *host,int event,double x,double y,unsigned modifiers);
int nxs_host_tracking(NXSViewHost *host);
/* Opt into native views that return from mouseDown and receive later
 * mouseDragged/mouseUp events, rather than running an NSCell tracking loop. */
void nxs_host_pointer_events(NXSViewHost *,int enabled);
int nxs_host_action(NXSViewHost *,void (*)(NSView *,void *),void *);
int nxs_host_focus(NXSViewHost *host,int focused);
int nxs_host_focused(NXSViewHost *host);
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *event);
int nxs_host_wheel(NXSViewHost *,const NXSWheelEvent *);
int nxs_host_menu_key(NSMenu *,const NXSKeyEvent *);
int nxs_host_responder_key(NSResponder *,NSWindow *,const NXSKeyEvent *);
NXSEditBindings *nxs_host_edit_bindings_create(void);
void nxs_host_edit_bindings_destroy(NXSEditBindings *);
void nxs_host_edit_bindings_reset(NXSEditBindings *);
int nxs_host_edit_bindings_resolve(NXSEditBindings *,const NXSKeyEvent *,NXSEditCommand,void *);
unsigned nxs_host_physical_modifier(unsigned);
int nxs_host_command_filter(NXSViewHost *,NXSCommandFilter,void *);
int nxs_host_command(NXSViewHost *,SEL,unsigned);
double nxs_host_dispatch_events(double maximum_wait);
int nxs_host_needs_display(NXSViewHost *host);
int nxs_host_set_screen_origin(NXSViewHost *host,double x,double y);
int nxs_host_set_screen_bounds(NXSViewHost *,NXSRect);
NXSRect nxs_host_rect_from_view(NXSViewHost *,NSView *,NSRect);
NSView *nxs_host_hit_view(NXSViewHost *,double,double);
NSPoint nxs_host_point_to_view(NXSViewHost *,NSView *,double,double);
void nxs_host_bind_input_window(NXSViewHost *,NSWindow *);
int nxs_host_owns_input_window(NXSViewHost *,NSWindow *);
unsigned nxs_host_auxiliary_capabilities(void);
int nxs_host_auxiliary_activate(NXSViewHost *,const char *);
int nxs_host_auxiliary_parent(NXSViewHost *,const char *);
void nxs_host_unbind_input_windows(NXSViewHost *);

int nxs_gnustep_file_panel_active(void);

/* The original menu asks its window for the initial source pointer. Supply
 * only that embedding coordinate, then restore the real native input stream. */
void nxs_host_popup_pointer(NXSViewHost *,NSWindow *,BOOL);
int nxs_host_window_parent(NSWindow *,const char *);
int nxs_host_window_activate(NSWindow *,const char *);

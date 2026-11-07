/* Shared native view hosting, not control implementations. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "../NativeUI.h"
typedef struct NXSViewHost NXSViewHost;
typedef struct NXSMenuLoop {
  NXSPump pump;
  void *context;
  struct NXSMenuLoop *previous;
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
NXSBitmap nxs_host_draw(NXSViewHost *host,double scale);
void nxs_host_track(NXSViewHost *host,double x,double y,unsigned modifiers);
int nxs_host_track_clicks(NXSViewHost *host,double x,double y,unsigned modifiers,unsigned click_count);
void nxs_host_send(NXSViewHost *host,int event,double x,double y,unsigned modifiers);
int nxs_host_tracking(NXSViewHost *host);
int nxs_host_action(NXSViewHost *,void (*)(NSView *,void *),void *);
int nxs_host_focus(NXSViewHost *host,int focused);
int nxs_host_focused(NXSViewHost *host);
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *event);
int nxs_host_wheel(NXSViewHost *,const NXSWheelEvent *);
int nxs_host_menu_key(NSMenu *,const NXSKeyEvent *);
int nxs_host_command_filter(NXSViewHost *,NXSCommandFilter,void *);
int nxs_host_command(NXSViewHost *,SEL,unsigned);
double nxs_host_dispatch_events(double maximum_wait);
int nxs_host_needs_display(NXSViewHost *host);
int nxs_host_set_screen_origin(NXSViewHost *host,double x,double y);
NXSRect nxs_host_rect_from_view(NXSViewHost *,NSView *,NSRect);
void nxs_host_bind_input_window(NXSViewHost *,NSWindow *);
void nxs_host_unbind_input_windows(NXSViewHost *);

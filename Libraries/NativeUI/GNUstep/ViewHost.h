/* Shared native view hosting, not control implementations. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "../NativeUI.h"
typedef struct NXSViewHost NXSViewHost;
int nxs_host_initialize(void);
NXSViewHost *nxs_host_create(NSView *view,NXSPump pump,void *context);
int nxs_host_destroy(NXSViewHost *host);
void nxs_host_resize(NXSViewHost *host,NSSize size);
NXSBitmap nxs_host_draw(NXSViewHost *host,double scale);
void nxs_host_track(NXSViewHost *host,double x,double y,unsigned modifiers);
void nxs_host_send(NXSViewHost *host,int event,double x,double y,unsigned modifiers);
int nxs_host_tracking(NXSViewHost *host);
int nxs_host_focus(NXSViewHost *host,int focused);
int nxs_host_focused(NXSViewHost *host);
int nxs_host_key(NXSViewHost *host,const NXSKeyEvent *event);

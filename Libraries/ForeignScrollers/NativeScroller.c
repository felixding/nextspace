/* Legacy scrollbar ABI; every operation forwards to the selected UI provider.
 * GPL-2.0-or-later. */
#include "NativeScroller.h"
#include <stddef.h>
NXSScroller *nxs_scroller_create(int horizontal,NXSChanged changed,NXSPump pump,void *context)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_create(horizontal,changed,pump,context):NULL;}
void nxs_scroller_destroy(NXSScroller *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->scroller_destroy(c);}
double nxs_scroller_width(void)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_width():0;}
void nxs_scroller_sync(NXSScroller *c,double length,double lower,double upper,double page,double step,double page_step,double value,int enabled)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->scroller_sync(c,length,lower,upper,page,step,page_step,value,enabled);}
NXSBitmap nxs_scroller_draw(NXSScroller *c,double scale)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_draw(c,scale):(NXSBitmap){0};}
NXSRect nxs_scroller_part(NXSScroller *c,int part)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_part(c,part):(NXSRect){0};}
void nxs_scroller_track(NXSScroller *c,double x,double y,unsigned modifiers)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->scroller_track(c,x,y,modifiers);}
void nxs_scroller_send(NXSScroller *c,int event,double x,double y,unsigned modifiers)
{const NXSNativeUIAPI *p=nxs_native_ui_api();if(p)p->scroller_send(c,event,x,y,modifiers);}
int nxs_scroller_tracking(NXSScroller *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_tracking(c):0;}
int nxs_scroller_hit_part(NXSScroller *c)
{const NXSNativeUIAPI *p=nxs_native_ui_api();return p?p->scroller_hit_part(c):0;}

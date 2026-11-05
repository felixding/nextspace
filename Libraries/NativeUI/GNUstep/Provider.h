/* GNUstep binding declarations, private to this provider. GPL-2.0-or-later. */
#include "../NativeUI.h"
NXSScroller *nxs_gnustep_scroller_create(int,NXSChanged,NXSPump,void *);
void nxs_gnustep_scroller_destroy(NXSScroller *);
double nxs_gnustep_scroller_width(void);
void nxs_gnustep_scroller_sync(NXSScroller *,double,double,double,double,double,double,double,int);
NXSBitmap nxs_gnustep_scroller_draw(NXSScroller *,double);
NXSRect nxs_gnustep_scroller_part(NXSScroller *,int);
void nxs_gnustep_scroller_track(NXSScroller *,double,double,unsigned);
void nxs_gnustep_scroller_send(NXSScroller *,int,double,double,unsigned);
int nxs_gnustep_scroller_tracking(NXSScroller *);
int nxs_gnustep_scroller_hit_part(NXSScroller *);
NXSControl *nxs_gnustep_control_create(int,NXSControlChanged,NXSPump,void *);
int nxs_gnustep_control_destroy(NXSControl *);
int nxs_gnustep_control_sync(NXSControl *,const NXSControlConfig *);
NXSControlState nxs_gnustep_control_state(NXSControl *);
NXSSize nxs_gnustep_control_size(NXSControl *);
NXSBitmap nxs_gnustep_control_draw(NXSControl *,double);
void nxs_gnustep_control_track(NXSControl *,double,double,unsigned);
void nxs_gnustep_control_send(NXSControl *,int,double,double,unsigned);

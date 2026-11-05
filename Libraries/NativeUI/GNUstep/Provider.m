/* The provider binds the C contract to GNUstep's actual controls. GPL-2.0-or-later. */
#include "Provider.h"
__attribute__((visibility("default"))) const NXSNativeUIAPI *nxs_native_ui_provider(uint32_t version)
{
  static const NXSNativeUIAPI api={
    .version=NXS_NATIVE_UI_ABI,.size=sizeof(NXSNativeUIAPI),
    .scroller_create=nxs_gnustep_scroller_create,.scroller_destroy=nxs_gnustep_scroller_destroy,
    .scroller_width=nxs_gnustep_scroller_width,.scroller_sync=nxs_gnustep_scroller_sync,
    .scroller_draw=nxs_gnustep_scroller_draw,.scroller_part=nxs_gnustep_scroller_part,
    .scroller_track=nxs_gnustep_scroller_track,.scroller_send=nxs_gnustep_scroller_send,
    .scroller_tracking=nxs_gnustep_scroller_tracking,.scroller_hit_part=nxs_gnustep_scroller_hit_part,
    .control_create=nxs_gnustep_control_create,.control_destroy=nxs_gnustep_control_destroy,
    .control_sync=nxs_gnustep_control_sync,.control_state=nxs_gnustep_control_state,
    .control_size=nxs_gnustep_control_size,.control_draw=nxs_gnustep_control_draw,
    .control_track=nxs_gnustep_control_track,.control_send=nxs_gnustep_control_send,
    .control_focus=nxs_gnustep_control_focus,.control_focused=nxs_gnustep_control_focused,
    .control_key=nxs_gnustep_control_key,
    .dispatch_events=nxs_host_dispatch_events,
    .control_needs_display=nxs_gnustep_control_needs_display,
    .control_set_step=nxs_gnustep_control_set_step,
    .control_popup_items=nxs_gnustep_control_popup_items,
    .control_popup_state=nxs_gnustep_control_popup_state,
    .control_popup_item_rect=nxs_gnustep_control_popup_item_rect,
    .control_set_screen_origin=nxs_gnustep_control_set_screen_origin,
    .event_source_create=nxs_gnustep_source_create,
    .event_source_destroy=nxs_gnustep_source_destroy,
    .control_popup_open=nxs_gnustep_control_popup_open,
    .control_text_sync=nxs_gnustep_control_text_sync,
    .control_text_get=nxs_gnustep_control_text_get,
    .control_text_filter=nxs_gnustep_control_text_filter,
    .control_text_command=nxs_gnustep_control_text_command,
    .control_track_clicks=nxs_gnustep_control_track_clicks
  };
  return version==NXS_NATIVE_UI_ABI?&api:0;
}

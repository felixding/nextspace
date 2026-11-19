/* Exact libxul build ace600697490ec169e3e371fb456dcb542e3abef. */
#define NXS_GECKO_GEOMETRY_COMPUTE 0x6aa4930ul
static const unsigned char gecko_geometry_compute_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0xc3,0x03,0xd1,0xfe,0x67,0x0b,0xa9,0xf8,0x5f,0x0c,0xa9,0xf6,0x57,0x0d,0xa9};
#define NXS_GECKO_GEOMETRY_TOPLEVEL 0x6aa3000ul
static const unsigned char gecko_geometry_toplevel_bytes[20]={0x5f,0x24,0x03,0xd5,0x00,0xd0,0x40,0xf9,0xd2,0x67,0xcb,0x14,0x3f,0x23,0x03,0xd5,0xfe,0x4f,0xbf,0xa9};
#define NXS_GECKO_GEOMETRY_FROM_WINDOW 0x6a9fa30ul
static const unsigned char gecko_geometry_from_window_bytes[20]={0x5f,0x24,0x03,0xd5,0x01,0xb6,0xfc,0x90,0x21,0x9c,0x3b,0x91,0x29,0x75,0xcb,0x14,0x3f,0x23,0x03,0xd5};
#define NXS_GECKO_GEOMETRY_RECOMPUTE 0x6aa4f04ul
static const unsigned char gecko_geometry_recompute_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0x03,0x05,0xd1,0xfd,0x7b,0x0f,0xa9,0xfa,0x67,0x10,0xa9,0xf8,0x5f,0x11,0xa9};
#define NXS_GECKO_GEOMETRY_ADDREF 0x37eb6b8ul
static const unsigned char gecko_geometry_addref_bytes[20]={0x5f,0x24,0x03,0xd5,0xea,0xb4,0xeb,0x17,0x5f,0x24,0x03,0xd5,0x00,0xe0,0x00,0x91,0xe4,0xf6,0x01,0x14};
#define NXS_GECKO_GEOMETRY_RELEASE 0x6a4f220ul
static const unsigned char gecko_geometry_release_bytes[20]={0x5f,0x24,0x03,0xd5,0xff,0x67,0xff,0x17,0x5f,0x24,0x03,0xd5,0x00,0xc0,0x05,0xd1,0xfc,0x67,0xff,0x17};
static int guard_geometry_calls(void) {return !memcmp((void *)(base+NXS_GECKO_GEOMETRY_COMPUTE),gecko_geometry_compute_bytes,20)&&
!memcmp((void *)(base+NXS_GECKO_GEOMETRY_TOPLEVEL),gecko_geometry_toplevel_bytes,20)&&
!memcmp((void *)(base+NXS_GECKO_GEOMETRY_FROM_WINDOW),gecko_geometry_from_window_bytes,20)&&
!memcmp((void *)(base+NXS_GECKO_GEOMETRY_RECOMPUTE),gecko_geometry_recompute_bytes,20)&&
!memcmp((void *)(base+NXS_GECKO_GEOMETRY_ADDREF),gecko_geometry_addref_bytes,20)&&
!memcmp((void *)(base+NXS_GECKO_GEOMETRY_RELEASE),gecko_geometry_release_bytes,20);}

#define NXS_GECKO_GEOMETRY_ROOT_FRAME 0x6daae44ul
static const unsigned char gecko_geometry_root_frame_bytes[20]={0x5f,0x24,0x03,0xd5,0x08,0x14,0x40,0xf9,0x08,0x11,0x40,0xf9,0x08,0x41,0x40,0xf9,0x00,0x05,0x40,0xf9};

#define NXS_GECKO_GEOMETRY_CLIENT_RECT 0x6e8651cul
static const unsigned char gecko_geometry_client_rect_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1e,0xf8,0xf4,0x4f,0x01,0xa9,0xf3,0x03,0x00,0xaa,0xf4,0x03,0x08,0xaa};

#define NXS_GECKO_GEOMETRY_SCREEN_APP_UNITS 0x6e84fd8ul
static const unsigned char gecko_geometry_screen_app_units_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0x83,0x01,0xd1,0xfe,0x13,0x00,0xf9,0xf8,0x5f,0x03,0xa9,0xf6,0x57,0x04,0xa9};
static int guard_frame_geometry_calls(void) {return !memcmp((void *)(base+NXS_GECKO_GEOMETRY_ROOT_FRAME),gecko_geometry_root_frame_bytes,20)&&!memcmp((void *)(base+NXS_GECKO_GEOMETRY_CLIENT_RECT),gecko_geometry_client_rect_bytes,20)&&!memcmp((void *)(base+NXS_GECKO_GEOMETRY_SCREEN_APP_UNITS),gecko_geometry_screen_app_units_bytes,20);}

/* Original WindowUtils accounts for cross-document CSS transforms, visual
 * viewport resolution and the widget-to-toplevel transform before projection.
 * DOMRect's final four doubles begin at48 in this exact binary. */
#define NXS_GECKO_WINDOW_UTILS 0x46d83d4ul
#define NXS_GECKO_ELEMENT_SCREEN_RECT 0x468fdf8ul
#define NXS_GECKO_TO_SCREEN_CSS_RECT 0x468feacul
#define NXS_GECKO_DOM_RECT_RELEASE 0x3b9f134ul
#define NXS_GECKO_DESKTOP_SCALE 0x46b241cul
#define NXS_GECKO_CHROME_PIXEL_UNITS 0x400e964ul
static int guard_projected_geometry_calls(void)
{
  static const uint32_t owner[]={0xd503233f,0xf81e0ffe,0xa9014ff4,0xaa0003f3,0xf940c800};
  static const uint32_t element[]={0xd503233f,0xd10103ff,0xf90013fe,0xa9034ff4,0x9002e2a8};
  static const uint32_t screen[]={0xd503233f,0xd10203ff,0x6d032beb,0x6d0423e9,0xf9002bfe};
  static const uint32_t fields[]={0xa90026c8,0xad0182c0,0x97d43c14};
  static const uint32_t desktop[]={0xd503233f,0xd100c3ff,0xa90157fe,0xa9024ff4,0xb002e188};
  static const uint32_t chrome[]={0xd503233f,0xa9bf4ffe,0xb9401413,0x94aa0ae6,0x1e2e1001};
  return !memcmp((void *)(base+NXS_GECKO_WINDOW_UTILS),owner,sizeof(owner))&&
    !memcmp((void *)(base+NXS_GECKO_ELEMENT_SCREEN_RECT),element,sizeof(element))&&
    !memcmp((void *)(base+NXS_GECKO_TO_SCREEN_CSS_RECT),screen,sizeof(screen))&&
    !memcmp((void *)(base+0x469008c),fields,sizeof(fields))&&
    !memcmp((void *)(base+NXS_GECKO_DESKTOP_SCALE),desktop,sizeof(desktop))&&
    !memcmp((void *)(base+NXS_GECKO_CHROME_PIXEL_UNITS),chrome,sizeof(chrome))&&
    *(const uint32_t *)(base+0x468ff3c)==0xf9401800; /* PresContext::DeviceContext +48 */
}

/* nsWindowWayland's first-popup path assumes a toplevel origin of zero.
 * NEXTSPACE supplies desktop origins, so use its existing parent subtraction
 * and WidgetToScreenOffsetUnscaled for toplevel parents as well as popups.
 * These witnesses include both original conversion calls; null-parent guards,
 * GTK placement, gravity, constraints and nested-popup handling stay original. */
#define NXS_GECKO_POPUP_ANCHOR_PARENT 0x6abc720ul
static const uint32_t gecko_popup_anchor_parent_words[]={
  0xf9422e68,0xaa0003f7,0xaa0103f6,0xb40002e8,
  0xf9422508,0xb40002a8,0xaa1303e0,0x940000a6
};
#define NXS_GECKO_POPUP_PARENT_POSITION 0x6abca40ul
static const uint32_t gecko_popup_parent_position_words[]={
  0xaa0003f4,0x97ff899e,0x360002c0,0xaa1403e0,0x97376726,0xaa0003f5
};
static int guard_popup_geometry_calls(void)
{
  return !memcmp((void *)(base+NXS_GECKO_POPUP_ANCHOR_PARENT),
    gecko_popup_anchor_parent_words,sizeof(gecko_popup_anchor_parent_words))&&
    !memcmp((void *)(base+NXS_GECKO_POPUP_PARENT_POSITION),
    gecko_popup_parent_position_words,sizeof(gecko_popup_parent_position_words));
}

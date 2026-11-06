/* Native display-item transport is shared by webpage and frontend fields.
 * The parent-only predicate additionally admits browser HTML text frames.
 * No browser CSS, text geometry or UI component is reproduced here. */
static __thread void *frontend_background_frame;
static int (*original_frontend_themed)(const void *,const void *,int *);
static void (*original_frontend_paint)(void *,void *,void *);
static int (*original_frontend_webrender)(void *,void *,void *,void *,void *,void *);
static int frontend_text_frame(const void *frame) {
  /* Evaluate Gecko's real process role at use time: libxul can be loaded
   * before a child has finished initializing its process role. */
  return frame&&frontend_requested&&((int (*)(void))(base+0x7546c5c))();
}
static int frontend_themed(const void *frame,const void *display,int *transparency) {
  if(frame==frontend_background_frame) {
    if(transparency)*transparency=0; /* nsITheme::eOpaque, actual native bitmap. */
    return 1;
  }
  return original_frontend_themed(frame,display,transparency);
}
static void *frontend_item_frame(void *item) {
  /* Actual virtual StyleFrame(), also used by these compiled paint methods. */
  return ((void *(*)(void *))(*(uintptr_t **)item)[20])(item);
}
static int frontend_item_owned(void *frame) {
  struct Widget *w=widget_for_frame(frame);
  return w&&w->text_owned;
}
static int frontend_webrender(void *item,void *builder,void *resources,void *stacking,void *manager,void *display_builder) {
  void *frame=frontend_item_frame(item);
  if(frame_kind(frame)==NXS_BUTTON)prepare_button_image(frame);
  /* The active nsITheme can be GTK even for web content. Select Gecko's
   * existing fallback at the display item, before virtual theme dispatch. */
  if(frontend_item_owned(frame)||eligible(frame,*((const unsigned char *)item+156)))return 0;
  return original_frontend_webrender(item,builder,resources,stacking,manager,display_builder);
}
static void frontend_paint(void *item,void *builder,void *context) {
  void *frame=frontend_item_frame(item);
  if(frame_kind(frame)==NXS_BUTTON)prepare_button_image(frame);
  if(frontend_item_owned(frame)) {
    /* GetDrawTarget is inlined at Theme::DrawWidgetBackground (+216).
     * mBackgroundRect (+120) and StyleFrame's virtual slot are independently
     * present in the actual nsDisplayThemedBackground::Paint disassembly. */
    void *target=*(void **)((char *)context+216);
    void *pres_context=*(void **)((char *)frame+40);
    double units=*(int *)((char *)pres_context+200);
    struct RectF area=((struct RectF (*)(const void *,double,const void *))(base+0x6db633c))((char *)item+120,units,target);
    if(draw_text_image(target,frame,&area))return;
  }
  original_frontend_paint(item,builder,context);
}
static const unsigned char frontend_paint_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0x83,0x01,0xd1,0xfe,0x1b,0x00,0xf9,0xf6,0x57,0x04,0xa9,0xf4,0x4f,0x05,0xa9};
static const unsigned char frontend_webrender_bytes[20]={0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1c,0xf8,0xf8,0x5f,0x01,0xa9,0xf6,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9};
static struct Detour frontend_detours[]={
  {NXS_GECKO_TEXT_IS_THEMED_OFFSET,gecko_text_is_themed_bytes,frontend_themed,(void **)&original_frontend_themed}
};
static struct Detour background_detours[]={
  {0x6fe2358,frontend_paint_bytes,frontend_paint,(void **)&original_frontend_paint},
  {0x6fe2464,frontend_webrender_bytes,frontend_webrender,(void **)&original_frontend_webrender}
};
static int prepare_background_bindings(void) {
  static const unsigned char target_bytes[8]={0x5f,0x24,0x03,0xd5,0x21,0x6c,0x40,0xf9};
  return !memcmp((void *)(base+0x6a5fbac),target_bytes,8)&&
    /* Actual StyleFrame virtual slot and appearance-byte load in the
     * compiled display-item WebRender method, not a copied theme layout. */
    !memcmp((void *)(base+0x6fe2490),(unsigned char[]){0x08,0x51,0x40,0xf9},4)&&
    !memcmp((void *)(base+0x6fe24bc),(unsigned char[]){0xc6,0x72,0x42,0x39},4)&&
    prepare_detours(background_detours,sizeof(background_detours)/sizeof(*background_detours));
}
static int prepare_frontend_bindings(void) {
  static const unsigned char parent_bytes[20]={0x5f,0x24,0x03,0xd5,0xe8,0x6c,0x01,0xd0,0x08,0xad,0x40,0xf9,0x08,0x01,0x40,0xb9,0x1f,0x01,0x00,0x71};
  return !memcmp((void *)(base+0x7546c5c),parent_bytes,20)&&
    prepare_detours(frontend_detours,sizeof(frontend_detours)/sizeof(*frontend_detours));
}

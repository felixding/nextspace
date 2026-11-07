/* The existing NSButton supplies complete title pixels and preferred size.
 * Blink retains DOM notifications, trusted actions and CSS layout. */
static void (*original_button_children)(void *,const void *);
static void (*original_button_attribute)(void *,const void *);
static void (*original_button_value)(void *,const void *,int,int,int);
static int native_button_owned(const struct NativeForm *form) {
  void *layout=form?decode_member((const char *)form->node+48):NULL;
  return form&&form->painted&&layout&&form->button_style==decode_member((char *)layout+32);
}
static int native_button_preferred(const void *node,const void *layout,struct SizeI *size) {
  struct NativeForm *form=find_form(node);
  if(!form||form->kind!=NXS_BUTTON||!native_button_owned(form)||!native_layout_unit_scale(node,layout)||form->preferred_width<1||form->preferred_height<1)return 0;
  *size=(struct SizeI){ceil(form->preferred_width),ceil(form->preferred_height)};return 1;
}
static void native_button_size_changed(struct NativeForm *form,const struct NXSResponse *response) {
  double width=response->parts[1].width,height=response->parts[1].height;
  if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>8192||height>8192)return;
  void *layout=decode_member((char *)form->node+48),*style=layout?decode_member((char *)layout+32):NULL;
  if(form->preferred_width==width&&form->preferred_height==height&&form->button_style==style)return;
  form->preferred_width=width;form->preferred_height=height;form->button_style=style;
  form->button_size_pending=1;native_button_size_work_pending=1;
  if(current_controller)((void (*)(void *))(base+NXS_LAYOUT_SCHEDULE_OFFSET))(current_controller);
}
static void native_button_size_work(void) {
  if(!native_button_size_work_pending)return;native_button_size_work_pending=0;
  for(struct NativeForm *form=native_forms;form;form=form->next) {
    if(!form->button_size_pending)continue;form->button_size_pending=0;
    void *layout=decode_member((char *)form->node+48);
    if(layout)((void (*)(void *,const char *))(base+NXS_LAYOUT_INVALIDATE_OFFSET))(layout,"Native control preferred size changed");
  }
}
static void native_button_model_changed(void *node,uint64_t control) {
  struct NativeForm *form=find_form(node);
  if(form&&form->control==control&&form->kind==NXS_BUTTON)invalidate_form(form);
}
static void button_children(void *node,const void *change) {
  struct NativeForm *form=bound_form_ancestor(node,NXS_BUTTON);void *owner=form?form->node:NULL;uint64_t control=form?form->control:0;
  original_button_children(node,change);
  if(control)native_button_model_changed(owner,control);
}
static void button_attribute(void *node,const void *params) {
  struct NativeForm *form=bound_form_ancestor(node,NXS_BUTTON);void *owner=form?form->node:NULL;uint64_t control=form?form->control:0;
  original_button_attribute(node,params);
  if(control)native_button_model_changed(owner,control);
}
static void button_value(void *node,const void *value,int behavior,int selection,int autofill) {
  struct NativeForm *form=find_form(node);uint64_t control=form?form->control:0;
  original_button_value(node,value,behavior,selection,autofill);
  if(control)native_button_model_changed(node,control);
}
static struct Detour button_model_detours[]={
 {NXS_LAYOUT_CHILDREN_OFFSET,nxs_layout_children_bytes,button_children,(void **)&original_button_children},
 {NXS_LAYOUT_ATTRIBUTE_OFFSET,nxs_layout_attribute_bytes,button_attribute,(void **)&original_button_attribute},
 {NXS_LAYOUT_VALUE_OFFSET,nxs_layout_value_bytes,button_value,(void **)&original_button_value}
};

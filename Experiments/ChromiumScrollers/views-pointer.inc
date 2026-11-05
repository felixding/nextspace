/* Views capture/model bindings; actual NSTextField owns pointer selection. */
static int (*original_views_pointer_press)(void *,const void *,int,int);
static int (*original_views_pointer_drag)(void *,const void *);
static void (*original_views_pointer_release)(void *,const void *);
static void (*original_views_pointer_lost)(void *);
static struct ViewsField *find_views_controller(const void *controller) {
  /* Actual Textfield::OnMouseDragged adds 0x510 to its Textfield base. */
  for(struct ViewsField *f=views_fields;f;f=f->next)
    if((const char *)f->transport.node+0x510==controller)return f;
  return NULL;
}
static int views_pointer_echo(struct ViewsField *f) {
  if(!f->transport.text_tracking)return 0;
  struct BlinkTextModel model={0};if(!views_model(f->transport.node,&model))return 0;
  struct NXSResponse *response=text_native_state(&f->transport);
  int same=0;struct NXSTextResponse state={0};
  if(response) {
    memcpy(&state,response+1,sizeof(state));size_t length=strlen(model.value);
    same=state.text_size==length&&response->size==sizeof(*response)+sizeof(state)+length&&
      !memcmp((char *)(response+1)+sizeof(state),model.value,length)&&!!(state.flags&2)==!!model.editable&&
      response->parts[2].x&&response->parts[3].y&&original_views_has_focus(f->transport.node)&&
      *(const unsigned char *)((char *)f->transport.node+458)==1&&
      *(const int *)((char *)f->transport.node+448)==f->transport.text_width&&
      *(const int *)((char *)f->transport.node+452)==f->transport.text_height&&
      model.start==f->transport.text_start&&model.end==f->transport.text_end;
  }
  if(same&&state.selection_start<=UINT32_MAX&&state.selection_length<=UINT32_MAX-state.selection_start) {
    f->transport.text_start=state.selection_start;f->transport.text_end=state.selection_start+state.selection_length;
    if(model.start!=f->transport.text_start||model.end!=f->transport.text_end) {
      struct ViewsRange range={f->transport.text_start,f->transport.text_end};
      ((int (*)(void *,const void *))(base+NXS_CHROMIUM_VIEWS_SELECTION_OFFSET))(f->transport.node,&range);
    }
  }
  free(model.value);return same;
}
static void views_pointer_end(struct ViewsField *f,int echo) {
  if(!f->transport.text_tracking)return;
  struct NXSResponse *response=form_request(&f->transport,4,f->transport.text_x,f->transport.text_y,f->pointer_modifiers);
  for(int n=0;response&&response->parts[0].y&&n<100;n++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=form_request(&f->transport,5,0,0,0);
  }
  if(echo)views_pointer_echo(f);
  f->transport.text_tracking=0;views_schedule(f->transport.node);
}
static int views_pointer_press(void *controller,const void *event,int handled,int initial_focus) {
  struct ViewsField *f=find_views_controller(controller);
  unsigned flags=*(const unsigned *)((const char *)event+80);
  /* These are the actual ui::MouseEvent click-count flags, not a local
   * click aggregator. The native editor interprets the supplied count. */
  unsigned clicks=(flags&(1u<<17))?3:(flags&(1u<<16))?2:1;
  if(f&&f->owned&&!handled&&(flags&0xf800)==0x800&&
     (clicks==1||(forms_pointer_capabilities&NXS_POINTER_CLICK_COUNT))&&
     original_views_has_focus(f->transport.node)&&
     !((int (*)(const void *))(base+NXS_CHROMIUM_VIEWS_COMPOSITION_OFFSET))(f->transport.node)) {
    views_pointer_end(f,1);f->pointer_owned=0;
    struct NXSResponse *response=views_sync(f);struct BlinkTextModel model={0};
    if(response&&views_model(f->transport.node,&model)) {
      const float *point=(const float *)((const char *)event+136);
      response=clicks==1?form_request(&f->transport,2,point[0],point[1],views_modifiers(event)):
        native_pointer_press(f->transport.kind,f->transport.control,point[0],point[1],views_modifiers(event),clicks);
      if(response&&response->parts[0].y) {
        f->pointer_owned=1;f->pointer_modifiers=views_modifiers(event);f->transport.text_tracking=1;
        f->transport.text_start=model.start;f->transport.text_end=model.end;
        f->transport.text_width=f->transport.rect.width;f->transport.text_height=f->transport.rect.height;
        f->transport.text_x=point[0];f->transport.text_y=point[1];
        /* The original handled path retains real click-count/drag-threshold
         * bookkeeping without entering engine selection geometry. */
        original_views_pointer_press(controller,event,1,initial_focus);
        views_pointer_echo(f);views_schedule(f->transport.node);free(model.value);return 1;
      }
      free(model.value);
    }
  }
  return original_views_pointer_press(controller,event,handled,initial_focus);
}
static int views_pointer_drag(void *controller,const void *event) {
  struct ViewsField *f=find_views_controller(controller);
  if(f&&f->pointer_owned) {
    if(f->transport.text_tracking) {
      const float *point=(const float *)((const char *)event+136);
      f->transport.text_x=point[0];f->transport.text_y=point[1];
      f->pointer_modifiers=views_modifiers(event);
      form_request(&f->transport,3,point[0],point[1],f->pointer_modifiers);
      if(!views_pointer_echo(f))views_pointer_end(f,0);
      views_schedule(f->transport.node);
    }
    return 1;
  }
  return original_views_pointer_drag(controller,event);
}
static void views_pointer_release(void *controller,const void *event) {
  struct ViewsField *f=find_views_controller(controller);
  if(f&&f->pointer_owned){f->pointer_modifiers=views_modifiers(event);views_pointer_end(f,1);f->pointer_owned=0;}
  /* Retain real primary-clipboard and capture bookkeeping after native release. */
  original_views_pointer_release(controller,event);
}
static void views_pointer_lost(void *controller) {
  struct ViewsField *f=find_views_controller(controller);
  if(f&&f->pointer_owned){views_pointer_end(f,1);f->pointer_owned=0;}
  original_views_pointer_lost(controller);
}

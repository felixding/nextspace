/* Original Gecko number models composed with the shared NSTextField/NSStepper.
 * No numeric policy, editor, arrow drawing or repeat loop. GPL-2.0-or-later. */
static void *number_active_node;
static uint64_t number_active_control;
static __thread struct {const void *event;void *node;uint64_t control;} number_default;
static int number_node(const void *node)
{
  return numbers_enabled&&native_web_process()&&node&&*(const uintptr_t *)node==base+0xa00fc30+16&&
    *((const unsigned char *)node+144)==139;
}
static int number_mutable(const void *node)
{return number_node(node)&&!(*(const uint64_t *)((const char *)node+112)&0x800010u);}
static int number_tracking(const struct Widget *w)
{return number_active_node==w->node&&number_active_control==w->id;}
static struct NXSResponse *number_request(struct Widget *w,unsigned operation,double x,double y,unsigned modifiers)
{
  return native_stepper_request(w->number_stepper.control,operation,w->number_rect.width,w->number_rect.height,
    number_mutable(w->node),x,y,modifiers);
}
static int number_pixels(struct Widget *w,const struct NXSResponse *response)
{
  if(!response||response->width!=lround(w->number_rect.width)||response->height!=lround(w->number_rect.height)||
     response->width<1||response->height<1||response->stride!=response->width*4||
     response->size!=sizeof(*response)+(size_t)response->stride*response->height)return 0;
  size_t bytes=(size_t)response->stride*response->height;
  uint32_t *pixels=malloc(bytes);if(!pixels)return 0;
  memcpy(pixels,response+1,bytes);free(w->number_pixels);w->number_pixels=pixels;
  w->number_pixel_width=response->width;w->number_pixel_height=response->height;return 1;
}
static int number_prepare(struct Widget *w,double width,double height)
{
  void *button=((void *(*)(const void *))(base+NXS_GECKO_NUMBER_BUTTON))(w->frame);
  if(!button)return 0;
  int bounds[4]={0};engine_frame_rect((void *)(base+0x6daae5c),button,bounds);
  struct PointI offset=((struct PointI (*)(const void *,const void *))(base+NXS_GECKO_NUMBER_OFFSET))(button,w->frame);
  struct NXSRectD rect={offset.x/60.,offset.y/60.,bounds[2]/60.,bounds[3]/60.};
  if(rect.x<1||rect.y<0||rect.width<1||rect.height<1||rect.x+rect.width>width||rect.y+rect.height>height)return 0;
  w->number_rect=rect;w->number_width=width;w->number_height=height;w->width=rect.x;
  if(!w->number_stepper.control)w->number_stepper.control=++next_widget;
  if(!ensure_text_watch())return 0;
  struct NXSResponse *response=number_request(w,number_tracking(w)?5:1,0,0,0);
  if(!number_pixels(w,response))return 0;
  if(!w->number_stepper.ready||w->number_stepper.epoch!=atomic_load(&native_host_epoch)) {
    struct NXSStepperBatch baseline;
    if(native_stepper_actions(&w->number_stepper,1,&baseline)<1)return 0;
  }
  return 1;
}
static int number_draw(void *target,struct Widget *w,const struct RectF *area)
{
  if(!w->number_pixels||lround(area->width)!=lround(w->number_width)||
     lround(area->height)!=lround(w->number_height))return 0;
  struct RectF rect={area->x+w->number_rect.x,area->y+w->number_rect.y,
    w->number_rect.width,w->number_rect.height};
  draw_bitmap(target,&rect,w->number_pixels,w->number_pixel_width,w->number_pixel_height);
  if(log_fd>=0)dprintf(log_fd,"%d native-number id=%llu stepper=%llu rect=%.3f,%.3f %.3fx%.3f\n",getpid(),
    (unsigned long long)w->id,(unsigned long long)w->number_stepper.control,
    w->number_rect.x,w->number_rect.y,w->number_rect.width,w->number_rect.height);
  return 1;
}
static struct PointI number_point(struct Widget *w,const void *event)
{
  struct PointI point=widget_point(w,event);
  point.x-=lround(w->number_rect.x*60);point.y-=lround(w->number_rect.y*60);return point;
}
static int number_hit(struct Widget *w,const void *event)
{
  if(!number_node(w->node)||!w->number_pixels)return 0;
  struct PointI point=number_point(w,event);
  /* Route to the original spin-box component only. NSStepper chooses arrows. */
  return point.x>=0&&point.y>=0&&point.x<w->number_rect.width*60&&point.y<w->number_rect.height*60;
}
static int number_default_pointer(void *node,void *visitor)
{
  if(!number_mutable(node))return 0;
  void *event=*(void **)((char *)visitor+8);int *status=(int *)((char *)visitor+24);
  struct Widget *w=widget_for_node(node);
  if(!w||!w->painted||!w->number_stepper.ready||*status==1||
     *(const uint16_t *)((char *)event+18)!=15||*(const int16_t *)((char *)event+152)!=0||
     !(*(const uint8_t *)((char *)event+48)&1)||(*((const uint8_t *)event+49)&2)||!number_hit(w,event))return 0;
  /* Retain the engine's consumed default-action result after DOM listeners,
   * so its later post handler does not turn the spinner into an editor click.
   * Only native NSStepper will execute the action and repeat. */
  number_default.event=event;number_default.node=node;number_default.control=w->id;*status=1;return 1;
}
static void number_apply(struct Widget *w)
{
  struct NXSStepperBatch batch;uint64_t control=w->id;void *node=w->node;
  int accepted=native_stepper_actions(&w->number_stepper,0,&batch);
  if(accepted<0){note("native Gecko number receipts unavailable");return;}
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  for(unsigned i=0;accepted&&i<batch.count;i++) {
    w=widget_for_node(node);if(!w||w->id!=control||!number_mutable(node))break;
    ((void (*)(void *,int))(base+NXS_GECKO_NUMBER_STEP))(node,batch.directions[i]);
  }
  w=widget_for_node(node);if(w&&w->id==control)invalidate_widget(w);
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static void number_end(int commit,const void *event)
{
  void *node=number_active_node;uint64_t control=number_active_control;
  number_active_node=NULL;number_active_control=0;if(!node)return;
  struct Widget *w=widget_for_node(node);
  if(w&&w->id==control) {
    struct PointI point=event?number_point(w,event):(struct PointI){-600000,-600000};
    struct NXSResponse *response=number_request(w,4,point.x/60.,point.y/60.,event?widget_modifiers(event):0);
    for(unsigned n=0;response&&response->parts[0].y&&n<100;n++) {
      struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);response=number_request(w,5,0,0,0);
    }
    number_apply(w);
    if(commit&&number_node(node))((void (*)(void *))(base+NXS_GECKO_NUMBER_CHANGE))(node);
    w=widget_for_node(node);if(w&&w->id==control)invalidate_widget(w);
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
}
static int number_pointer_post(void *self,void *context,void *event,void *frame,int *status,void *override,uint32_t *result)
{
  if(!numbers_enabled||!(*(const uint8_t *)((char *)event+48)&1))return 0;
  unsigned message=*(const uint16_t *)((char *)event+18);
  if(message!=13&&message!=14&&message!=15)return 0;
  int primary=*(const int16_t *)((char *)event+152)==0;
  if(message!=13&&!primary)return 0;
  struct Widget *w=number_active_node?widget_for_node(number_active_node):NULL;
  if(!w&&message==15) {
    if(number_default.event==event) {
      w=widget_for_node(number_default.node);
      if(w&&w->id!=number_default.control)w=NULL;
    }
    void *root=text_pointer_frame(frame);
    if(!w)w=root?widget_for_frame(root):NULL;
    if(!w||!w->painted||!w->number_stepper.ready||!number_hit(w,event))return 0;
  }
  if(!w)return 0;
  void *node=w->node;uint64_t control=w->id;
  int owned_default=number_default.event==event&&number_default.node==node&&number_default.control==control;
  int allowed=*status!=1||owned_default;
  if(number_default.event==event)memset(&number_default,0,sizeof(number_default));
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  if(message==14)number_end(1,event);
  *result=original_post_event(self,context,event,frame,status,override);
  w=widget_for_node(node);
  if(w&&w->id==control&&message!=14&&allowed&&(owned_default||!(*((const uint8_t *)event+49)&2))&&number_mutable(node)) {
    if(message==15) {
      if(number_active_node)number_end(1,NULL);
      w=widget_for_node(node);
      if(w&&w->id==control&&number_mutable(node)&&number_pixels(w,number_request(w,1,0,0,0))) {
        struct NXSStepperBatch baseline;
        if(native_stepper_actions(&w->number_stepper,1,&baseline)>0) {
          struct PointI point=number_point(w,event);
          struct NXSResponse *response=number_request(w,2,point.x/60.,point.y/60.,widget_modifiers(event));
          if(response&&response->parts[0].y) {
            ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
            number_active_node=node;number_active_control=control;
            ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(node,1,NULL);
          }
        }
      }
    } else if(number_tracking(w)) {
      struct PointI point=number_point(w,event);
      number_request(w,3,point.x/60.,point.y/60.,widget_modifiers(event));number_apply(w);
    }
  }
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);return 1;
}
static void number_native_work(void)
{
  struct Widget *w=number_active_node?widget_for_node(number_active_node):NULL;
  if(w&&w->id==number_active_control)number_apply(w);
}
static void number_forget(struct Widget *w)
{
  if(!w->number_stepper.control)return;
  if(number_tracking(w)) {
    void *node=number_active_node;number_active_node=NULL;number_active_control=0;
    number_request(w,4,-10000,-10000,0);
    ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
  number_request(w,6,0,0,0);free(w->number_pixels);w->number_pixels=NULL;
  memset(&w->number_stepper,0,sizeof(w->number_stepper));
}
static void number_reset(void){number_active_node=NULL;number_active_control=0;memset(&number_default,0,sizeof(number_default));}
static int number_application_command(void *node,const char *selector,unsigned phase)
{
  int direction=native_stepper_command_direction(selector);
  if(!direction||!number_node(node))return -1;
  if(!number_mutable(node))return 0;
  if(phase==NXS_COMMAND_VALIDATE)return 1;
  ((void (*)(void *,int))(base+NXS_GECKO_NUMBER_STEP))(node,direction);
  if(number_node(node))((void (*)(void *))(base+NXS_GECKO_NUMBER_CHANGE))(node);
  return 1;
}

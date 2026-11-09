/* Shared canonical date model/action binding. Native NSDatePicker owns editing,
 * hit testing, formatting, calendar arithmetic and repeat. GPL-2.0-or-later. */
#include "ActionReceipts.inc"
struct NXSDateBinding {
  uint64_t control,cursor;
  uint32_t epoch;
  int ready,model_ready;
  NXSDateModel model;
};
static int native_date_model_same(const NXSDateModel *a,const NXSDateModel *b)
{
  return a->flags==b->flags&&a->elements==b->elements&&a->style==b->style&&a->value==b->value&&
    a->minimum==b->minimum&&a->maximum==b->maximum;
}
static int native_date_model_domain_same(const NXSDateModel *a,const NXSDateModel *b)
{
  const unsigned policy=NXS_DATE_UTC|NXS_DATE_ALLOW_EMPTY|NXS_DATE_TIME_OF_DAY;
  return a->elements==b->elements&&a->style==b->style&&(a->flags&policy)==(b->flags&policy);
}
static int native_date_binding_sync(struct NXSDateBinding *binding,const NXSDateModel *model,int tracking)
{
  if(binding->epoch!=atomic_load(&native_host_epoch)){binding->ready=0;binding->model_ready=0;}
  if(tracking)return binding->ready;
  if(!binding->model_ready||!native_date_model_same(&binding->model,model)) {
    if(!native_date_sync(binding->control,model))return 0;
    binding->model=*model;binding->model_ready=1;
  }
  if(!binding->ready) {
    struct NXSNativeActionBatch baseline;
    if(native_action_receipts(NXS_DATEPICKER,binding->control,&binding->epoch,&binding->cursor,&binding->ready,1,&baseline)<1)return 0;
  }
  return 1;
}
static int native_date_binding_actions(struct NXSDateBinding *binding,struct NXSNativeActionBatch *batch)
{
  int accepted=native_action_receipts(NXS_DATEPICKER,binding->control,&binding->epoch,&binding->cursor,&binding->ready,0,batch);
  if(accepted<1)return accepted;
  for(unsigned i=0;i<batch->count;i++) {
    const struct NXSActionReceipt *action=&batch->actions[i];
    if(action->event!=NXS_VALUE_CHANGED||(action->state!=0&&action->state!=-1)||
       (action->state==-1&&action->value!=0)){binding->ready=0;return -1;}
  }
  binding->cursor=batch->last;
  return 1;
}
static void native_date_binding_echo(struct NXSDateBinding *binding,const struct NXSActionReceipt *action)
{
  /* A native action already changed the control. Its canonical application
   * echo must not reset the native selected field or multi-digit edit state. */
  binding->model.value=action->value;
  if(action->state==-1)binding->model.flags|=NXS_DATE_EMPTY;
  else binding->model.flags&=~NXS_DATE_EMPTY;
}
static void native_date_binding_discard(struct NXSDateBinding *binding)
{
  /* A script replaced the model during a native callback. End native tracking
   * first, then retire queued actions from that model. The next sync writes the
   * application's replacement and subscribes with a fresh receipt baseline. */
  struct NXSControlActionsRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=63,
    .process=identity(),.kind=NXS_DATEPICKER,.control=binding->control,.subscribe=0};
  exchange_bytes(&request,sizeof(request));
  binding->ready=0;binding->cursor=0;binding->model_ready=0;
}

/* Native stepper target/actions to application commands. No numeric parser,
 * step/range policy, arrow hit geometry or repeat timer. GPL-2.0-or-later. */
#include <float.h>
#include "ActionReceipts.inc"
struct NXSStepperBinding {uint64_t control,cursor;double counter;uint32_t epoch;int ready;};
struct NXSStepperBatch {unsigned count;int directions[NXS_ACTION_BATCH_MAX];};
/* Applications connect native editor commands to their numeric domain. The
 * native key map chooses these selectors; no physical key bindings live here. */
static int native_stepper_command_direction(const char *selector)
{return !strcmp(selector,"moveUp:")?1:!strcmp(selector,"moveDown:")?-1:0;}
static struct NXSResponse *native_stepper_request(uint64_t control,unsigned operation,double width,double height,
    int enabled,double x,double y,unsigned modifiers)
{
  /* The native control displays arrows only. Its neutral integral counter
   * transports exact target/action direction; the application owns numbers,
   * constraints and decimal stepping through its original model methods. */
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_STEPPER,.control=control,.width=width,.height=height,
    .minimum=-DBL_MAX,.maximum=DBL_MAX,.enabled=enabled,.x=x,.y=y,.modifiers=modifiers};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(operation==1&&response&&response->parts[5].x!=1) {
    struct NXSControlStepRequest step={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=10,
      .process=identity(),.kind=NXS_STEPPER,.control=control,.step=1};
    response=exchange_bytes(&step,sizeof(step));
    if(!response||response->parts[5].x!=1)return NULL;
  }
  return response;
}
static int native_stepper_actions(struct NXSStepperBinding *binding,int begin,struct NXSStepperBatch *batch)
{
  batch->count=0;
  struct NXSNativeActionBatch native;
  int accepted=native_action_receipts(NXS_STEPPER,binding->control,&binding->epoch,&binding->cursor,&binding->ready,begin,&native);
  if(accepted<1)return accepted;
  if(begin){binding->counter=native.value;return 1;}
  double counter=binding->counter;
  for(unsigned i=0;i<native.count;i++) {
    const struct NXSActionReceipt *action=&native.actions[i];double direction=action->value-counter;
    if(action->event!=NXS_VALUE_CHANGED||(direction!=1&&direction!=-1))return -1;
    batch->directions[batch->count++]=direction>0?1:-1;counter=action->value;
  }
  binding->cursor=native.last;binding->counter=counter;return 1;
}

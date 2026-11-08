/* Native stepper target/actions to application commands. No numeric parser,
 * step/range policy, arrow hit geometry or repeat timer. GPL-2.0-or-later. */
#include <float.h>
#define NXS_ACTION_BATCH_MAX 256
struct NXSStepperBinding {uint64_t control,cursor;double counter;uint32_t epoch;int ready;};
struct NXSStepperBatch {unsigned count;int directions[NXS_ACTION_BATCH_MAX];};
/* Applications connect native editor commands to their numeric domain. The
 * native key map chooses these selectors; no physical key bindings live here. */
static int native_stepper_command_direction(const char *selector)
{return !strcmp(selector,"moveUp:")?1:!strcmp(selector,"moveDown:")?-1:0;}
_Static_assert(sizeof(struct NXSControlActionsRequest)==sizeof(struct NXSControlRequest),"Older-host compatible action envelope");
_Static_assert(sizeof(struct NXSActionSnapshot)==32&&sizeof(struct NXSActionReceipt)==24,"Action receipt ABI");
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
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(binding->epoch!=epoch){binding->epoch=epoch;binding->cursor=0;binding->counter=0;binding->ready=0;}
  if(!begin&&!binding->ready)return 0;
  struct NXSControlActionsRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=63,
    .process=identity(),.kind=NXS_STEPPER,.control=binding->control,.after=binding->cursor,.subscribe=1};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1||response->size<sizeof(*response)+sizeof(struct NXSActionSnapshot))return -1;
  struct NXSActionSnapshot snapshot;memcpy(&snapshot,response+1,sizeof(snapshot));
  if(snapshot.size!=sizeof(snapshot)||snapshot.count>NXS_ACTION_BATCH_MAX||snapshot.reserved||snapshot.flags&~3u||
     snapshot.flags&NXS_ACTION_LOST||response->size!=sizeof(*response)+sizeof(snapshot)+snapshot.count*sizeof(struct NXSActionReceipt))return -1;
  if(begin) {
    /* Begin only after draining a prior gesture and synchronizing the neutral
     * native model. Do not replay actions already committed to the app. */
    if(snapshot.count||!isfinite(response->parts[0].x))return -1;
    binding->cursor=snapshot.last;binding->counter=response->parts[0].x;binding->ready=1;return 1;
  }
  if(snapshot.flags&NXS_ACTION_BASELINE||snapshot.floor>binding->cursor||snapshot.last<binding->cursor)return -1;
  uint64_t cursor=binding->cursor;double counter=binding->counter;
  for(unsigned i=0;i<snapshot.count;i++) {
    struct NXSActionReceipt action;memcpy(&action,(char *)(response+1)+sizeof(snapshot)+i*sizeof(action),sizeof(action));
    double direction=action.value-counter;
    if(action.serial!=cursor+1||action.event!=NXS_VALUE_CHANGED||!isfinite(action.value)||(direction!=1&&direction!=-1))return -1;
    batch->directions[batch->count++]=direction>0?1:-1;cursor=action.serial;counter=action.value;
  }
  if(cursor!=snapshot.last)return -1;
  binding->cursor=cursor;binding->counter=counter;return 1;
}

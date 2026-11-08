/* Ordered native callback data shared by control bindings. No UI rules.
 * Include Protocol.h and Transport.inc first. GPL-2.0-or-later. */
#ifndef NXS_ACTION_RECEIPTS_INCLUDED
#define NXS_ACTION_RECEIPTS_INCLUDED
#define NXS_ACTION_BATCH_MAX 256
struct NXSNativeActionBatch {
  unsigned count;
  uint64_t last;
  double value;
  int state;
  struct NXSActionReceipt actions[NXS_ACTION_BATCH_MAX];
};
_Static_assert(sizeof(struct NXSControlActionsRequest)==sizeof(struct NXSControlRequest),"Older-host compatible action envelope");
_Static_assert(sizeof(struct NXSActionSnapshot)==32&&sizeof(struct NXSActionReceipt)==24,"Action receipt ABI");
static int native_action_receipts(unsigned kind,uint64_t control,uint32_t *epoch,uint64_t *cursor,int *ready,
    int begin,struct NXSNativeActionBatch *batch)
{
  batch->count=0;
  uint32_t current=atomic_load(&native_host_epoch);
  if(*epoch!=current){*epoch=current;*cursor=0;*ready=0;}
  if(!begin&&!*ready)return 0;
  struct NXSControlActionsRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=63,
    .process=identity(),.kind=kind,.control=control,.after=*cursor,.subscribe=1};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1||response->size<sizeof(*response)+sizeof(struct NXSActionSnapshot))return -1;
  struct NXSActionSnapshot snapshot;memcpy(&snapshot,response+1,sizeof(snapshot));
  if(snapshot.size!=sizeof(snapshot)||snapshot.count>NXS_ACTION_BATCH_MAX||snapshot.reserved||snapshot.flags&~3u||
     snapshot.flags&NXS_ACTION_LOST||response->size!=sizeof(*response)+sizeof(snapshot)+snapshot.count*sizeof(struct NXSActionReceipt))return -1;
  batch->value=response->parts[0].x;batch->state=response->parts[0].height;
  if(begin) {
    if(snapshot.count||!isfinite(batch->value))return -1;
    *cursor=snapshot.last;*ready=1;return 1;
  }
  if(snapshot.flags&NXS_ACTION_BASELINE||snapshot.floor>*cursor||snapshot.last<*cursor)return -1;
  uint64_t last=*cursor;
  for(unsigned i=0;i<snapshot.count;i++) {
    struct NXSActionReceipt *action=&batch->actions[i];
    memcpy(action,(char *)(response+1)+sizeof(snapshot)+i*sizeof(*action),sizeof(*action));
    if(action->serial!=last+1||!isfinite(action->value))return -1;
    last=action->serial;
  }
  if(last!=snapshot.last)return -1;
  /* The binding acknowledges only after validating its typed actions. */
  batch->last=last;batch->count=snapshot.count;return 1;
}
#endif

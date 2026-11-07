/* Original engine hit traversal plus native semantic row IDs. No UI hit rules.
 * The original array insertion retains root/ancestor ordering. */
#include "pinned-list-hits.h"
static uint32_t (*original_list_frames_for_area)(struct RelativeTo,const struct ViewportRect *,void *,const void *);
static __thread unsigned list_hit_depth;
static uint32_t list_frames_for_area(struct RelativeTo origin,const struct ViewportRect *rect,void *frames,const void *options)
{
  unsigned nested=list_hit_depth++;
  uint32_t result=original_list_frames_for_area(origin,rect,frames,options);
  if(nested||(result&0x80000000u)||origin.viewport>1||rect->width!=1||rect->height!=1)goto done;
  void *header=*(void **)frames;unsigned count=*(const uint32_t *)header;
  if(!count)goto done;
  uint64_t *seen=calloc(count,sizeof(*seen));if(!seen)goto done;unsigned used=0;
  for(unsigned i=0;i<*(const uint32_t *)*(void **)frames;i++) {
    header=*(void **)frames;void *owner=((void **)((char *)header+8))[i];
    struct GeckoList *list=list_find(owner);
    if(!list||!list->owned||!native_list_frame(owner))continue;
    uint64_t id=list->binding.control;int duplicate=0;
    for(unsigned j=0;j<used;j++)if(seen[j]==id)duplicate=1;
    if(duplicate)continue;seen[used++]=id;
    void *root=list->node;((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_ADDREF))(root);
    /* Gecko owns viewport, page-scroll and transform conversion. */
    struct PointI point={rect->x,rect->y};
    int transformed=((int (*)(struct RelativeTo,struct RelativeTo,struct PointI *))(base+NXS_GECKO_LIST_HIT_TRANSFORM_POINT))(origin,(struct RelativeTo){owner,0},&point)==0;
    int ready=prepare_list_image(owner);list=list_find_id(id);
    if(*(void **)((char *)root+96)!=owner) {
      /* Frame pointers are non-owning engine data. Drop the completed result
       * if an application callback retired its owner during metadata RPC. */
      *(uint32_t *)*(void **)frames=0;
      ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(root);break;
    }
    uint64_t item=0;
    int queried=transformed&&ready&&list&&list->frame==owner&&list->node==root&&
      native_control_item_at_point(NXS_LISTBOX,id,point.x/60.,point.y/60.,&item);
    list=list_find_id(id);
    if(*(void **)((char *)root+96)!=owner) {
      *(uint32_t *)*(void **)frames=0;
      ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(root);break;
    }
    if(queried&&item&&list&&list->frame==owner&&list->node==root&&list->owned) {
      void *node=NULL;
      for(unsigned j=0;j<list->model.packet->count;j++)if((uintptr_t)list->model.nodes[j]==item){node=list->model.nodes[j];break;}
      void *frame=node?*(void **)((char *)node+96):NULL;
      if(frame&&((void *(*)(void *,unsigned))(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET))(frame,3)==owner) {
        /* Use Gecko's own allocation/relocation; the inserted value is an
         * existing weak frame pointer, with the native root left after it. */
        ((void (*)(void *,size_t,size_t,size_t))(base+NXS_GECKO_LIST_HIT_ARRAY_INSERT))(frames,i,1,sizeof(void *));
        header=*(void **)frames;((void **)((char *)header+8))[i]=frame;i++;
      } else *(uint32_t *)*(void **)frames=0;
    }
    ((unsigned (*)(void *))(base+NXS_GECKO_POPUP_NODE_RELEASE))(root);
  }
  free(seen);
done:
  list_hit_depth--;return result;
}
static struct Detour list_hit_detours[]={
  {NXS_GECKO_LIST_HIT_FRAMES_FOR_AREA,gecko_list_hit_frames_for_area_bytes,list_frames_for_area,(void **)&original_list_frames_for_area}
};

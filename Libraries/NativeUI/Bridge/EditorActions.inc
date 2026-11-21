/* Fallbacks for GNUstep selectors that the browser key-command ABI cannot
 * represent. Keep edits with the browser's original editor. */
enum BrowserEditAction {
  BrowserCenter, BrowserKill, BrowserYank, BrowserTranspose, BrowserNewline, BrowserBackward
};

struct BrowserEditActions {
  enum BrowserEditAction actions[8];
  unsigned count;
};

static struct BrowserEditActions browser_editor_plan(const struct NXSResponse *response)
{
  static const char *const selectors[]={
    [BrowserCenter]="centerSelectionInVisibleArea:", [BrowserKill]="deleteToEndOfLine:",
    [BrowserYank]="yank:", [BrowserTranspose]="transpose:",
    [BrowserNewline]="insertNewlineIgnoringFieldEditor:", [BrowserBackward]="moveBackward:"
  };
  struct BrowserEditActions plan={0};
  if(!response||response->parts[3].x!=NXS_EDIT_COMMANDS||response->size<=sizeof(*response))
    return plan;
  const char *next=(const char *)(response+1),*end=(const char *)response+response->size;
  int extended=0;
  while(next<end&&plan.count<sizeof(plan.actions)/sizeof(*plan.actions)) {
    const char *terminator=memchr(next,0,end-next);
    if(!terminator)return (struct BrowserEditActions){0};
    unsigned action=0;
    while(action<sizeof(selectors)/sizeof(*selectors)&&strcmp(selectors[action],next))
      action++;
    if(action==sizeof(selectors)/sizeof(*selectors))return (struct BrowserEditActions){0};
    plan.actions[plan.count++]=action;
    extended|=action!=BrowserBackward;
    next=terminator+1;
  }
  if(next!=end||!extended)plan.count=0;
  return plan;
}

static struct BrowserEditActions browser_editor_actions(uint64_t editor,const NXSKeyEvent *event)
{
  return browser_editor_plan(native_edit_binding_request(editor,event));
}

/* Engine text models measure selection in UTF-16 units. The UTF-8 copies
 * below preserve complete code points and never export text to a clipboard. */
static const char *browser_text_offset(const char *text,uint32_t units)
{
  while(units&&*text) {
    unsigned width=(unsigned char)*text>=0xf0?2:1;
    if(units<width)return NULL;
    units-=width;
    do text++; while(((unsigned char)*text&0xc0)==0x80);
  }
  return units?NULL:text;
}

static void browser_remember_kill(char **kill,const char *before,const char *after,uint32_t start)
{
  const char *prefix=browser_text_offset(before,start);
  if(!prefix)return;
  size_t position=prefix-before,old_size=strlen(before),new_size=strlen(after);
  if(new_size>=old_size||position>new_size||memcmp(before,after,position)||
     strcmp(prefix+old_size-new_size,after+position))return;
  char *removed=strndup(prefix,old_size-new_size);
  if(removed){free(*kill);*kill=removed;}
}

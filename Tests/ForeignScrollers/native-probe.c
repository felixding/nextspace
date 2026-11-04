/* Exercise the bridge without reimplementing control drawing/tracking. GPL-2.0-or-later. */
#include "NativeScroller.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static NXSScroller *control;
static double value = 300;
static int counter;
static double move_x, move_y;
static unsigned held_modifiers;
static const char *capture_path;
static void save_bitmap(const char *path) {
  NXSBitmap bitmap=nxs_scroller_draw(control,1);FILE *file=fopen(path,"wb");assert(file);
  size_t written=fwrite(bitmap.pixels,bitmap.stride,bitmap.height,file);assert(written==(size_t)bitmap.height);fclose(file);
}
static void changed(void *unused, double next) { value = next; }
static void pump(void *unused) {
  if(capture_path) {save_bitmap(capture_path);nxs_scroller_send(control,NXS_RELEASE,move_x,move_y,0);return;}
  if (counter++ == 0) nxs_scroller_send(control, NXS_MOVE, move_x, move_y, held_modifiers);
  else nxs_scroller_send(control, NXS_RELEASE, move_x, move_y, held_modifiers);
}
int main(int argc, char **argv) {
  control = nxs_scroller_create(0, changed, pump, NULL);
  assert(control);
  int render = argc > 7 && !strcmp(argv[1],"--render");
  nxs_scroller_sync(control, render ? atof(argv[2]) : 240, 0, render ? atof(argv[3]) : 1000,
    render ? atof(argv[4]) : 200, 10, 180, render ? atof(argv[5]) : value, 1);
  NXSRect knob = nxs_scroller_part(control, 2);
  if(argc>2 && !strcmp(argv[1],"--pressed")) {
    capture_path=argv[2];NXSRect arrow=nxs_scroller_part(control,5);
    move_x=arrow.x+arrow.width/2;move_y=arrow.y+arrow.height/2;
    nxs_scroller_track(control,move_x,move_y,0);
    char path[1024];snprintf(path,sizeof(path),"%s.normal",capture_path);save_bitmap(path);
    printf("{\"width\":18,\"height\":240}\n");
  } else if (argc > 1 && strcmp(argv[1], "--track") == 0) {
    move_x = knob.x + knob.width/2; move_y = knob.y + knob.height/2 + 50;
    nxs_scroller_track(control, knob.x+knob.width/2, knob.y+knob.height/2, 0);
    assert(value > 300 && value < 800);
    double plain=value;
    counter=0;value=300;held_modifiers=NXS_SUPER;
    nxs_scroller_sync(control,240,0,1000,200,10,180,value,1);
    knob=nxs_scroller_part(control,2);
    move_x=knob.x+knob.width/2;move_y=knob.y+knob.height/2+50;
    nxs_scroller_track(control,knob.x+knob.width/2,knob.y+knob.height/2,held_modifiers);
    double slow=value;
    assert(slow>300 && slow-300<(plain-300)*.3);
    counter=0;value=300;
    nxs_scroller_sync(control,240,0,1000,200,10,180,value,1);
    NXSRect arrow=nxs_scroller_part(control,5);
    move_x=arrow.x+arrow.width/2;move_y=arrow.y+arrow.height/2;
    nxs_scroller_track(control,move_x,move_y,held_modifiers);
    assert(value==480);
    printf("{\"tracked_value\":%g,\"slow_value\":%g,\"alternate_arrow_value\":%g}\n",plain,slow,value);
  } else {
    NXSBitmap bitmap = nxs_scroller_draw(control, render ? atof(argv[6]) : argc > 2 ? atof(argv[2]) : 1);
    assert(bitmap.pixels && bitmap.width > 0 && bitmap.height > 0);
    FILE *file = fopen(render ? argv[7] : argc > 1 ? argv[1] : "/tmp/native-scroller.argb", "wb");
    assert(file);size_t written=fwrite(bitmap.pixels, bitmap.stride, bitmap.height, file);
    assert(written == (size_t)bitmap.height);fclose(file);
    printf("{\"width\":%d,\"height\":%d,\"knob\":[%g,%g,%g,%g]}\n",
      bitmap.width, bitmap.height, knob.x, knob.y, knob.width, knob.height);
  }
  nxs_scroller_destroy(control);
  return 0;
}

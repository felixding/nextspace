/* Transport the source group's row/column arrangement as model data. Native
 * NSMatrix still performs directional navigation and skips disabled cells.
 * Row membership is geometric overlap, independent of pixels or display scale. */
static unsigned native_radio_columns(const struct NXSRectD *bounds,unsigned count)
{
  if(!count)return 1;
  double top=bounds[0].y,bottom=top+bounds[0].height;
  unsigned columns=1;
  for(unsigned i=1;i<count;i++) {
    top=fmax(top,bounds[i].y);bottom=fmin(bottom,bounds[i].y+bounds[i].height);
    if(!(bottom>top))break;
    columns++;
  }
  return columns;
}

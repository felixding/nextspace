/* Application-specific exceptions to the default Qt Widgets adapter.
 * GPL-2.0-or-later. */
static bool kdeRetainsOriginalControl(const QWidget *widget)
{
  // KTextEditor paints its document minimap and annotations in this scrollbar.
  // Keep the custom control until its model has a separate native presentation.
  return widget->inherits("KateScrollBar");
}

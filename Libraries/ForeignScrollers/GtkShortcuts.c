/* Bind Command shortcuts to the application's own GActions. GPL-2.0-or-later. */
#include <gtk/gtk.h>
#include "../NativeUI/NativeUI.h"

#if GTK_MAJOR_VERSION == 3
#define GDK_ALT_MASK GDK_MOD1_MASK
#endif

void nextspace_gtk_set_accels(GtkApplication *app, const char *action, const char *const *accels,
                              void (*set)(GtkApplication *, const char *, const char *const *))
{
  const char *policy = g_getenv("NEXTSPACE_SHORTCUTS");
  if (!action || !accels || !accels[0] || (policy && !g_str_equal(policy, "native"))) {
    set(app, action, accels);
    return;
  }
  guint key = 0;
  GdkModifierType modifiers = 0;
  gtk_accelerator_parse(accels[0], &key, &modifiers);
  key = gdk_keyval_to_lower(key);
  GdkModifierType command = 0;
  if (key && (modifiers == GDK_CONTROL_MASK || modifiers == (GDK_CONTROL_MASK | GDK_SHIFT_MASK))) {
    switch (nxs_physical_modifier(NXS_MENU_COMMAND)) {
      case NXS_ALT: command = GDK_ALT_MASK; break;
      case NXS_CONTROL: command = GDK_CONTROL_MASK; break;
      case NXS_SUPER: command = GDK_SUPER_MASK; break;
    }
  }
  if (!command) {
    set(app, action, accels);
    return;
  }
  GdkModifierType effective = command | (modifiers & GDK_SHIFT_MASK);
  g_autofree char *binding = gtk_accelerator_name(key, effective);
  g_auto(GStrv) owners = gtk_application_get_actions_for_accel(app, binding);
  if (owners && owners[0] && !g_str_equal(owners[0], action)) {
    set(app, action, accels);
    return;
  }
  GPtrArray *bindings = g_ptr_array_new();
  g_ptr_array_add(bindings, binding);
  for (size_t index = 0; accels[index]; index++) {
    guint original_key = 0;
    GdkModifierType original_mods = 0;
    gtk_accelerator_parse(accels[index], &original_key, &original_mods);
    if (gdk_keyval_to_lower(original_key) != key || original_mods != effective)
      g_ptr_array_add(bindings, (gpointer)accels[index]);
  }
  g_ptr_array_add(bindings, NULL);
  set(app, action, (const char *const *)bindings->pdata);
  g_ptr_array_unref(bindings);
}

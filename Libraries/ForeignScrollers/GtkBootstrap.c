/* Load GTK integration only in a process that actually initializes GTK.
 * No GTK or AppKit dependency is injected into other session processes.
 * GPL-2.0-or-later. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static void *symbol(const char *library,const char *name)
{
  void *value=dlsym(RTLD_NEXT,name);
  if(value) return value;
  /* PyGObject loads its dependencies RTLD_LOCAL; RTLD_NEXT alone cannot see
   * that scope. NOLOAD finds the existing object without injecting a library. */
  void *handle=dlopen(library,RTLD_NOW|RTLD_NOLOAD);
  if(handle) {value=dlsym(handle,name);dlclose(handle);}
  return value;
}
static unsigned gtk_major(void)
{
  unsigned (*major)(void)=symbol("libgtk-4.so.1","gtk_get_major_version");
  if(!major) major=symbol("libgtk-3.so.0","gtk_get_major_version");
  return major ? major() : 0;
}
static void install(void)
{
  static int installed;
  unsigned major=gtk_major();
  const char *disabled = getenv("NEXTSPACE_SCROLLBARS");
  if (installed || (major != 3 && major != 4) || (disabled && strcmp(disabled, "off") == 0)) return;
  Dl_info info;
  if (!dladdr((void *)install, &info)) return;
  char path[PATH_MAX];
  if (snprintf(path, sizeof(path), "%s", info.dli_fname) >= (int)sizeof(path)) return;
  char *slash = strrchr(path, '/'); if (!slash) return; *slash = '\0';
  size_t length = strlen(path);
  if (snprintf(path + length, sizeof(path) - length, "/libnextspace-gtk%u-scrollbars.so",major) >= (int)(sizeof(path) - length)) return;
  void *module = dlopen(path, RTLD_NOW | RTLD_LOCAL);
  void (*initialize)(void) = module ? dlsym(module,major==4?"nextspace_gtk4_scrollbars_init":"nextspace_gtk3_scrollbars_init") : NULL;
  if (initialize) { installed = 1; initialize(); }
}
static int install_idle(void *unused) { install();return 0; }

/* GI programs load GTK after process startup and may call gtk_init through a
 * library-local function pointer. GTK's public GObject registration boundary
 * still lets us schedule installation on the main context after construction. */
uintptr_t g_type_register_static_simple(uintptr_t parent,const char *name,unsigned class_size,
    void (*class_init)(void *,void *),unsigned instance_size,void (*instance_init)(void *,void *),unsigned flags)
{
  uintptr_t (*next)(uintptr_t,const char *,unsigned,void (*)(void *,void *),unsigned,void (*)(void *,void *),unsigned)
    =symbol("libgobject-2.0.so.0","g_type_register_static_simple");
  uintptr_t type=next(parent,name,class_size,class_init,instance_size,instance_init,flags);
  if(!strcmp(name,"GtkScrolledWindow")) {
    unsigned (*idle)(int,int (*)(void *),void *,void (*)(void *))=symbol("libglib-2.0.so.0","g_idle_add_full");
    if(idle) idle(0,install_idle,NULL,NULL);
  }
  return type;
}
/* GTK3 accepts arguments, GTK4 does not. Dispatch according to the loaded ABI. */
void gtk_init(int *argc, char ***argv)
{
  unsigned major=gtk_major();
  if (!major) return;
  if (major == 4) { void (*next)(void) = symbol("libgtk-4.so.1", "gtk_init"); next(); }
  else { void (*next)(int *, char ***) = symbol("libgtk-3.so.0", "gtk_init"); next(argc, argv); }
  install();
}
int gtk_init_check(int *argc, char ***argv)
{
  unsigned major=gtk_major();
  if (!major) return 0;
  int success;
  if (major == 4) { int (*next)(void) = symbol("libgtk-4.so.1", "gtk_init_check"); success = next(); }
  else { int (*next)(int *, char ***) = symbol("libgtk-3.so.0", "gtk_init_check"); success = next(argc, argv); }
  if (success) install();
  return success;
}
int g_application_run(void *application, int argc, char **argv)
{
  /* GtkApplication initializes GTK internally; install the map hook before its
   * activation handler constructs widgets, including GtkBuilder-created ones. */
  install();
  int (*next)(void *, int, char **) = symbol("libgio-2.0.so.0", "g_application_run");
  return next(application, argc, argv);
}

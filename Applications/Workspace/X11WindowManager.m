/* Copyright (C) 2014-2021 Sergii Stoian; 2026 NEXTSPACE contributors.
   X11 policy extracted from Controller.m. SPDX-License-Identifier: GPL-2.0-or-later */
#import "WindowManager.h"
#import "Workspace+WM.h"
#import "Recycler.h"
#import "X11RecyclerIcon.h"
#import "WMNotificationCenter.h"
#import "Processes/ProcessManager+WindowManager.h"
#import <AppKit/NSWindow.h>
#import <GNUstepGUI/GSDisplayServer.h>
#import <SystemKit/OSEKeyboard.h>
#import <SystemKit/OSESessionSettings.h>
#include <core/string_utils.h>
#include <core/wuserdefaults.h>
#include <WM/desktop.h>
#include <unistd.h>
#include <signal.h>
#include <limits.h>

static NSString *desktopPreferencesPath(void)
{
  CFStringRef path = WMUserDefaultsCopyStringForDomain(CFSTR("WM.plist"));
  char bytes[PATH_MAX];
  NSString *value = path && CFStringGetCString(path, bytes, sizeof(bytes), kCFStringEncodingUTF8) ?
    [NSString stringWithUTF8String:bytes] : nil;
  if (path) CFRelease(path);
  return value;
}

@interface WSX11WindowManager : NSObject <WSWindowManager, OSESessionSettings>
@end

static WWindow *windowForNSWindow(NSWindow *window)
{
  if (!window) return NULL;
  return wWindowFor((Window)[GSCurrentServer() windowDevice:[window windowNumber]]);
}

@implementation WSX11WindowManager
- (void)prepareForTermination {}
- (bycopy NSData *)nextspaceSettingsRequest:(bycopy NSData *)bytes
{
  NSDictionary *request = OSESessionSettingsDecode(bytes);
  if ([[request objectForKey:@"schema"] integerValue] != 1 ||
      ![[request objectForKey:@"action"] isEqual:@"desktop-settings"]) return nil;
  NSDictionary *result = [self desktopSettings:request];
  return result ? OSESessionSettingsEncode(result) : nil;
}
- (NSDictionary *)desktopSettings:(NSDictionary *)changes
{
  WScreen *screen = wDefaultScreen();
  if (!screen) return nil;
  NSString *path = desktopPreferencesPath();
  if (!path) return nil;
  NSDictionary *requested = [changes objectForKey:@"shortcuts"];
  if (requested) {
    if (![requested isKindOfClass:[NSDictionary class]]) return nil;
    for (id key in requested)
      if (![WSDesktopShortcutNames() containsObject:key] || ![[requested objectForKey:key] isKindOfClass:[NSString class]] ||
          [[requested objectForKey:key] length] > 128) return nil;
  }
  NSArray *names = [changes objectForKey:@"names"];
  if (names) {
    if (![names isKindOfClass:[NSArray class]] || ![names count] || [names count] > 10) return nil;
    for (id name in names)
      if (![name isKindOfClass:[NSString class]] || ![name length] || [name length] > 128) return nil;
    /* Reject the complete shrink before deleting any empty trailing desktops. */
    for (NSUInteger index = [names count]; index < screen->desktop_count; index++)
      if (!wDesktopCanDelete(screen, (int)index)) return nil;
    while (screen->desktop_count > [names count])
      if (!wDesktopDelete(screen, screen->desktop_count - 1)) return nil;
    if (screen->desktop_count < [names count]) wDesktopMake(screen, [names count] - screen->desktop_count);
    NSUInteger index;
    for (index = 0; index < [names count]; index++)
      wDesktopRename(screen, index, [[names objectAtIndex:index] UTF8String]);
    wDesktopSaveState(screen);
    WMUserDefaultsWrite(screen->session_state, CFSTR("WMState"));
  }
  NSMutableDictionary *defaults = [[[NSDictionary dictionaryWithContentsOfFile:path] mutableCopy] autorelease];
  if (!defaults) defaults = [NSMutableDictionary dictionary];
  if (requested) {
    [defaults addEntriesFromDictionary:requested];
    if (![defaults writeToFile:path atomically:YES]) return nil;
    [[WMNotificationCenter defaultCenter] postNotificationName:@"WMDidChangeAppearanceSettingsNotification"
      object:@"GSWorkspaceNotification" userInfo:nil];
  }
  NSMutableDictionary *shortcuts = [[WSDefaultDesktopShortcuts() mutableCopy] autorelease];
  for (NSString *key in WSDesktopShortcutNames()) {
    id value = [defaults objectForKey:key];
    if (!value && [key hasPrefix:@"Desktop"])
      value = [defaults objectForKey:[key stringByReplacingOccurrencesOfString:@"Desktop" withString:@"Workspace"]];
    if ([value isKindOfClass:[NSString class]]) [shortcuts setObject:value forKey:key];
  }
  NSMutableArray *current = [NSMutableArray array];
  int index;
  for (index = 0; index < screen->desktop_count; index++)
    [current addObject:[NSString stringWithUTF8String:screen->desktops[index]->name]];
  return [NSDictionary dictionaryWithObjectsAndKeys:current, @"names", shortcuts, @"shortcuts",
    [NSNumber numberWithInt:screen->current_desktop], @"current", nil];
}
- (BOOL)terminateApplication:(NSDictionary *)info
{
  /* Legacy ProcessManager uses its existing GNUstep/X11 termination paths. */
  return NO;
}
- (NSString *)keyboardLayoutBadgeForNotification:(NSNotification *)notification
{
  OSEKeyboard *keyboard = [[OSEKeyboard new] autorelease];
  NSArray *layouts = [keyboard layouts];
  NSInteger group = [[[notification userInfo] objectForKey:@"XkbGroup"] integerValue];
  return [layouts count] > 1 && group >= 0 && group < [layouts count] ? [layouts objectAtIndex:group] : @"";
}
- (void)unhideWorkspace { wUnhideApplication(wApplicationWithName(NULL, "Workspace"), NO, NO); }
- (void)hideOtherApplications
{
  Window window = (Window)[GSCurrentServer() windowDevice:[[NSApp keyWindow] windowNumber]];
  NSDictionary *info = @{@"WindowID" : [NSNumber numberWithUnsignedLong:window],
                          @"ApplicationName" : @"Workspace"};
  [[NSDistributedNotificationCenter defaultCenter]
    postNotificationName:CF_NOTIFICATION(WMShouldHideOthersNotification)
    object:WSSessionServiceName(@"GSWorkspaceNotification") userInfo:info];
}
- (void)beginApplicationLaunch:(NSDictionary *)info fromPoint:(NSPoint)point
{
  wLaunchingAppIconCreate([info[@"WMName"] cString], [info[@"WMClass"] cString],
    [info[@"LaunchPath"] cString], point.x, point.y, [info[@"IconPath"] cString]);
}
- (void)endApplicationLaunch:(NSString *)command
{
  WAppIcon *icon = wLaunchingAppIconForCommand(wDefaultScreen(), (char *)[command cString]);
  if (icon) wLaunchingAppIconDestroy(wDefaultScreen(), icon);
}
- (void)observeApplicationEventsFor:(ProcessManager *)manager
{
  NSNotificationCenter *center = [self notificationCenter];
  [center addObserver:manager selector:@selector(windowManagerDidCreateApplication:)
    name:CF_NOTIFICATION(WMDidCreateApplicationNotification) object:nil];
  [center addObserver:manager selector:@selector(windowManagerDidDestroyApplication:)
    name:CF_NOTIFICATION(WMDidDestroyApplicationNotification) object:nil];
  [center addObserver:manager selector:@selector(windowManagerDidActivateApplication:)
    name:CF_NOTIFICATION(WMDidActivateApplicationNotification) object:nil];
  [center addObserver:manager selector:@selector(windowManagerDidManageWindow:)
    name:CF_NOTIFICATION(WMDidManageWindowNotification) object:nil];
  [center addObserver:manager selector:@selector(windowManagerDidUnmanageWindow:)
    name:CF_NOTIFICATION(WMDidUnmanageWindowNotification) object:nil];
}
- (NSInteger)dockLevel { return wDockLevel(wDefaultScreen()->dock); }
- (NSArray *)supportedDockLevels { return @[@0, @5, @(-1000)]; }
- (void)setDockLevel:(NSInteger)level { wDockSetLevel(wDefaultScreen()->dock, level); }
- (NSInteger)dockSlotCount
{ return wDefaultScreen()->dock ? wDefaultScreen()->dock->max_icons : 0; }
- (NSDictionary *)dockApplicationAtSlot:(NSInteger)slot
{
  WDock *dock = wDefaultScreen()->dock;
  if (!dock || slot < 0 || slot >= dock->max_icons) return nil;
  WAppIcon *icon = wDockAppiconAtSlot(dock, slot);
  if (!icon) return nil;
  return @{ @"Name": [NSString stringWithFormat:@"%s.%s", icon->wm_instance, icon->wm_class],
    @"Command": icon->command ? [NSString stringWithUTF8String:icon->command] : @"",
    @"PasteCommand": icon->paste_command ? [NSString stringWithUTF8String:icon->paste_command] : @"",
    @"DropCommand": icon->dnd_command ? [NSString stringWithUTF8String:icon->dnd_command] : @"",
    @"AutoLaunch": icon->flags.auto_launch ? @"Yes" : @"No",
    @"Lock": icon->flags.lock ? @"Yes" : @"No" };
}
- (void)setDockValue:(NSString *)value forKey:(NSString *)key atSlot:(NSInteger)slot
{
  if (slot < 0 || slot >= [self dockSlotCount]) return;
  WAppIcon *icon = wDockAppiconAtSlot(wDefaultScreen()->dock, slot);
  if (!icon) return;
  if ([key isEqualToString:@"AutoLaunch"]) icon->flags.auto_launch = [value boolValue];
  else if ([key isEqualToString:@"Lock"]) icon->flags.lock = [value boolValue];
  else {
    char **field = [key isEqualToString:@"Command"] ? &icon->command :
      [key isEqualToString:@"PasteCommand"] ? &icon->paste_command :
      [key isEqualToString:@"DropCommand"] ? &icon->dnd_command : NULL;
    if (!field) return;
    wfree(*field); *field = wstrdup([value UTF8String]);
  }
  wScreenSaveState(wDefaultScreen());
}
- (NSString *)dockChangeNotification { return CF_NOTIFICATION(WMDidChangeDockContentNotification); }
- (NSImage *)dockImageAtSlot:(NSInteger)position
{
  if (position < 0 || position >= [self dockSlotCount]) return nil;
  WAppIcon *btn = wDockAppiconAtSlot(wDefaultScreen()->dock, position);
  NSString *iconPath;
  NSString *appName;
  NSDictionary *appDesc;
  NSImage *icon = nil;

  if (btn) {
    // NSDebugLLog(@"Preferences", @"W+W: icon image file: %s", btn->icon->file);
    if (btn->icon->file) {  // Docked and not running application
      iconPath = [NSString stringWithCString:btn->icon->file];
      icon = [[NSImage alloc] initWithContentsOfFile:iconPath];
      [icon autorelease];
    } else {
      if (!strcmp(btn->wm_class, "GNUstep")) {
        appName = [NSString stringWithCString:btn->wm_instance];
      } else {
        appName = [NSString stringWithCString:btn->wm_class];
      }

      appDesc = [[ProcessManager shared] _applicationWithName:appName];

      if (!strcmp(btn->wm_class, "GNUstep")) {
        icon = [[NSApp delegate] iconForFile:[appDesc objectForKey:@"NSApplicationPath"]];
      } else {
        icon = [appDesc objectForKey:@"NSApplicationIcon"];
      }
    }
    if (!icon) {
      icon = [NSImage imageNamed:@"NXUnknownApplication"];
    }
  }

  return icon;
}
- (void)setDockImageAtPath:(NSString *)path atSlot:(NSInteger)position
{
  WAppIcon *btn;
  RImage *rimage;

  if (position < 0 || position >= [self dockSlotCount] || ![path length]) return;
  btn = wDockAppiconAtSlot(wDefaultScreen()->dock, position);
  if (!btn) {
    return;
  }

  if (btn->icon->file) {
    wfree(btn->icon->file);
  }
  btn->icon->file = wstrdup([path cString]);

  rimage = WSCreateRasterImage(btn->icon->file, wDefaultScreen());
  if (!rimage) {
    return;
  }

  if (btn->icon->file_image) {
    RReleaseImage(btn->icon->file_image);
    btn->icon->file_image = NULL;
  }
  btn->icon->file_image = RRetainImage(rimage);

  // Write to WM's 'WMWindowAttributes' file
  if (YES) {
    CFMutableDictionaryRef winAttrs, appAttrs;
    CFStringRef appKey, iconFile;

    winAttrs = w_global.domain.window_attrs->dictionary;

    appKey = CFStringCreateWithFormat(kCFAllocatorDefault, 0, CFSTR("%s.%s"), btn->wm_instance,
                                      btn->wm_class);
    CFDictionaryRef existing = CFDictionaryGetValue(winAttrs, appKey);
    appAttrs = existing ? CFDictionaryCreateMutableCopy(kCFAllocatorDefault, 0, existing) : NULL;
    if (!appAttrs) {
      appAttrs = CFDictionaryCreateMutable(kCFAllocatorDefault, 1, &kCFTypeDictionaryKeyCallBacks,
                                           &kCFTypeDictionaryValueCallBacks);
    }
    iconFile =
        CFStringCreateWithCString(kCFAllocatorDefault, btn->icon->file, kCFStringEncodingUTF8);
    CFDictionarySetValue(appAttrs, CFSTR("Icon"), iconFile);
    CFRelease(iconFile);
    CFDictionarySetValue(appAttrs, CFSTR("AlwaysUserIcon"), CFSTR("YES"));

    if (position == 0) {
      CFDictionarySetValue(winAttrs, CFSTR("Logo.WMDock"), appAttrs);
      CFDictionarySetValue(winAttrs, CFSTR("Logo.WMPanel"), appAttrs);
    }

    CFDictionarySetValue(winAttrs, appKey, appAttrs);
    CFRelease(appKey);
    CFRelease(appAttrs);
    WMUserDefaultsWrite(winAttrs, CFSTR("WMWindowAttributes"));
  }

  wIconUpdate(btn->icon);
}

- (BOOL)isDockVisible { return wDefaultScreen()->dock->mapped; }
- (void)setDockVisible:(BOOL)visible
{
  if (visible) wDockShowIcons(wDefaultScreen()->dock);
  else wDockHideIcons(wDefaultScreen()->dock);
}
- (BOOL)isDockCollapsed { return wDefaultScreen()->dock->collapsed; }
- (void)setDockCollapsed:(BOOL)collapsed
{
  if (collapsed) wDockCollapse(wDefaultScreen()->dock);
  else wDockUncollapse(wDefaultScreen()->dock);
}
- (BOOL)isIconYardVisible { return wDefaultScreen()->flags.icon_yard_mapped; }
- (void)setIconYardVisible:(BOOL)visible
{
  if (visible) wIconYardShowIcons(wDefaultScreen());
  else wIconYardHideIcons(wDefaultScreen());
}
- (void)updateUsableArea { wScreenUpdateUsableArea(wDefaultScreen()); }
- (NSInteger)desktopIndex { return wDefaultScreen()->current_desktop; }
- (BOOL)shouldRestoreWorkspaceWindows
{
  WAppIcon *icon = wDockAppiconAtSlot(wDefaultScreen()->dock, 0);
  return icon && icon->flags.auto_launch == 1;
}
- (NSWindow *)newRecyclerIconForRecycler:(Recycler *)recycler
{
  WDock *dock = wDefaultScreen()->dock;
  if (!dock || !dock->icon_array[0]) return nil;
  WAppIcon *icon = [RecyclerIcon recyclerAppIconForDock:dock];
  if (!icon) return nil;
  XClassHint classhint = {.res_name = "Recycler", .res_class = "GNUstep"};
  XSetClassHint(dpy, icon->icon->core->window, &classhint);
  icon->icon->owner = dock->icon_array[0]->icon->owner;
  icon->main_window = dock->icon_array[0]->main_window;
  return [[RecyclerIcon alloc] initWithWindowRef:&icon->icon->core->window recycler:recycler];
}
- (void)finishStartup
{
  wDockDoAutoLaunch(wDefaultScreen()->dock, 0);
  wDefaultScreen()->flags.startup2 = 0;
}
- (void)setFocusEventsEnabled:(BOOL)enabled { wDefaultScreen()->flags.ignore_focus_events = !enabled; }
- (void)updateScreenParameters { WSUpdateScreenParameters(); }
- (NSNotificationCenter *)notificationCenter { return [WMNotificationCenter defaultCenter]; }
- (NSString *)desktopChangeNotification { return CF_NOTIFICATION(WMDidChangeDesktopNotification); }
- (NSString *)keyboardLayoutChangeNotification { return CF_NOTIFICATION(WMDidChangeKeyboardLayoutNotification); }

- (NSString *)serverVersion
{
  Display *display = [GSCurrentServer() serverDevice];
  int release = VendorRelease(display);
  return [NSString stringWithFormat:@"%s %d.%d.%d", ServerVendor(display), release / 10000000,
    (release / 100000) % 100, (release / 1000) % 100];
}

- (void)setWindow:(NSWindow *)window shaded:(BOOL)shaded
{
  WWindow *managed = windowForNSWindow(window);
  if (!managed) return;
  if (shaded) wShadeWindow(managed);
  else wUnshadeWindow(managed);
}

- (NSString *)stateForWindow:(NSWindow *)nsWindow
{
  WWindow *wWin = windowForNSWindow(nsWindow);

  if (!wWin)
    return nil;

  if (wWin->flags.miniaturized) {
    return @"Miniaturized";
  } else if (wWin->flags.shaded) {
    return @"Shaded";
  } else if (wWin->flags.hidden) {
    return @"Hidden";
  } else {
    return @"Normal";
  }
}

- (NSArray *)undockedApplications
{
  NSMutableArray *appList = [[NSMutableArray alloc] init];
  NSString *appName;
  NSString *appCommand;
  WAppIcon *appIcon;
  char *command = NULL;

  appIcon = wDefaultScreen()->app_icon_list;
  while (appIcon->next) {
    if (!strcmp(appIcon->wm_class, "GNUstep") && !strcmp(appIcon->wm_instance, "Login")) {
      appIcon = appIcon->next;
      continue;
    }
    if (!appIcon->flags.docked) {
      if (appIcon->command && appIcon->command != NULL) {
        command = wstrdup(appIcon->command);
      }
      if (command == NULL && appIcon->icon->owner != NULL) {
        command = wGetCommandForWindow(appIcon->icon->owner->client_win);
      }
      if (command != NULL) {
        appName =
            [[NSString alloc] initWithFormat:@"%s.%s", appIcon->wm_instance, appIcon->wm_class];
        appCommand = [[NSString alloc] initWithCString:command];
        [appList addObject:@{@"Name" : appName, @"Command" : appCommand}];
        [appName release];
        [appCommand release];
        wfree(command);
        command = NULL;
      } else {
        NSLog(@"Application `%s.%s` was not saved. No application command found.",
              appIcon->wm_instance, appIcon->wm_class);
      }
    }
    appIcon = appIcon->next;
  }

  return [appList autorelease];
}

- (BOOL)isApplicationRunning:(NSString *)appName
{
  NSArray *nameComps = [appName componentsSeparatedByString:@"."];
  char *app_instance = (char *)[[nameComps objectAtIndex:0] cString];
  char *app_class = (char *)[[nameComps objectAtIndex:1] cString];
  BOOL isAppFound = NO;
  WAppIcon *appIcon;

  appIcon = wDefaultScreen()->app_icon_list;
  while (appIcon->next) {
    if (!strcmp(app_instance, appIcon->wm_instance) && !strcmp(app_class, appIcon->wm_class)) {
      isAppFound = YES;
      break;
    }
    appIcon = appIcon->next;
  }

  return isAppFound;
}

- (pid_t)executeCommand:(NSString *)command
{
  pid_t pid;
  char **argv;
  int argc;

  wtokensplit((char *)[command cString], &argv, &argc);

  if (!argc) {
    return 0;
  }

  pid = fork();
  if (pid == 0) {
    char **args;
    int i;

    args = malloc(sizeof(char *) * (argc + 1));
    if (!args)
      exit(111);
    for (i = 0; i < argc; i++) {
      args[i] = argv[i];
    }

    sigset_t sigs;
    sigfillset(&sigs);
    sigprocmask(SIG_UNBLOCK, &sigs, NULL);

    args[argc] = NULL;
    execvp(argv[0], args);
    exit(111);
  }
  while (argc > 0) {
    wfree(argv[--argc]);
  }
  wfree(argv);

  return pid;
}

@end

Class WSX11WindowManagerClass(void) { return [WSX11WindowManager class]; }

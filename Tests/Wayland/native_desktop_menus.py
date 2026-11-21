"""Original persistent application-menu lifetime on the English preview."""
import argparse
import json
from pathlib import Path
import time

from desktop_input import Desktop

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--browser-platform',action='store_true')
a=p.parse_args();desktop=Desktop(a.root);rows=[];outside_targets=[]
report=a.root/'ordinary-menu-ux.json'
def save(complete=False,**extra):
    report.write_text(json.dumps(dict(complete=complete,checks=rows,outside_targets=outside_targets,**extra),indent=2)+'\n')
def until(read,predicate,label):
    end=time.monotonic()+12
    while True:
        value=read()
        if predicate(value):return value
        assert time.monotonic()<end,(label,value)
        time.sleep(.05)
def check(case,passed):
    rows.append(dict(case=case,passed=bool(passed)));save();assert passed,case
def menus():
    return [w for w in desktop.command('windows') if w['visible'] and w['level']==20]
def outside(main):
    # Use the visible document intersection. A fixture can put Firefox at the
    # left edge or Chromium partly offscreen; a fixed offset can hit Save As.
    head=desktop.command('outputs')[0]
    left=max(main['x']+24,head['work_x']+24)
    right=min(main['x']+main['width']-24,head['work_x']+head['work_width']-24)
    y=max(head['work_y']+24,min(main['y']+160,head['work_y']+head['work_height']-24))
    blockers=menus()+desktop.command('popups')
    def covered(x):
        return any(w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height'] for w in blockers)
    x=next(x for x in (right,(left+right)/2,left) if left<=x<=right and not covered(x))
    outside_targets.append(dict(x=x,y=y,main=main['id'],blockers=blockers));save()
    desktop.click(x,y)

try:
    for family,icon_title,menu_title,item_y in (
            ('chromium','chromium-browser','Chromium',32 if a.browser_platform else 391),
            ('firefox','firefox-esr','firefox-esr',112 if a.browser_platform else 32)):
        if not any(w['title']==menu_title for w in menus()):
            icon=next(w for w in desktop.command('windows')
                if w['visible'] and w['app_id']=='org.nextspace.Workspace' and w['title']==icon_title)
            # Native menus can cover part of an app icon at high density.
            points=[(icon['x']+x,icon['y']+icon['height']/2) for x in (icon['width']-4,4,icon['width']/2)]
            x,y=next((x,y) for x,y in points if not any(
                w['x']<=x<w['x']+w['width'] and w['y']<=y<w['y']+w['height'] for w in menus()))
            desktop.double_click(x,y)
        menu=until(menus,lambda m:len(m)==1 and m[0]['title']==menu_title,family+' current menu')[0]
        app_id='chromium-browser' if family=='chromium' else 'firefox-esr'
        main=next(w for w in desktop.command('windows') if w['visible'] and w['app_id']==app_id
            and w['level']==0 and 'NEXTSPACE controls' in w['title'])
        check(family+'-one-current-application-menu',True)
        # These are observed item centers in this owned, pinned English model,
        # in logical points. Production code never uses these test coordinates.
        x,y=menu['x']+30,menu['y']+item_y
        for cycle in range(2):
            name=family+'-'+str(cycle+1)
            desktop.click(x,y)
            until(lambda:desktop.command('popups'),bool,name+' first open')
            desktop.capture(name+'-menu-open')
            check(name+'-submenu-opens-on-one-click',True)
            outside(main)
            until(lambda:desktop.command('popups'),bool,name+' persistent native submenu')
            desktop.capture(name+'-menu-after-outside-click')
            # Original nontransient NSMenu remains attached after an action
            # or outside click. A transient Wayland grab must not replace that
            # native lifetime or consume input in the owning foreign app.
            current=next(w for w in desktop.command('windows') if w['id']==main['id'])
            check(name+'-persistent-submenu-keeps-native-lifetime-and-browser-focus',current['focused'])
            desktop.click(x,y)
            until(lambda:desktop.command('popups'),lambda v:not v,name+' native root close')
            desktop.capture(name+'-menu-closed')
            check(name+'-native-root-closes-attached-submenu',True)
            desktop.click(x,y)
            until(lambda:desktop.command('popups'),bool,name+' first reopen')
            desktop.capture(name+'-menu-reopened')
            check(name+'-closed-submenu-reopens-on-one-click',True)
            desktop.click(x,y)
            until(lambda:desktop.command('popups'),lambda v:not v,name+' final native root close')
    save(True)
except BaseException as error:
    save(error=repr(error))
    desktop.capture('ordinary-menu-failure')
    raise

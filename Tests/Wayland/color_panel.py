"""Shared native setup for TimeMon's unmodified system color-panel workflow."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
from gnustep import capture_frame,capture_process_failure,headless_session,process_runtime
from integration import until
from timemon_pause import application_action
from timemon_static_artwork import open_panel


class ColorPanel:
    def __init__(self,app,probe,env,command,artifacts):
        self.app,self.probe,self.env,self.command,self.artifacts=app,probe,env,command,artifacts
        self.runtime=None;self.normal_keyboard_quit=False

    def query(self,*arguments):
        assert self.app.poll() is None,(self.artifacts/'application.log').read_text()
        return application_action(self.probe,self.env,self.artifacts,'controls',*arguments)

    def controls(self):
        return next(w for w in self.query()['windows'] if w['title']=='Colors' and w['visible'])

    def window(self):
        assert self.app.poll() is None,(self.artifacts/'application.log').read_text()
        return next(w for w in self.command('windows') if w['pid']==self.app.pid and w['title']=='Colors' and w['visible'])

    def click(self,rect,dx=.5,dy=.5,window=None):
        w=window or self.window();x,y,width,height=rect
        assert self.command(f"pointer {int(w['x']+x+width*dx)} {int(w['y']+w['height']-y-height*dy)}")['ok']
        assert self.command('button 272')['ok']

    def captured(self,density):
        w=self.window();path=self.artifacts/'native/captures'/f"window-{w['client_id']}-{density}.png"
        if w['preferred_scale']!=density:return False
        frame=capture_frame(path,(w['buffer_width'],w['buffer_height']))
        return (w,frame['image']) if frame else False


@contextmanager
def color_panel(compositor,application,probe,artifacts):
    artifacts.mkdir(parents=True)
    with headless_session(compositor,artifacts/'native') as (env,command):
        with (artifacts/'application.log').open('w') as log:
            app=subprocess.Popen([str(application),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                                  '-NSUseRunningCopy','NO'],env=env,stdout=log,stderr=log)
        panel=ColorPanel(app,probe,env,command,artifacts)
        try:
            until(lambda:application_action(probe,env,artifacts,'state'),'TimeMon registration')
            pref=open_panel(command,app,artifacts,'Preferences',1)
            controls=next(w for w in panel.query()['windows'] if w['title']=='Preferences' and w['visible'])
            button,=controls['buttons'];panel.click(button['base'],window=pref)
            until(lambda:next((w for w in command('windows') if w['pid']==app.pid and w['title']=='Colors' and w['visible']),None),
                  'TimeMon Set button opens the shared color panel')
            yield panel
            panel.runtime=process_runtime(app.pid)
            pickers={line.split()[-1] for line in Path(f'/proc/{app.pid}/maps').read_text().splitlines() if '/ColorPickers/' in line}
            panel.runtime['libraries']=sorted(set(panel.runtime['libraries'])|pickers)
            assert command(f"focus {panel.window()['id']}")['ok']
            for code,state in [(56,1),(16,1),(16,0),(56,0)]:assert command(f'key {code} {state}')['ok']
            app.wait(timeout=10);assert app.returncode==0
            until(lambda:not any(w['pid']==app.pid for w in command('windows')),'Color-panel quit removes its surfaces')
            panel.normal_keyboard_quit=True
        except BaseException:
            try:
                capture_process_failure(app,artifacts,'failure-color-panel')
            except Exception as diagnostic_error:
                (artifacts/'failure-color-panel-diagnostic.txt').write_text(repr(diagnostic_error)+'\n')
            raise
        finally:
            if app.poll() is None:app.terminate();app.wait(timeout=5)

"""Check printing on the existing disposable X11 Workspace fixture."""
import json
from pathlib import Path
import subprocess

from integration import read_json_lines, until
from printing import check_exports


def run(probe, env, artifacts, unflipped=False, profile='portrait', nested=False, reference_directory=None):
    assert env.get('DISPLAY'), 'The X11 Workspace fixture must supply its owned display'
    artifacts.mkdir(parents=True)
    with (artifacts/'probe.log').open('w') as log, (artifacts/'probe.stderr').open('w') as errors:
        client=subprocess.Popen([str(probe),'-GSBackend','libgnustep-x11','-GSTheme','NextSpace',
            '-ExportDirectory',str(artifacts.resolve()),'-UnflippedView','YES' if unflipped else 'NO','-ExportCase',profile,
            '-NestedPrintView','YES' if nested else 'NO'],
            env=env,stdout=log,stderr=errors)
    def xdo(*arguments):
        return subprocess.run(['xdotool',*arguments],env=env,capture_output=True,text=True,timeout=3)
    try:
        def window():
            assert client.poll() is None,(artifacts/'probe.stderr').read_text()[-4000:]
            for identity in xdo('search','--onlyvisible','--pid',str(client.pid),'--name','^PrintingProbe$').stdout.splitlines():
                geometry=xdo('getwindowgeometry','--shell',identity)
                if geometry.returncode==0:
                    fields=dict(line.split('=',1) for line in geometry.stdout.splitlines())
                    if int(fields['WIDTH'])>200 and int(fields['HEIGHT'])>200:return identity
        identity=until(window,'X11 printing document')
        libraries=sorted({line.split()[-1] for line in Path(f'/proc/{client.pid}/maps').read_text().splitlines()
            if any(token in line for token in ('libgnustep-','libobjc.so.'))})
        assert any('libgnustep-x11' in path for path in libraries),libraries
        assert not any('libgnustep-wayland' in path for path in libraries),libraries
        (artifacts/'runtime.json').write_text(json.dumps(dict(executable=str(probe),libraries=libraries),indent=2)+'\n')
        assert xdo('windowactivate','--sync',identity).returncode==0
        assert xdo('mousemove','--window',identity,'30','50','click','1','key','e').returncode==0
        def exported():
            return next((row for row in read_json_lines(artifacts/'probe.log','{') if row.get('event')=='export'),None)
        result=until(exported,'X11 PDF/EPS/printer save');assert result['ok'] and result['scale']==120,result
        check_exports(artifacts,120,unflipped,profile=profile,reference_directory=reference_directory)
        (artifacts/'results.json').write_text(json.dumps(dict(export=result,x11=True,flipped_view=not unflipped,
            profile=profile,nested=nested,physical_printer_tested=False),indent=2)+'\n')
        print('X11 PDF/EPS/printer save: page geometry, orientation, images and text PASS')
    finally:
        if client.poll() is None:
            client.terminate()
            try:client.wait(timeout=5)
            except subprocess.TimeoutExpired:client.kill();client.wait(timeout=5)

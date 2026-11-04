#!/usr/bin/env python3
"""Compare actual AppKit PDF/EPS output across native screen densities."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile
import uuid

from PIL import Image
from gnustep import private_defaults, process_runtime, pasteboard_storage
from integration import read_json_lines, until


def raster(source, destination):
    if source.suffix == '.pdf':
        subprocess.run(['pdftoppm', '-singlefile', '-r', '72', '-png', str(source), str(destination)],
                       check=True, capture_output=True)
    else:
        subprocess.run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-dEPSCrop',
                        '-sDEVICE=png16m', '-r72', '-sOutputFile='+str(destination)+'.png', str(source)],
                       check=True, capture_output=True)
    with Image.open(str(destination)+'.png') as image:
        return image.convert('RGB')


def check_exports(artifacts, scale, unflipped=False, references=None, profile='portrait', reference_directory=None):
    if references is None:references={}
    for extension in ('pdf','eps','ps'):
        image=raster(artifacts/f'print-{scale}.{extension}',artifacts/f'{extension}-{scale}')
        if reference_directory:
            with Image.open(reference_directory/f'{extension}-{scale}.png') as reference:
                assert image.size==reference.size and image.tobytes()==reference.convert('RGB').tobytes(),(
                    extension,scale,'Nested printing differs from the same flat view')
        cropped=profile=='crop' and extension!='ps'
        size=(203,251) if cropped else ((313,257) if profile=='landscape' else (257,313))
        if profile=='landscape' and extension=='ps':
            assert image.size==(257,313),(extension,scale,image.size)
            # Printer jobs keep portrait paper and rotate the landscape view.
            image=image.transpose(Image.Transpose.ROTATE_270)
        assert image.size==size,(extension,scale,image.size)
        # Printing chooses the best image representation independently of the screen.
        for point,color in (((20,20),(255,0,0)),((110,20),(0,255,0)),((20,150),(0,0,255)),((180,150),(0,0,255))):
            if cropped:point=(point[0]-7,point[1]-5)
            if unflipped:point=(point[0],image.height-point[1]-1)
            assert image.getpixel(point)==color,(extension,scale,point,image.getpixel(point))
        if extension not in references:references[extension]=image.tobytes()
        assert image.tobytes()==references[extension],(extension,scale,'Printed pixels changed with screen density')
    text=subprocess.check_output(['pdftotext',str(artifacts/f'print-{scale}.pdf'),'-'],text=True)
    assert 'NEXTSPACE print geometry' in text,text


def run(compositor, probe, artifacts, unflipped=False, profile='portrait', nested=False, reference_directory=None,
        pasteboard_server=None, pasteboard_probe=None):
    assert pasteboard_server and pasteboard_probe, 'Printing needs owned native pasteboard storage'
    artifacts.mkdir(parents=True)
    records=[];references={}
    with tempfile.TemporaryDirectory(prefix='nextspace-printing-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',
                 WLR_HEADLESS_OUTPUTS='2',WLR_RENDERER='pixman',
                 NEXTSPACE_SESSION_ID='test-printing-'+uuid.uuid4().hex)
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        private_defaults(env,runtime)
        (artifacts/'GNUstep.conf').write_bytes(Path(env['GNUSTEP_CONFIG_FILE']).read_bytes())
        (artifacts/'session.json').write_text(json.dumps(dict(session_id=env['NEXTSPACE_SESSION_ID']),indent=2)+'\n')
        captures=artifacts/'captures';captures.mkdir()
        env['NEXTSPACE_WAYLAND_CAPTURE_DIR']=str(captures.resolve())
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        with (artifacts/'compositor.log').open('w') as log:
            server=subprocess.Popen([str(compositor),'-c',str(child.fileno())],env=env,
                pass_fds=[child.fileno()],stdout=subprocess.PIPE,stderr=log,text=True)
        child.close();client=None;services=ExitStack()
        def command(value):
            control.sendall(value.encode());return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout],[],[],10)[0]
            line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
            env['WAYLAND_DISPLAY']=line.split('=',1)[1]
            services.enter_context(pasteboard_storage(pasteboard_server, pasteboard_probe, env, artifacts))
            with (artifacts/'probe.log').open('w') as log, (artifacts/'probe.stderr').open('w') as errors:
                client=subprocess.Popen([str(probe),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                    '-ExportDirectory',str(artifacts.resolve()),'-UnflippedView','YES' if unflipped else 'NO',
                    '-ExportCase',profile,'-NestedPrintView','YES' if nested else 'NO'],
                    env=env,stdout=log,stderr=errors)
            def window():
                assert client.poll() is None,(artifacts/'probe.stderr').read_text()[-4000:]
                return next((w for w in command('windows') if w['pid']==client.pid and
                             w['title']=='PrintingProbe' and w['style']==3),None)
            w=until(window,'native printing window');assert not w['legacy']
            until(lambda:any(row.get('event')=='ready' for row in read_json_lines(
                artifacts/'probe.log','{')), 'printing event loop ready')
            outputs=command('outputs');target=outputs[0]
            (artifacts/'runtime.json').write_text(json.dumps(process_runtime(client.pid),indent=2)+'\n')
            for scale in (120,150,180,210,240,120):
                assert command(f"test-scale {target['name']} {scale} 10000")['ok']
                assert command('confirm')['ok']
                assert command(f"move {w['id']} {target['x']+10} {target['y']+10}")['ok']
                until(lambda: window()['preferred_scale']==scale and window()['buffer_width']==
                      (window()['width']*scale+60)//120,'printing window backing density')
                def screen_image():
                    current=window()
                    path=captures/f"window-{current['client_id']}-{scale}.png"
                    try:
                        with Image.open(path) as image:
                            if image.size!=(current['buffer_width'],current['buffer_height']):return False
                            height=257 if profile=='landscape' else 313
                            y=height-150-1 if unflipped else 150
                            point=(round((current['frame_left']+180)*scale/120),
                                   round((current['frame_top']+y)*scale/120))
                            return image.convert('RGB').getpixel(point)==((255,0,0) if scale==120 else (0,0,255))
                    except OSError:return False
                until(screen_image,'screen image representation follows backing density')
                count=len(read_json_lines(artifacts/'probe.log','{'))
                assert command(f"focus {w['id']}")['ok']
                current=window()
                assert command(f"pointer {current['x']+30} {current['y']+50}")['ok']
                assert command('button 272')['ok']
                assert command('key 18 1')['ok'];assert command('key 18 0')['ok']
                def exported():
                    rows=read_json_lines(artifacts/'probe.log','{')[count:]
                    return next((row for row in rows if row.get('event')=='export' and row['scale']==scale),None)
                result=until(exported,'PDF and EPS export');assert result['ok'],result
                check_exports(artifacts,scale,unflipped,references,profile,reference_directory)
                records.append(dict(scale=scale,window=window(),export=result))
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,pdf_eps_density_independent=True,
                printer_save_density_independent=True,flipped_view=not unflipped,profile=profile,nested=nested,
                physical_printer_tested=False),indent=2)+'\n')
            print('AppKit PDF/EPS/printer save: six density transitions, exact raster/page geometry and text PASS')
        except BaseException:
            (artifacts/'failure.json').write_text(json.dumps(dict(windows=command('windows'),records=records,
                events=read_json_lines(artifacts/'probe.log','{') if (artifacts/'probe.log').exists() else []),indent=2)+'\n')
            raise
        finally:
            if client and client.poll() is None:client.terminate();client.wait(timeout=5)
            services.close()
            if server.poll() is None:control.sendall(b'quit');server.wait(timeout=5)
            server.stdout.close();control.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compositor','probe','artifacts','pasteboard-server','pasteboard-probe'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--unflipped',action='store_true')
    parser.add_argument('--profile',choices=('portrait','crop','landscape'),default='portrait')
    parser.add_argument('--nested',action='store_true')
    parser.add_argument('--reference',type=Path)
    args=parser.parse_args();run(args.compositor.resolve(),args.probe.resolve(),args.artifacts.resolve(),args.unflipped,
        args.profile,args.nested,args.reference.resolve() if args.reference else None,
        args.pasteboard_server.resolve(),args.pasteboard_probe.resolve())

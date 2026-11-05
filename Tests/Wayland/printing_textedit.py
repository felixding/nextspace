#!/usr/bin/env python3
"""Exercise TextEdit's real document pagination and printer-save path."""
import argparse,json,os,select,socket,subprocess,tempfile
from pathlib import Path
from PIL import Image
from gnustep import private_defaults
from integration import until
from text_input import stop_process

CONTENT='NEXTSPACE application printing\n'+''.join(f'Line {i:03d}: retained document text\n' for i in range(60))


def pages(source,directory):
    pdf=directory/'print.pdf'
    subprocess.run(['gs','-q','-dSAFER','-dBATCH','-dNOPAUSE','-dAutoRotatePages=/None','-sDEVICE=pdfwrite',
                    '-sOutputFile='+str(pdf),str(source)],check=True,capture_output=True)
    text=subprocess.check_output(['pdftotext','-layout',str(pdf),'-'],text=True)
    assert all(f'Line {index:03d}' in text for index in range(60)),text
    subprocess.run(['pdftoppm','-r','72','-png',str(pdf),str(directory/'page')],check=True,capture_output=True)
    rendered=[]
    for path in sorted(directory.glob('page-*.png')):
        with Image.open(path) as image:
            assert image.size==(257,313),image.size
            rendered.append(image.convert('RGB').tobytes())
    assert 2<=len(rendered)<=20,len(rendered)
    return rendered


def print_document(probe,env,directory,layout,orientation):
    directory.mkdir();path=directory/'print.ps'
    result=subprocess.run([str(probe),'--textedit-print',str(path),layout,orientation],env=env,
                          capture_output=True,text=True,timeout=20)
    (directory/'request.json').write_text(json.dumps(dict(returncode=result.returncode,
        stdout=result.stdout,stderr=result.stderr),indent=2)+'\n')
    assert result.returncode==0,(result.stdout,result.stderr)
    assert json.loads(result.stdout)['saved'] and path.stat().st_size>0
    return pages(path,directory)


def run(compositor,textedit,probe,artifacts,pasteboard_server,pasteboard_probe,layouts=('continuous','paged')):
    artifacts.mkdir(parents=True);home=artifacts/'home';home.mkdir();records=[]
    document=artifacts/'document.txt'
    document.write_text(CONTENT)
    with tempfile.TemporaryDirectory(prefix='nextspace-textedit-printing-') as runtime:
        env=dict(os.environ,HOME=str(home),XDG_RUNTIME_DIR=runtime,WLR_BACKENDS='headless',WLR_HEADLESS_OUTPUTS='2',
                 WLR_RENDERER='pixman',NEXTSPACE_SESSION_ID='test-'+Path(runtime).name,NEXTSPACE_GS_BACKEND='wayland')
        for key in ('DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET'):env.pop(key,None)
        private_defaults(env,runtime)
        control,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);control.settimeout(5)
        server=client=storage=None
        def command(value):
            control.sendall(value.encode());return json.loads(control.recv(65536))
        try:
            with (artifacts/'compositor.log').open('w') as log:
                server=subprocess.Popen([str(compositor),'-c',str(child.fileno())],env=env,
                    pass_fds=[child.fileno()],stdout=subprocess.PIPE,stderr=log,text=True)
            child.close();assert select.select([server.stdout],[],[],10)[0]
            line=server.stdout.readline().strip();assert line.startswith('WAYLAND_DISPLAY='),line
            env['WAYLAND_DISPLAY']=line.split('=',1)[1]
            with (artifacts/'gpbs.log').open('w') as log:
                storage=subprocess.Popen([str(pasteboard_server),'--no-fork'],env=env,stdout=log,stderr=log)
            def pasteboard_ready():
                assert storage.poll() is None,(artifacts/'gpbs.log').read_text()[-2000:]
                return subprocess.run([str(pasteboard_probe),'--ping'],env=env,
                    capture_output=True,timeout=3).returncode==0
            until(pasteboard_ready,'owned native pasteboard storage')
            with (artifacts/'textedit.log').open('w') as log:
                client=subprocess.Popen([str(textedit),'-GSBackend','libgnustep-wayland','-GSTheme','NextSpace',
                    '-GSFilePath',str(document),'-NSUseRunningCopy','NO'],env=env,stdout=log,stderr=log)
            def window():
                assert client.poll() is None,(artifacts/'textedit.log').read_text()[-3000:]
                return next((w for w in command('windows') if w['pid']==client.pid and w['width']>200),None)
            w=until(window,'native TextEdit document');assert not w['legacy']
            names=[o['name'] for o in command('outputs')]
            for paged in layouts:
                for orientation in ('portrait','landscape'):
                    references=None
                    for index,scale in enumerate((120,150,180,210,240,120)):
                        output=names[index%len(names)]
                        assert command(f'test-scale {output} {scale} 10000')['ok'];assert command('confirm')['ok']
                        output=next(o for o in command('outputs') if o['name']==output)
                        assert command(f"move {w['id']} {output['x']+10} {output['y']+10}")['ok']
                        until(lambda: window()['preferred_scale']==scale,'TextEdit density')
                        assert command(f"focus {w['id']}")['ok']
                        directory=artifacts/f'{paged}-{orientation}-{index}-{scale}'
                        rendered=print_document(probe,env,directory,paged,orientation)
                        if references is None:references=rendered
                        assert rendered==references,(paged,orientation,scale,'Printed page pixels or pagination changed with screen density')
                        assert document.read_text()==CONTENT
                        records.append(dict(scale=scale,paged=paged,orientation=orientation,pages=len(rendered),window=window()))
                        (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=False),indent=2)+'\n')
            libraries=sorted({line.split()[-1] for line in Path(f'/proc/{client.pid}/maps').read_text().splitlines()
                if any(token in line for token in ('libgnustep-','libobjc.so.','libDesktopKit','libSystemKit','GSPrinting/'))})
            (artifacts/'runtime.json').write_text(json.dumps(dict(executable=str(textedit),libraries=libraries),indent=2)+'\n')
            (artifacts/'results.json').write_text(json.dumps(dict(cases=records,complete=True,
                document_unchanged=True,physical_printer_tested=False),indent=2)+'\n')
            print('TextEdit document printing: continuous/paged, portrait/landscape, exact multi-page output across six density transitions PASS')
        except BaseException:
            (artifacts/'failure.json').write_text(json.dumps(dict(cases=records,
                windows=command('windows') if server and server.poll() is None else []),indent=2)+'\n')
            raise
        finally:
            if client:stop_process(client)
            if storage:stop_process(storage)
            if server:
                if server.poll() is None:command('quit');server.wait(timeout=5)
                server.stdout.close()
            child.close();control.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    names=('compositor','textedit','probe','artifacts','pasteboard-server','pasteboard-probe')
    for name in names:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--layout',choices=('continuous','paged'))
    args=p.parse_args();run(*(getattr(args,name.replace('-','_')).resolve() for name in names),
        layouts=(args.layout,) if args.layout else ('continuous','paged'))

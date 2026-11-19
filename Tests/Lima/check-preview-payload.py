"""Verify the delivery payload against libraries mapped by the ordinary preview."""
import argparse,hashlib,json,os,socket,struct
from pathlib import Path
import sys
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('root',type=Path)
parser.add_argument('--payload',type=Path,default=Path(__file__).resolve().parents[2]/'.build/native-ui/runtime-update')
parser.add_argument('--browser-platform',action='store_true')
args=parser.parse_args();root=args.root;payload=args.payload
bridge=Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge'
sys.path.insert(0,str(bridge))
def digest(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()
def verify_webui(family,executable,receipt_path):
 if args.browser_platform and family=='chromium':
  from chromium_webui import EXECUTABLE_SHA256, PACK_SHA256
  assert not receipt_path.exists(),'Chromium replaced its original WebUI resources'
  assert digest(executable)==EXECUTABLE_SHA256
  assert digest(executable.parent/'resources.pak')==PACK_SHA256
  return dict(case='chromium-original-builtin-resources',passed=True)
 receipt=json.loads(receipt_path.read_text())
 private=Path(receipt['root'])
 assert executable.parent==private,(executable,private)
 assert digest(executable)==receipt['executable_sha256']
 prefix=receipt['adapter_prefix']
 common=(bridge/'NativeWebControls.js').read_text()+'\n'+(bridge/f'{family.capitalize()}WebUI.js').read_text()
 if family=='firefox':
  from firefox_webui import PANEL_PATH, TOOLTIP_PATH, EDITOR_PATH
  common=common.replace('__NXS_WEBUI_PREFIX__',prefix or '')
  if args.browser_platform:
   assert prefix is None and receipt['shared_base_resources']==[PANEL_PATH,TOOLTIP_PATH,EDITOR_PATH]
  else:
   common+='\nnxsNativeFirefox(document);\n'
  assert digest(private/'omni.ja')==receipt['private_pack_sha256']
  assert digest(private/'browser/omni.ja')==receipt['private_browser_pack_sha256']
  assert digest(bridge/'FirefoxDevTools.js')==receipt['devtools_adapter_sha256']
 else:
  common=common.replace('__NXS_RADIO_PREFIX__',prefix)
  assert digest(private/'resources.pak')==receipt['private_pack_sha256']
 assert hashlib.sha256(common.encode()).hexdigest()==receipt['adapter_sha256']
 return dict(case=family+'-shared-builtin-adapter-and-private-resources-match',passed=True,root=str(private))
def control(value):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(20);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=value)).encode());return json.loads(s.recv(1048576))
windows=control('windows');checks=[];stage=None
for app,hook in [('chromium-browser','chromium-density-06.so'),('firefox-esr','firefox-root-04.so')]:
 w=next(w for w in windows if w['app_id']==app and w['level']==0)
 command=(Path('/proc')/str(w['pid'])/'cmdline').read_bytes().split(b'\0')
 assert not any(flag in arg for arg in command for flag in
                (b'--marionette',b'--remote-debugging',b'--remote-allow-system-access')),command
 family='firefox' if app=='firefox-esr' else 'chromium'
 # Chromium rewrites argv[0] to its complete process title. The kernel's
 # executable link identifies the running file independently of that title.
 executable=(Path('/proc')/str(w['pid'])/'exe').resolve()
 checks.append(verify_webui(family,executable,root/'runtime'/f'{family}-profile/native-webui.json'))
 paths={line.split()[-1] for line in (Path('/proc')/str(w['pid'])/'maps').read_text().splitlines() if len(line.split())>=6}
 mapped=next(Path(p) for p in paths if p.endswith('/'+hook));stage=mapped.parent
 assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256((payload/hook).read_bytes()).digest()
 checks.append(dict(case=app+'-exact-delivery-hook-mapped',passed=True,pid=w['pid'],path=str(mapped)))
 geometry=['libnextspace-wayland-geometry.so.0.1']
 if app=='firefox-esr':geometry.append('libnextspace-gtk3-geometry.so.0.1')
 for name in geometry:
  library=next(Path(p) for p in paths if p.endswith('/'+name))
  assert library==stage/'native-ui'/name,library
  assert hashlib.sha256(library.read_bytes()).digest()==hashlib.sha256((payload/'native-ui'/name).read_bytes()).digest()
  checks.append(dict(case=app+'-'+name+'-exact-delivery-library-mapped',passed=True,pid=w['pid'],path=str(library)))
 if app=='firefox-esr':
  parent_log='\n'.join(line for line in (root/'firefox-hook.log').read_text().splitlines() if line.startswith(str(w['pid'])+' '))
  features=['native Gecko color binding installed','native Gecko original key registry and global menu binding installed',
            'native Gecko focus/input ordering installed','original GTK activation handoff enabled',
            'original GTK activation input ordering enabled',
            'original GTK activation tokens requested at presentation']
  if args.browser_platform:
   features.append('native Gecko edit bindings enabled')
   assert 'native Gecko text bindings installed' not in parent_log
  else:
   features.extend(['native Gecko text bindings installed','native Gecko frontend text binding installed'])
  assert all(message in parent_log for message in features),'Firefox parent missed native feature negotiation'
  checks.append(dict(case='firefox-parent-native-features-negotiated',passed=True,pid=w['pid'],features=features))
 elif args.browser_platform:
  parent_log='\n'.join(line for line in (root/'chromium-hook.log').read_text().splitlines() if line.startswith(str(w['pid'])+' '))
  assert 'native LinuxUi edit bindings enabled' in parent_log
  checks.append(dict(case='chromium-parent-native-edit-commands-negotiated',passed=True,pid=w['pid']))
prefs=(root/'runtime/firefox-profile/prefs.js').read_text()
assert 'user_pref("focusmanager.testmode", true)' not in prefs
checks.append(dict(case='ordinary-browsers-without-automation-focus-overrides',passed=True))
for row in json.loads((payload/'manifest.json').read_text()):
 p=stage/row['path']
 if 'link' in row:assert p.is_symlink() and os.readlink(p)==row['link'],row
 else:assert not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row
ordinary=root/'ordinary-picker-ux.json'
endpoint=next(line.split('=',1)[1] for line in (root/'session.stdout').read_text().splitlines()
              if line.startswith('NEXTSPACE_NATIVE_UI_SOCKET='))
with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
 connection.connect(endpoint)
 supervisor,uid,gid=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
 assert uid==os.getuid(),(supervisor,uid,gid)
# The session supervisor accepts the public connection and passes its fd to
# the native host. SO_PEERCRED therefore identifies the supervisor. Resolve its
# single host child, then verify its mapped provider and real panel ownership.
children=(Path('/proc')/str(supervisor)/'task'/str(supervisor)/'children').read_text().split()
hosts=[]
for pid in children:
 try:
  argv=(Path('/proc')/pid/'cmdline').read_bytes().split(b'\0')
  if any(arg.endswith(b'/NativeUI/Host/main.py') for arg in argv):hosts.append(int(pid))
 except FileNotFoundError:pass
assert len(hosts)==1,dict(supervisor=supervisor,host_children=hosts)
host=hosts[0]
if ordinary.exists():
 rows=json.loads(ordinary.read_text());assert rows['complete'] and all(r['passed'] for r in rows['checks'])
 assert host==next(r['window']['pid'] for r in rows['checks'] if r.get('window'))
else:
 panel_receipt=root/'production-panel-checks.json'
 if panel_receipt.exists():
  panels=json.loads(panel_receipt.read_text());assert host==panels[0]['panel'][0]['pid']
paths={line.split()[-1] for line in (Path('/proc')/str(host)/'maps').read_text().splitlines() if len(line.split())>=6}
for name in ['libnextspace-native-ui.so.0.1','libnextspace-native-ui-gnustep.so.0.1','libgnustep-gui.so.0.32.0']:
 matches=[Path(p) for p in paths if p.endswith('/'+name)]
 assert len(matches)==1,dict(pid=host,missing_library=name,mapped_libraries=sorted(p for p in paths if '.so' in p))
 mapped=matches[0];assert mapped.parent==stage/'native-ui',mapped
 assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256((payload/'native-ui'/name).read_bytes()).digest()
 checks.append(dict(case=name+'-exact-delivery-library-mapped',passed=True,pid=host,path=str(mapped)))
name='libgnustep-wayland-032.bundle/libgnustep-wayland-032'
mapped=next(Path(p) for p in paths if p.endswith('/'+name))
assert mapped==stage/'native-ui'/name,mapped
assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256((payload/'native-ui'/name).read_bytes()).digest()
checks.append(dict(case='exact-delivery-wayland-backend-mapped',passed=True,pid=host,path=str(mapped)))
compositors=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  mapped=(proc/'exe').resolve()
  if mapped==stage/'nextspace-compositor':compositors.append((int(proc.name),mapped))
 except (OSError,RuntimeError):pass
assert len(compositors)==1,compositors
pid,mapped=compositors[0]
assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256((payload/'nextspace-compositor').read_bytes()).digest()
checks.append(dict(case='exact-delivery-compositor-running',passed=True,pid=pid,path=str(mapped)))
workspace=next(w for w in windows if w['app_id']=='org.nextspace.Workspace')
pid=workspace['pid'];mapped=(Path('/proc')/str(pid)/'exe').resolve()
assert mapped==stage/'Workspace.app/Workspace',mapped
assert hashlib.sha256(mapped.read_bytes()).digest()==hashlib.sha256((payload/'Workspace.app/Workspace').read_bytes()).digest()
checks.append(dict(case='exact-delivery-workspace-running',passed=True,pid=pid,path=str(mapped)))
checks.append(dict(case='all-delivery-runtime-manifest-records-match-running-stage',passed=True,records=len(json.loads((payload/'manifest.json').read_text()))))
(root/'production-payload-checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(dict(complete=True,checks=len(checks),stage=str(stage))))

"""Owned Chromium DevTools transport on its original inherited pipe descriptors."""
import json,os,select,subprocess,sys,time

class CDPPipe:
 def __init__(self,arguments,environment,output,hook):
  read_input,write_input=os.pipe();read_output,write_output=os.pipe()
  self.descriptors=(write_input,read_output);self.pending=b'';self.serial=0
  self.history=output/'cdp-transport.jsonl'
  launcher=output/'chromium-pipe.py'
  launcher.write_text('import os,sys\nr,w=int(sys.argv[1]),int(sys.argv[2])\nos.dup2(r,3);os.dup2(w,4)\nos.set_inheritable(3,True);os.set_inheritable(4,True)\nfor fd in (r,w):\n if fd not in (3,4):os.close(fd)\nos.environ["LD_PRELOAD"]=sys.argv[3]\nos.execv(sys.argv[4],sys.argv[4:])\n')
  environment=dict(environment);environment.pop('LD_PRELOAD',None)
  try:
   with (output/'browser.stdout').open('w') as log,(output/'browser.stderr').open('w') as error:
    self.process=subprocess.Popen([sys.executable,str(launcher),str(read_input),str(write_output),str(hook),*arguments],env=environment,pass_fds=(read_input,write_output),stdout=log,stderr=error)
  except BaseException:
   self.close();raise
  finally:
   os.close(read_input);os.close(write_output)
 def record(self,event,**values):
  with self.history.open('a') as stream:stream.write(json.dumps(dict(event=event,time=time.monotonic(),**values))+'\n')
 def call(self,request):
  self.serial+=1;request=dict(request,id=self.serial)
  self.record('request',id=self.serial,method=request['method'],sessionId=request.get('sessionId'))
  os.write(self.descriptors[0],json.dumps(request).encode()+b'\0');deadline=time.monotonic()+15
  try:
   while True:
    while b'\0' in self.pending:
     line,self.pending=self.pending.split(b'\0',1)
     if not line:continue
     reply=json.loads(line)
     if 'method' in reply:self.record('notification',notification=reply)
     else:self.record('response',id=reply.get('id'),error=reply.get('error'))
     if reply.get('id')==self.serial:return reply
    assert time.monotonic()<deadline,'Owned CDP pipe response'
    if not select.select([self.descriptors[1]],[],[],1)[0]:continue
    data=os.read(self.descriptors[1],65536);assert data,'Owned CDP pipe closed';self.pending+=data
  except BaseException as error:
   self.record('failure',id=self.serial,method=request['method'],error=str(error),browser_returncode=self.process.poll())
   raise
 def close(self):
  for descriptor in self.descriptors:os.close(descriptor)

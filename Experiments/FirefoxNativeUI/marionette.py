#!/usr/bin/env python3
"""Sequential client for an owned Firefox fixture's built-in Marionette port."""
import json,socket

class Marionette:
    def __init__(self,port,timeout=20):
        self.connection=socket.create_connection(('127.0.0.1',port),timeout=timeout)
        self.sequence=0;self.has_session=False
        try:
            self.greeting=self.receive()
            assert self.greeting.get('applicationType')=='gecko',self.greeting
            assert self.greeting.get('marionetteProtocol')==3,self.greeting
        except BaseException:
            self.connection.close();raise
    def receive(self):
        length=b''
        while True:
            byte=self.connection.recv(1)
            if not byte:raise EOFError('Firefox disconnected')
            if byte==b':':break
            if not byte.isdigit() or len(length)>9:raise ValueError('Invalid Marionette frame')
            length+=byte
        remaining=int(length);assert 0<remaining<=32*1024*1024
        parts=[]
        while remaining:
            data=self.connection.recv(remaining)
            if not data:raise EOFError('Truncated Marionette frame')
            parts.append(data);remaining-=len(data)
        return json.loads(b''.join(parts))
    def command(self,name,parameters=None):
        self.sequence+=1
        data=json.dumps([0,self.sequence,name,parameters or {}],ensure_ascii=False).encode('utf-8')
        self.connection.sendall(str(len(data)).encode()+b':'+data)
        kind,sequence,error,result=self.receive()
        assert kind==1 and sequence==self.sequence
        if error:raise RuntimeError(json.dumps(error))
        if name=='WebDriver:NewSession':self.has_session=True
        elif name=='WebDriver:DeleteSession':self.has_session=False
        return result
    def close(self):
        try:
            if self.has_session:self.command('WebDriver:DeleteSession')
        finally:self.connection.close()

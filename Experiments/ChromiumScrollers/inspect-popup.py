#!/usr/bin/env python3
"""Read a fixture popup's actual NativeUI state without changing its input/model."""
import argparse,ctypes as C,json,socket
from pathlib import Path
from helper import Response
from native_controls import ControlRequest,MAGIC
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--socket',type=Path,required=True)
p.add_argument('--log',type=Path,required=True)
p.add_argument('--model-count',type=int,required=True,help='Unique item count in the private test fixture')
p.add_argument('--item',type=int,default=1)
a=p.parse_args()
rows=[json.loads(line) for line in a.log.read_text().splitlines()]
model=next(row for row in reversed(rows) if row['event']=='native-popup-model' and row['count']==a.model_count)
with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as connection:
    connection.settimeout(3);connection.connect(str(a.socket))
    def query(operation):
        request=ControlRequest(magic=MAGIC,operation=operation,process=model['process'],kind=6,control=model['control'],x=a.item)
        connection.send(bytes(request));data=connection.recv(65536)
        assert len(data)==C.sizeof(Response)
        response=Response.from_buffer_copy(data);assert response.magic==MAGIC
        return response
    state=query(5);rectangle=query(12).parts[6]
    print(json.dumps(dict(process=model['process'],control=model['control'],value=state.parts[0].x,
        actions=state.parts[0].width,tracking=bool(state.parts[0].y),visible=state.parts[6].width>0,
        highlighted=state.parts[5].y,menu_frame={key:getattr(state.parts[6],key) for key in ('x','y','width','height')},
        item_rect={key:getattr(rectangle,key) for key in ('x','y','width','height')})))

"""Regenerate the owned stored Macintosh archive fixtures."""
from pathlib import Path
import binascii
import struct
import zlib

fixtures = Path(__file__).resolve().parent
payload = (fixtures / 'legacy.txt').read_bytes()
resource = b'NEXTSPACE resource fork\n'
name = b'legacy.txt'

def crc16(data):
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xa001 if crc & 1 else 0)
    return crc

def put(header, offset, code, value):
    struct.pack_into('>' + code, header, offset, value)

file = bytearray(112)
file[2] = len(name)
file[3:3 + len(name)] = name
file[66:74] = b'TEXTttxt'
for offset in (76, 80):
    put(file, offset, 'I', 2082844800)
for offset, value in ((84, len(resource)), (88, len(payload)), (92, len(resource)), (96, len(payload))):
    put(file, offset, 'I', value)
put(file, 100, 'H', crc16(resource))
put(file, 102, 'H', crc16(payload))
put(file, 110, 'H', crc16(file[:110]))
header = bytearray(22)
header[:4] = b'SIT!'
put(header, 4, 'H', 1)
put(header, 6, 'I', 22 + len(file) + len(resource) + len(payload))
header[10:14] = b'rLau'
header[14] = 1
(fixtures / 'legacy.sit').write_bytes(header + file + resource + payload)

header = bytearray(94)
header[0] = len(name)
header[1:1 + len(name)] = name
header[64:72] = b'TEXTttxt'
put(header, 76, 'I', len(payload))
put(header, 80, 'I', len(resource))
for offset in (84, 88):
    put(header, offset, 'I', 2082844800)
put(header, 92, 'H', binascii.crc_hqx(header[:92], 0))
(fixtures / 'legacy.pit').write_bytes(b'PMag' + header + payload + resource +
    struct.pack('>H', binascii.crc_hqx(payload + resource, 0)) + b'PEnd')

assert not any(value in (0x81, 0x82) for value in resource + payload)
file = bytearray(80)
file[0] = len(name)
file[1:1 + len(name)] = name
put(file, 36, 'I', 8)
file[40:48] = b'TEXTttxt'
for offset in (48, 52):
    put(file, offset, 'I', 2082844800)
put(file, 58, 'I', zlib.crc32(resource + payload) ^ 0xffffffff)
for offset, value in ((64, len(resource)), (68, len(payload)), (72, len(resource)), (76, len(payload))):
    put(file, offset, 'I', value)
index = bytes(file[:1 + len(name)]) + bytes(file[35:])
entry_count = b'\0\1\0'
header = b'\1\0\0\0' + struct.pack('>I', 8 + len(resource) + len(payload))
header2 = struct.pack('>I', zlib.crc32(entry_count + index) ^ 0xffffffff) + entry_count
(fixtures / 'legacy.cpt').write_bytes(header + resource + payload + header2 + index)
(fixtures / 'legacy.txt').write_bytes(payload)
(fixtures / 'resource.txt').write_bytes(resource)

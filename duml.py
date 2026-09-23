"""Protocolo DUML da DJI sobre serial (CDC-ACM)."""
import struct

# CRC8: poly refletido 0x8C, init 0x77 (cabecalho)
def _mk8():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x8C if c & 1 else c >> 1
        t.append(c)
    return t

# CRC16: poly refletido 0x8408, init 0x3692 (pacote inteiro)
def _mk16():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x8408 if c & 1 else c >> 1
        t.append(c)
    return t

T8, T16 = _mk8(), _mk16()

def crc8(data, seed=0x77):
    c = seed
    for b in data:
        c = T8[(c ^ b) & 0xFF]
    return c

def crc16(data, seed=0x3692):
    c = seed
    for b in data:
        c = (c >> 8) ^ T16[(c ^ b) & 0xFF]
    return c & 0xFFFF

def build(src, dst, seq, cmd_type, cmd_set, cmd_id, payload=b'', version=1):
    length = 13 + len(payload)
    hdr = bytes([0x55, length & 0xFF, ((length >> 8) & 0x03) | ((version & 0x3F) << 2)])
    hdr += bytes([crc8(hdr)])
    body = bytes([src, dst]) + struct.pack('<H', seq) + bytes([cmd_type, cmd_set, cmd_id]) + payload
    pkt = hdr + body
    return pkt + struct.pack('<H', crc16(pkt))

def addr(dev_type, index=0):
    return (dev_type & 0x1F) | ((index & 0x07) << 5)

class Parser:
    """Extrai pacotes DUML de um fluxo de bytes."""
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(0x55)
            if i < 0:
                self.buf.clear()
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < 4:
                break
            length = self.buf[1] | ((self.buf[2] & 0x03) << 8)
            if length < 13 or crc8(self.buf[:3]) != self.buf[3]:
                del self.buf[0]
                continue
            if len(self.buf) < length:
                break
            pkt = bytes(self.buf[:length])
            del self.buf[:length]
            if crc16(pkt[:-2]) == struct.unpack('<H', pkt[-2:])[0]:
                out.append(pkt)
        return out

def describe(pkt):
    return dict(src=pkt[4], dst=pkt[5], seq=struct.unpack('<H', pkt[6:8])[0],
                ctype=pkt[8], cset=pkt[9], cid=pkt[10], payload=pkt[11:-2])

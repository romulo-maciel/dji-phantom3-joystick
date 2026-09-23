#!/usr/bin/env python3
"""Leitura do radio DJI Phantom 3 pela porta serial (DUML).

O radio nao transmite sozinho: e preciso pedir. O pedido e um pacote DUML
cmd_set 0x06 (REMOTE_CTRL) / cmd_id 0x27, endereçado ao destino 0x0E.
A resposta tem 58 bytes e carrega as posicoes dos sticks.
"""
import struct
import time

import serial

import duml

# handshake proprietario (preambulo 55 aa 55 aa), do mDjiController
INIT = bytes([0x55, 0xaa, 0x55, 0xaa, 0x1e, 0x00, 0x01, 0x00, 0x00, 0x01, 0x01,
              0x00, 0x80, 0x00, 0x04, 0x04, 0x74, 0x94, 0x35, 0x00, 0xd8, 0xc0,
              0x41, 0x00, 0x30, 0xf6])

# Pedido endereçado a controladora de voo da AERONAVE (destino 0x03).
# Nao precisamos dele: sem aeronave, o radio fica tentando repassar pelo link
# e o LED de power pisca verde/vermelho. Mantido so para referencia.
PING_AERONAVE = bytes([0x55, 0x0D, 0x04, 0x33, 0x0A, 0x03, 0x04, 0x00, 0x40,
                       0x00, 0x0E, 0xD0, 0xE3])

# Pedido das posicoes dos sticks (destino 0x0E). E o unico que importa.
PING_STICKS = bytes([0x55, 0x0D, 0x04, 0x33, 0x0A, 0x0E, 0x05, 0x00, 0x40,
                     0x06, 0x27, 0x58, 0x35])

# o que o mDjiController manda: os dois colados
PING = PING_AERONAVE + PING_STICKS

STICK_REPLY_LEN = 58


class Radio:
    def __init__(self, path='/dev/ttyACM0', baud=115200, pingar_aeronave=False):
        self.port = serial.Serial(path, baud, timeout=0.02, bytesize=8,
                                  parity=serial.PARITY_NONE, stopbits=1)
        self.port.dtr = True
        self.port.rts = True
        time.sleep(0.3)
        self.port.reset_input_buffer()
        self.parser = duml.Parser()
        self.ping = PING if pingar_aeronave else PING_STICKS
        self.port.write(INIT)
        self.port.flush()
        time.sleep(0.2)

    def poll(self):
        """Pede e devolve o payload de sticks mais recente, ou None."""
        self.port.write(self.ping)
        self.port.flush()
        latest = None
        t0 = time.time()
        while time.time() - t0 < 0.05:
            data = self.port.read(256)
            if not data:
                continue
            for pkt in self.parser.feed(data):
                if len(pkt) == STICK_REPLY_LEN and pkt[9] == 0x06 and pkt[10] == 0x27:
                    latest = pkt
            if latest:
                break
        return latest

    def close(self):
        try:
            self.port.close()
        except Exception:
            pass


def words(pkt):
    """Todos os u16 little-endian do pacote, por offset."""
    return {i: struct.unpack_from('<H', pkt, i)[0]
            for i in range(11, len(pkt) - 3)}


def decode(pkt):
    """Offsets confirmados empiricamente neste radio (ver mapa.json)."""
    return {
        'a': struct.unpack_from('<H', pkt, 16)[0],
        'b': struct.unpack_from('<H', pkt, 18)[0],
        'c': struct.unpack_from('<H', pkt, 20)[0],
        'd': struct.unpack_from('<H', pkt, 22)[0],
        'e': struct.unpack_from('<H', pkt, 24)[0],
        'f': struct.unpack_from('<H', pkt, 26)[0],
        'byte28': pkt[28],
        'byte29': pkt[29],
    }

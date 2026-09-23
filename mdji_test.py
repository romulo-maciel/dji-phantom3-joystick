#!/usr/bin/env python3
"""Sequencia exata do mDjiController, o projeto que funciona no rádio GL300C.

initData: handshake proprietario com preambulo 55 aa 55 aa
pingData: dois pacotes DUML colados; o segundo (cmd_set 0x06 / cmd_id 0x27)
          e o pedido de posicao dos sticks.
Resposta esperada: 58 bytes comecando com 0x55, sticks nos offsets 16..23.
"""
import sys
import time

import serial

INIT = bytes([0x55, 0xaa, 0x55, 0xaa, 0x1e, 0x00, 0x01, 0x00, 0x00, 0x01, 0x01,
              0x00, 0x80, 0x00, 0x04, 0x04, 0x74, 0x94, 0x35, 0x00, 0xd8, 0xc0,
              0x41, 0x00, 0x30, 0xf6])

PING = bytes([0x55, 0x0D, 0x04, 0x33, 0x0A, 0x03, 0x04, 0x00, 0x40, 0x00, 0x0E,
              0xD0, 0xE3,
              0x55, 0x0D, 0x04, 0x33, 0x0A, 0x0E, 0x05, 0x00, 0x40, 0x06, 0x27,
              0x58, 0x35])

PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'

port = serial.Serial(PORT, 115200, timeout=0.05, bytesize=8,
                     parity=serial.PARITY_NONE, stopbits=1)
port.dtr = True
port.rts = True
time.sleep(0.3)
port.reset_input_buffer()

total = 0


def drain(seconds, tag):
    global total
    t0 = time.time()
    got = b''
    while time.time() - t0 < seconds:
        d = port.read(512)
        if d:
            got += d
    if got:
        total += len(got)
        print(f"  [{tag}] {len(got)} bytes: {got.hex(' ')}", flush=True)
    return got


print(f"porta: {PORT}")
print("1) initData (handshake 55 aa 55 aa), aguardando 2.5s...")
port.write(INIT)
port.flush()
drain(2.5, 'pos-init')

print("2) loop de ping completo (init+sticks), 15s...")
t0 = time.time()
while time.time() - t0 < 15:
    port.write(PING)
    port.flush()
    drain(0.3, 'pos-ping')

print("3) so o pacote de sticks, sem o resto, 5s...")
port.reset_input_buffer()
t0 = time.time()
while time.time() - t0 < 5:
    port.write(PING[13:])
    port.flush()
    drain(0.3, 'so-sticks')

print("4) init repetido 3x seguidas + ping, 5s...")
for _ in range(3):
    port.write(INIT)
    port.flush()
    time.sleep(0.2)
t0 = time.time()
while time.time() - t0 < 5:
    port.write(PING)
    port.flush()
    drain(0.3, 'init3x')

print(f"\n>>> TOTAL DE BYTES RECEBIDOS: {total}")
port.close()

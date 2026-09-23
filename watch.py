#!/usr/bin/env python3
"""Vigia continua do controle DJI.

Detecta o aparelho aparecendo/sumindo/mudando de identidade USB (assinatura de
modo bootloader) e registra qualquer byte que sair da porta serial, com horario.

Deixe rodando e va testando posicoes de interruptor e sequencias de ligar.
Ctrl-C para sair. Tudo fica salvo em watch.log.
"""
import glob
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duml  # noqa: E402

import serial  # noqa: E402

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'watch.log')
PROBE = '--probe' in sys.argv


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def dji_devices():
    """Todo dispositivo USB que pareca ser DJI, por VID:PID ou por nome."""
    try:
        out = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return set()
    found = set()
    for ln in out.splitlines():
        m = re.search(r'ID ([0-9a-f]{4}):([0-9a-f]{4})(.*)', ln, re.I)
        if not m:
            continue
        vid, pid, name = m.group(1).lower(), m.group(2).lower(), m.group(3).strip()
        # fff0 = VID do controle; 2ca3 = VID oficial da DJI; 0483 = STM32 DFU
        if vid in ('fff0', '2ca3', '0483') or 'dji' in name.lower():
            found.add(f"{vid}:{pid} {name}")
    return found


def main():
    log("=== vigia iniciada ===")
    log("mude interruptores e ligue/desligue o controle a vontade; eu registro tudo")

    known = dji_devices()
    for d in known:
        log(f"presente agora: {d}")

    port = None
    port_path = None
    parser = duml.Parser()
    total = 0
    last_scan = 0.0
    last_probe = 0.0
    seq = 1

    try:
        while True:
            now = time.time()

            # --- vigia a identidade USB ---
            if now - last_scan > 1.0:
                last_scan = now
                cur = dji_devices()
                for d in cur - known:
                    log(f"*** APARECEU: {d}")
                for d in known - cur:
                    log(f"*** SUMIU:    {d}")
                    if port:
                        port.close()
                        port = None
                known = cur

            # --- mantem a porta serial aberta ---
            if port is None:
                paths = sorted(glob.glob('/dev/ttyACM*') + glob.glob('/dev/ttyUSB*'))
                if paths:
                    try:
                        port = serial.Serial(paths[0], 115200, timeout=0.02)
                        port.dtr = True
                        port.rts = True
                        port_path = paths[0]
                        parser = duml.Parser()
                        log(f"porta aberta: {port_path}")
                    except Exception as e:
                        log(f"nao consegui abrir {paths[0]}: {e}")
                        time.sleep(1)
                else:
                    time.sleep(0.3)
                    continue

            # --- sonda opcional ---
            if PROBE and now - last_probe > 1.0:
                last_probe = now
                for dst in (6, 3, 9):
                    try:
                        port.write(duml.build(duml.addr(2, 6), duml.addr(dst, 0),
                                              seq, 0x40, 0x00, 0x01))
                        seq = (seq + 1) & 0xFFFF
                    except Exception:
                        pass

            # --- le tudo que vier ---
            try:
                data = port.read(1024)
            except Exception as e:
                log(f"porta caiu: {e}")
                port = None
                continue

            if data:
                total += len(data)
                log(f"### {len(data)} BYTES (total {total}): {data.hex(' ')}")
                for p in parser.feed(data):
                    i = duml.describe(p)
                    log(f"    DUML src={i['src']:#04x} dst={i['dst']:#04x} "
                        f"set={i['cset']:#04x} id={i['cid']:#04x} "
                        f"payload={i['payload'].hex(' ')}")
    except KeyboardInterrupt:
        log(f"=== encerrada. total de bytes vistos: {total} ===")


if __name__ == '__main__':
    main()

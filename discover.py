#!/usr/bin/env python3
"""Mapeia empiricamente quais bytes do pacote correspondem a cada controle.

Os seis eixos de 16 bits ficam sempre visiveis, com barra ao vivo. Mexa um
controle de cada vez e veja qual linha responde. Ctrl-C salva mapa.json.
"""
import json
import os
import struct
import sys

import dji_rc

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'

# eixos candidatos: u16 alinhados a partir do offset 16
AXIS_OFFSETS = [16, 18, 20, 22, 24, 26]

radio = dji_rc.Radio(PORT)
print(f"conectado em {PORT}")

stat = {off: None for off in AXIS_OFFSETS}   # [min, max, atual]
b_stat = {}
frames = 0


def bar(cur, lo, hi, width=44):
    if hi - lo < 8:
        lo, hi = cur - 1024, cur + 1024
    frac = max(0.0, min(1.0, (cur - lo) / (hi - lo)))
    pos = int(frac * (width - 1))
    cells = [' '] * width
    cells[width // 2] = '|'
    cells[pos] = '#'
    return ''.join(cells)


try:
    while True:
        pkt = radio.poll()
        if not pkt:
            continue
        frames += 1

        for off in AXIS_OFFSETS:
            v = struct.unpack_from('<H', pkt, off)[0]
            s = stat[off]
            if s is None:
                stat[off] = [v, v, v]
            else:
                s[0] = min(s[0], v)
                s[1] = max(s[1], v)
                s[2] = v

        for off in range(11, len(pkt) - 2):
            b_stat.setdefault(off, set()).add(pkt[off])

        if frames % 8:
            continue

        os.system('clear')
        print(f"quadros: {frames}    Ctrl-C para salvar e sair\n")
        print("Mexa UM controle por vez ate o batente dos dois lados.\n")
        print(f"{'offset':>6} {'min':>6} {'max':>6} {'atual':>6} {'ampl':>6}  posicao")
        for off in AXIS_OFFSETS:
            s = stat[off]
            if s is None:
                continue
            lo, hi, cur = s
            span = hi - lo
            flag = '  <== MEXEU' if span > 200 else ''
            print(f"{off:>6} {lo:>6} {hi:>6} {cur:>6} {span:>6}  [{bar(cur, lo, hi)}]{flag}")

        print("\nbytes que mudaram de valor (chaves S1/S2, botoes):")
        sw = [(o, v) for o, v in sorted(b_stat.items())
              if 1 < len(v) <= 8 and o not in
              (16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27)]
        for off, vs in sw[:10]:
            print(f"  offset {off:>3}: {sorted(vs)}")
        if not sw:
            print("  (nenhum ainda)")

except KeyboardInterrupt:
    radio.close()
    out = {
        'eixos': {str(off): {'min': s[0], 'max': s[1], 'amplitude': s[1] - s[0]}
                  for off, s in sorted(stat.items()) if s},
        'bytes_variaveis': {str(off): sorted(vs) for off, vs in sorted(b_stat.items())
                            if 1 < len(vs) <= 8},
        'quadros': frames,
    }
    path = os.path.join(HERE, 'mapa.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nsalvo em {path}\n")
    print(json.dumps(out['eixos'], indent=2))

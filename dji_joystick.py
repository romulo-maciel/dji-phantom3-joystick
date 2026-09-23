#!/usr/bin/env python3
"""Transforma o radio DJI Phantom 3 num joystick virtual para jogos.

Le as posicoes dos sticks pela serial (DUML) e publica um gamepad via uinput,
que aparece como /dev/input/jsN para qualquer jogo ou simulador.

    python3 dji_joystick.py             # roda
    python3 dji_joystick.py --monitor   # roda mostrando os valores ao vivo
    python3 dji_joystick.py --calibrar  # regrava os batentes dos sticks
"""
import argparse
import json
import os
import struct
import sys
import time

from evdev import AbsInfo, UInput
from evdev import ecodes as e

import dji_rc

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, 'config.json')
RANGE = 32767


def carregar():
    with open(CONFIG) as f:
        return json.load(f)


def salvar(cfg):
    with open(CONFIG, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def escalar(bruto, eixo, zona_morta):
    """Converte contagem crua em -32767..32767, com o centro exatamente em 0.

    As duas metades sao escaladas separadamente porque o centro fisico do
    stick nao fica no meio exato entre os batentes.
    """
    lo, ct, hi = eixo['min'], eixo['centro'], eixo['max']

    if eixo.get('tipo') == 'dial':
        # dial nao volta ao centro: mapeia a faixa inteira, sem zona morta
        span = hi - lo
        v = ((bruto - lo) / span * 2 - 1) if span else 0.0
        v = max(-1.0, min(1.0, v))
        if eixo.get('inverter'):
            v = -v
        return int(v * RANGE)

    if bruto >= ct:
        span = hi - ct
        v = (bruto - ct) / span if span else 0.0
    else:
        span = ct - lo
        v = (bruto - ct) / span if span else 0.0

    v = max(-1.0, min(1.0, v))

    if abs(v) < zona_morta:
        v = 0.0
    else:
        # reescala para nao haver salto na borda da zona morta
        v = (abs(v) - zona_morta) / (1 - zona_morta) * (1 if v > 0 else -1)

    if eixo.get('inverter'):
        v = -v
    return int(v * RANGE)


def chaves_do_cfg(cfg):
    """Devolve [(nome, spec)] das chaves configuradas, ignorando comentarios."""
    ch = cfg.get('chaves', {})
    return [(n, s) for n, s in ch.items() if isinstance(s, dict)]


def ler_chave(pkt, cfg, spec):
    """Extrai o campo de 2 bits e devolve (nome_da_posicao, indice_na_ordem)."""
    byte = pkt[cfg['chaves']['offset']]
    codigo = (byte >> spec['deslocamento_bits']) & 0x03
    nome = spec['codigos'].get(str(codigo))
    if nome is None:
        return f"?{codigo}", None
    return nome, spec['ordem'].index(nome)


def montar_uinput(cfg):
    abs_caps = []
    for nome in cfg['eixos']:
        abs_caps.append((getattr(e, nome),
                         AbsInfo(value=0, min=-RANGE, max=RANGE,
                                 fuzz=16, flat=0, resolution=0)))

    botoes = []          # lista de codigos evdev, na ordem
    mapa_botoes = {}     # (chave, posicao) -> codigo evdev
    for nome, spec in chaves_do_cfg(cfg):
        if spec.get('eixo'):
            abs_caps.append((getattr(e, spec['eixo']),
                             AbsInfo(value=0, min=-RANGE, max=RANGE,
                                     fuzz=0, flat=0, resolution=0)))
        for pos, btn in spec.get('botoes', {}).items():
            codigo = getattr(e, btn)
            mapa_botoes[(nome, pos)] = codigo
            botoes.append(codigo)

    caps = {e.EV_ABS: abs_caps}
    if botoes:
        caps[e.EV_KEY] = botoes

    ui = UInput(caps, name='DJI Phantom 3 RC', vendor=0x2ca3,
                product=0x0008, version=1)
    return ui, mapa_botoes


def calibrar(radio, cfg):
    print("\n=== CALIBRACAO DOS STICKS ===")
    print("1) Deixe os dois sticks SOLTOS no centro e tecle Enter.")
    input()
    centros = {}
    amostras = {nome: [] for nome in cfg['eixos']}
    t0 = time.time()
    while time.time() - t0 < 1.5:
        pkt = radio.poll()
        if not pkt:
            continue
        for nome, eixo in cfg['eixos'].items():
            amostras[nome].append(struct.unpack_from('<H', pkt, eixo['offset'])[0])
    for nome, vals in amostras.items():
        if vals:
            centros[nome] = sum(vals) // len(vals)
    print("   centros:", centros)

    print("\n2) Gire os DOIS sticks ate o batente, em circulos, por uns 10s.")
    print("   Gire tambem a RODA DO GIMBAL de ponta a ponta.")
    print("   Tecle Enter para comecar.")
    input()
    lim = {nome: [10 ** 6, -1] for nome in cfg['eixos']}
    t0 = time.time()
    while time.time() - t0 < 10:
        pkt = radio.poll()
        if not pkt:
            continue
        for nome, eixo in cfg['eixos'].items():
            v = struct.unpack_from('<H', pkt, eixo['offset'])[0]
            lim[nome][0] = min(lim[nome][0], v)
            lim[nome][1] = max(lim[nome][1], v)
        resta = 10 - (time.time() - t0)
        print(f"\r   faltam {resta:4.1f}s   " +
              "  ".join(f"{n}:{lim[n][0]}-{lim[n][1]}" for n in lim), end='')
    print()

    for nome, eixo in cfg['eixos'].items():
        eixo['min'] = lim[nome][0]
        eixo['max'] = lim[nome][1]
        eixo['centro'] = centros.get(nome, eixo['centro'])
    salvar(cfg)
    print(f"\nsalvo em {CONFIG}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--monitor', action='store_true', help='mostra os valores ao vivo')
    ap.add_argument('--calibrar', action='store_true', help='regrava os batentes')
    ap.add_argument('--porta', default=None)
    args = ap.parse_args()

    cfg = carregar()
    porta = args.porta or cfg['porta']

    try:
        radio = dji_rc.Radio(porta)
    except Exception as ex:
        sys.exit(f"nao consegui abrir {porta}: {ex}\n"
                 f"o radio esta ligado e o cabo conectado? outro script segurando a porta?")

    if args.calibrar:
        calibrar(radio, cfg)
        radio.close()
        return

    ui, mapa_botoes = montar_uinput(cfg)
    chaves = chaves_do_cfg(cfg)
    print(f"joystick virtual criado: {ui.device.path}  ({ui.device.name})")
    print("ele aparece para os jogos como /dev/input/jsN")
    if chaves:
        print("chaves mapeadas:")
        for nome, spec in chaves:
            binds = ", ".join(f"{p}={b}" for p, b in spec.get('botoes', {}).items())
            print(f"  {nome} -> eixo {spec.get('eixo', '-')} | {binds}")
    print("Ctrl-C para sair.\n")

    zona = cfg.get('zona_morta', 0.02)
    estado_botoes = {}
    quadros = 0
    t_ini = time.time()
    ultimo_print = 0.0

    try:
        while True:
            pkt = radio.poll()
            if not pkt:
                continue
            quadros += 1

            valores = {}
            for nome, eixo in cfg['eixos'].items():
                bruto = struct.unpack_from('<H', pkt, eixo['offset'])[0]
                v = escalar(bruto, eixo, zona)
                valores[nome] = (bruto, v)
                ui.write(e.EV_ABS, getattr(e, nome), v)

            posicoes = {}
            for nome, spec in chaves:
                pos, idx = ler_chave(pkt, cfg, spec)
                posicoes[nome] = pos

                if spec.get('eixo') and idx is not None:
                    n = len(spec['ordem'])
                    v = int((idx / (n - 1) * 2 - 1) * RANGE) if n > 1 else 0
                    ui.write(e.EV_ABS, getattr(e, spec['eixo']), v)

                for p, codigo in mapa_botoes.items():
                    if p[0] != nome:
                        continue
                    apertado = 1 if p[1] == pos else 0
                    if estado_botoes.get(p) != apertado:
                        estado_botoes[p] = apertado
                        ui.write(e.EV_KEY, codigo, apertado)

            ui.syn()

            agora = time.time()
            if args.monitor and agora - ultimo_print > 0.1:
                ultimo_print = agora
                hz = quadros / (agora - t_ini)
                os.system('clear')
                print(f"DJI Phantom 3 RC -> {ui.device.path}     {hz:5.1f} Hz\n")
                for nome, eixo in cfg['eixos'].items():
                    bruto, v = valores[nome]
                    frac = v / RANGE
                    pos_bar = int((frac + 1) / 2 * 43)
                    cells = [' '] * 44
                    cells[22] = '|'
                    cells[max(0, min(43, pos_bar))] = '#'
                    print(f"{eixo['rotulo']:>38}  bruto {bruto:>5}  "
                          f"{v:>7}  [{''.join(cells)}]")
                print()
                for nome, spec in chaves:
                    opcoes = "  ".join(
                        (f"[{o}]" if o == posicoes[nome] else f" {o} ")
                        for o in spec['ordem'])
                    print(f"{spec['rotulo']:>38}  {opcoes}")
                print(f"\n{'byte das chaves':>38}  "
                      f"{pkt[cfg['chaves']['offset']]:08b}")
    except KeyboardInterrupt:
        print("\nencerrando.")
    finally:
        ui.close()
        radio.close()


if __name__ == '__main__':
    main()

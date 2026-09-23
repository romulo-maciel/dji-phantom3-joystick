#!/usr/bin/env python3
"""Descobre quais bytes/bits correspondem as chaves S1 e S2.

Pede uma posicao por vez, da um tempo para voce mexer, le, e registra.
No fim cruza todas as leituras e mostra exatamente qual offset e qual bit
identificam cada posicao. O resultado vai para chaves.json e config.json.
"""
import json
import os
import sys
from collections import Counter

import dji_rc

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'

ESPERA = 6.0      # segundos para voce mexer a chave
AMOSTRA = 1.5     # segundos lendo, depois da espera

# (identificador, instrucao na tela)
PASSOS = [
    ('S1=P  S2=cima',  'S1 na posicao P (toda para CIMA)  |  S2 toda para CIMA'),
    ('S1=A  S2=cima',  'S1 na posicao A (MEIO)            |  S2 continua para CIMA'),
    ('S1=F  S2=cima',  'S1 na posicao F (toda para BAIXO) |  S2 continua para CIMA'),
    ('S1=P  S2=baixo', 'S1 de volta para P (CIMA)         |  S2 toda para BAIXO'),
    ('S1=P  S2=meio',  'S1 continua em P (CIMA)           |  S2 no MEIO, se existir'),
]


def conta_regressiva(segundos, texto):
    import time
    t0 = time.time()
    while True:
        resta = segundos - (time.time() - t0)
        if resta <= 0:
            break
        print(f"\r  {texto}   lendo em {resta:3.1f}s ...", end='', flush=True)
        time.sleep(0.1)
    print("\r" + " " * 70, end='\r')


def amostrar(radio, segundos):
    """Le por N segundos e devolve, por offset, o valor mais frequente
    e o quanto ele foi estavel (0..1)."""
    import time
    pacotes = []
    t0 = time.time()
    while time.time() - t0 < segundos:
        pkt = radio.poll()
        if pkt:
            pacotes.append(pkt)
    if not pacotes:
        return None, 0
    tam = min(len(p) for p in pacotes)
    perfil = {}
    for off in range(tam):
        c = Counter(p[off] for p in pacotes)
        valor, vezes = c.most_common(1)[0]
        perfil[off] = (valor, vezes / len(pacotes))
    return perfil, len(pacotes)


def main():
    try:
        radio = dji_rc.Radio(PORT)
    except Exception as ex:
        sys.exit(f"nao consegui abrir {PORT}: {ex}\n"
                 f"o radio esta ligado? algum outro script segurando a porta "
                 f"(dji_joystick.py, discover.py)? feche antes.")

    print("=" * 68)
    print("  CALIBRACAO DAS CHAVES S1 E S2")
    print("=" * 68)
    print(f"\n  Cada passo: voce tem {ESPERA:.0f}s para posicionar, depois eu leio"
          f" por {AMOSTRA:.1f}s.")
    print("  Nao encoste nos sticks durante a leitura.")
    print("  Se uma posicao nao existir no seu radio, deixe como esta e siga.\n")
    input("  Tecle Enter para comecar. ")

    leituras = {}
    for i, (chave, instrucao) in enumerate(PASSOS, 1):
        print(f"\n[{i}/{len(PASSOS)}] {instrucao}")
        conta_regressiva(ESPERA, "posicione agora")
        print("  lendo...", end='', flush=True)
        perfil, n = amostrar(radio, AMOSTRA)
        if not perfil:
            print(" FALHOU (nenhum pacote). O radio desligou?")
            continue
        leituras[chave] = perfil
        print(f" ok ({n} pacotes)")

    radio.close()

    if len(leituras) < 2:
        sys.exit("\nleituras insuficientes para cruzar.")

    # offsets estaveis dentro de cada passo (>=90% do tempo no mesmo valor)
    # e que mudaram de valor entre passos
    chaves = list(leituras)
    tam = min(len(p) for p in leituras.values())
    interessantes = []
    for off in range(tam):
        vals, estaveis = [], True
        for k in chaves:
            valor, estabilidade = leituras[k][off]
            if estabilidade < 0.9:
                estaveis = False
                break
            vals.append(valor)
        if estaveis and len(set(vals)) > 1:
            interessantes.append((off, vals))

    print("\n" + "=" * 68)
    print("  RESULTADO")
    print("=" * 68)

    if not interessantes:
        print("\n  Nenhum byte estavel mudou entre as posicoes.")
        print("  Ou as chaves nao chegam por essa via, ou elas nao foram movidas.")
        return

    larg = max(len(k) for k in chaves)
    print(f"\n  {'offset':>6}  " + "  ".join(f"{k:>{larg}}" for k in chaves))
    for off, vals in interessantes:
        print(f"  {off:>6}  " + "  ".join(f"{v:>{larg}}" for v in vals))

    print("\n  Em binario (para ver os bits):\n")
    print(f"  {'offset':>6}  " + "  ".join(f"{k:>{max(larg, 8)}}" for k in chaves))
    for off, vals in interessantes:
        print(f"  {off:>6}  " + "  ".join(f"{v:>0{max(larg, 8)}b}" for v in vals))

    # quais bits distinguem cada posicao
    print("\n  Bits que mudam, por offset:")
    for off, vals in interessantes:
        mudam = 0
        for v in vals[1:]:
            mudam |= (v ^ vals[0])
        bits = [b for b in range(8) if mudam & (1 << b)]
        print(f"    offset {off:>3}: bits {bits}")

    saida = {
        'leituras': {k: {str(off): leituras[k][off][0] for off, _ in interessantes}
                     for k in chaves},
        'offsets_relevantes': [off for off, _ in interessantes],
    }
    caminho = os.path.join(HERE, 'chaves.json')
    with open(caminho, 'w') as f:
        json.dump(saida, f, indent=2, ensure_ascii=False)
    print(f"\n  salvo em {caminho}")


if __name__ == '__main__':
    main()

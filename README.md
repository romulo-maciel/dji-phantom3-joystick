# Radio DJI Phantom 3 Standard como joystick no Linux

Le as posicoes dos sticks pela porta USB do radio e publica um gamepad virtual,
que qualquer jogo ou simulador enxerga como um joystick comum.

Funciona com o radio **sozinho** — nao precisa da aeronave, nem de hardware
extra, nem de root.

## Instalacao

```bash
git clone https://github.com/romulo-maciel/dji-phantom3-joystick.git
cd dji-phantom3-joystick
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Seu usuario precisa estar no grupo `dialout` para abrir a porta serial. Confira
com `id`; se nao estiver:

```bash
sudo usermod -aG dialout $USER
```

Depois saia e entre na sessao (ou reinicie) para o grupo valer.

O `config.json` que vem no repo esta calibrado para **um** radio especifico.
Cada aparelho tem batentes e centro um pouco diferentes, entao em um radio novo
rode a calibracao antes de jogar:

```bash
./.venv/bin/python dji_joystick.py --calibrar
```

## Uso

```bash
./.venv/bin/python dji_joystick.py
```

O radio precisa estar **ligado** (chave OFF/ON) e conectado pelo cabo micro-USB.
O gamepad aparece como `/dev/input/jsN`. Nao precisa de root.

Outras opcoes:

```bash
./.venv/bin/python dji_joystick.py --monitor    # com barras ao vivo
./.venv/bin/python dji_joystick.py --calibrar   # regrava os batentes
```

## Como funciona

O radio enumera como um CDC-ACM (`fff0:0008`, vira `/dev/ttyACM0`), mas **nao
transmite nada sozinho** — e preciso pedir. Foi isso que despistou o diagnostico
inicial: pedidos que ele nao reconhece sao ignorados em silencio, o que e
indistinguivel de hardware morto.

O pedido certo e um pacote DUML:

| campo | valor |
|---|---|
| cmd_set | `0x06` (REMOTE_CTRL) |
| cmd_id | `0x27` |
| destino | `0x0E` |
| remetente | `0x0A` |

A resposta tem 58 bytes e carrega os eixos como `u16` little-endian.
Antes do primeiro pedido vai um handshake proprietario com preambulo
`55 aa 55 aa` (constante `INIT` em `dji_rc.py`).

### Por que NAO mandamos o pacote da aeronave

O `pingData` do mDjiController sao dois pacotes DUML colados. O primeiro
(`PING_AERONAVE`) e endereçado ao destino `0x03`, a controladora de voo da
**aeronave**. Sem aeronave conectada, manda-lo dezenas de vezes por segundo faz
o LED de power do radio piscar verde/vermelho sem parar, como se estivesse
conectando e desconectando.

Nao precisamos dele: o radio responde as posicoes dos sticks so com o segundo
pacote. Por isso o padrao e `pingar_aeronave=False`, e o loop manda apenas
`PING_STICKS`. De quebra o ciclo fica mais curto (~49 Hz em vez de ~48).

Para reproduzir o comportamento original: `dji_rc.Radio(porta,
pingar_aeronave=True)`.

### Mapa dos eixos

Levantado empiricamente neste radio — **difere** do projeto mDjiController,
que mapeia o GL300C (Phantom 3 Professional/Advanced), um modelo diferente:

| offset | controle | sentido cru |
|---|---|---|
| 16 | stick direito, horizontal (roll) | direto |
| 18 | stick direito, vertical (pitch) | direto |
| 20 | stick esquerdo, vertical (throttle) | invertido |
| 22 | stick esquerdo, horizontal (yaw) | invertido |
| 24 | roda do gimbal (dial do ombro esquerdo) | direto |
| 26 | constante nos testes (nao identificado) | — |

O centro fisico dos sticks nao fica no meio exato entre os batentes, entao cada
metade e escalada separadamente para que o centro caia exatamente em zero.

### Chaves S1 e S2

Byte 28, dois campos de 2 bits. Levantado com `calibrar_chaves.py`; as cinco
leituras cruzadas sao consistentes entre si.

| chave | bits | valor 0 | valor 1 | valor 2 |
|---|---|---|---|---|
| S1 (modo de voo) | 4–5 | `A` | `P` | `F` |
| S2 (return to home) | 6–7 | meio | cima | baixo |

Exemplo: `S1=F, S2=cima` = bit 5 (32) + bit 6 (64) = 96.

As duas chaves tem **tres** posicoes. Cada uma e publicada de duas formas, para
servir aos dois estilos de mapeamento que os jogos usam:

| chave | eixo | botoes (por posicao) |
|---|---|---|
| S1 | `ABS_RUDDER` (−32767 / 0 / +32767) | `BTN_TRIGGER` / `BTN_THUMB` / `BTN_THUMB2` |
| S2 | `ABS_WHEEL` (−32767 / 0 / +32767) | `BTN_TOP` / `BTN_TOP2` / `BTN_PINKIE` |

Numeracao como os jogos veem em `/dev/input/jsN`:

| eixo js | controle | botao js | posicao |
|---|---|---|---|
| 0 | yaw | 0 | S1 = P |
| 1 | throttle | 1 | S1 = A |
| 2 | roll | 2 | S1 = F |
| 3 | pitch | 3 | S2 = cima |
| 4 | roda do gimbal | 4 | S2 = meio |
| 5 | S1 | 5 | S2 = baixo |
| 6 | S2 | | |

### Por que codigos de joystick, e nao de gamepad

A primeira versao usava `BTN_SOUTH`/`BTN_EAST`/`BTN_NORTH`/`BTN_WEST`/`BTN_TL`/
`BTN_TR` com `ABS_Z` e `ABS_RZ`. Esse conjunto e a assinatura de um **gamepad
padrao**: o SDL e a Gamepad API do navegador reconhecem o padrao e aplicam um
perfil de controle de videogame por cima. `ABS_Z`/`ABS_RZ` viram gatilhos
analogicos, os botoes sao reordenados para as posicoes A/B/X/Y e os que faltam
sao sintetizados — o FPV Labs chegou a mostrar 11 botoes onde so existem 6.

Um radio de voo nao e um gamepad. Agora os botoes ficam na faixa classica de
joystick (`BTN_TRIGGER`..`BTN_PINKIE`, contiguos, sem buracos) e as chaves usam
`ABS_RUDDER`/`ABS_WHEEL`. Assim nada remapeia, e o que o jogo le e exatamente o
que o radio mandou.

Ao trocar isso, **reinicie o driver e recarregue a pagina do jogo**: navegadores
so redetectam um joystick quando ele re-registra e recebe um evento.

O offset 32 tambem variou durante a calibracao (192, 194, 195, 196, 197), mas
cresce com o tempo e nao com as chaves: e um contador, nao estado. Ignorado.

## Arquivos

| arquivo | papel |
|---|---|
| `duml.py` | protocolo DUML: CRC8/CRC16, montagem e parser de pacotes |
| `dji_rc.py` | conexao com o radio, handshake e leitura dos pacotes |
| `dji_joystick.py` | driver principal: le o radio, publica o gamepad via uinput |
| `config.json` | mapa dos eixos, inversoes, calibracao |
| `discover.py` | ferramenta de mapeamento: mostra qual byte responde a qual controle |
| `calibrar_chaves.py` | calibracao guiada das chaves S1/S2, uma posicao por vez |
| `watch.py` | vigia de conexao/desconexao USB, util para diagnostico |
| `mdji_test.py` | teste cru da sequencia de handshake |
| `rawusb.py` | leitura direta dos endpoints USB (precisa de root) |

O `duml.py` foi validado reconstruindo byte a byte os pacotes de uma
implementacao de referencia que funciona.

## Se algo nao funcionar

**`nao consegui abrir /dev/ttyACM0`** — o radio esta desligado, o cabo caiu, ou
outro script (`discover.py`, `watch.py`) esta segurando a porta. Feche os outros.

**Eixo no sentido errado no jogo** — troque `inverter` daquele eixo em
`config.json` e reinicie. A convencao varia de jogo para jogo.

**Sticks nao chegam ao maximo** — rode `--calibrar`.

**Permissao negada na porta** — seu usuario precisa estar no grupo `dialout`
(`id` mostra os grupos).

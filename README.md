# Tecla Fantasma

A tecla de interrogação do meu teclado morreu. Em vez de trocar o teclado,
resolvi construir uma.

No layout ABNT2 o `?` divide a mesma tecla física com `/` e `°`. Aqui só o `?`
importa — a barra ainda dá pra pegar no teclado numérico.

## Como funciona

Qualquer gatilho termina no mesmo lugar: um processo no PC injeta o caractere
na janela em foco. A injeção usa `SendInput` com `KEYEVENTF_UNICODE`, ou seja,
**não simula tecla física** — entrega o caractere direto pro aplicativo. Isso
faz o layout do teclado ser irrelevante.

```
   Ctrl+Alt+Q ────────┐
                      │
   botão no Arduino ──┼──▶  tecla_fantasma.py  ──▶  SendInput  ──▶  janela
   (serial)           │
                      │
   HTTP /k/... ───────┘
```

Os três gatilhos são intercambiáveis. Adicionar um novo (voz, gesto, pedal)
é escrever só o front-end — o injetor não muda.

## Rodando

```
pip install pyserial          # opcional, só pro botão físico
python tecla_fantasma.py
```

Sem hardware nenhum já funciona: `Ctrl+Alt+Q` digita `?`.

## O botão físico

Arduino Nano (serve igual em Uno e Mega). Sem resistor externo:

```
   D2  ────[ botão ]──── GND
```

O `INPUT_PULLUP` interno segura o pino em HIGH; apertar puxa pra LOW.
Debounce de 40 ms no firmware — sem isso o tremor do contato mecânico
transforma um aperto em vários `?`.

Pra gravar:

```powershell
winget install ArduinoSA.CLI          # uma vez
arduino-cli core install arduino:avr  # uma vez, ~200 MB

.\gravar.ps1                          # Nano, detecta a porta e grava
.\gravar.ps1 -Placa uno               # ou uno / mega
.\gravar.ps1 -Porta COM7              # força uma porta
.\gravar.ps1 -SoCompilar              # só compila, sem placa plugada
```

Rode do **PowerShell**, não do `cmd` — o `cmd` não executa `.ps1`, ele abre o
arquivo no editor.

Depois é só rodar o daemon — ele acha a porta COM sozinho pelo VID do chip
USB-serial.

O `gravar.ps1` cobre duas pegadinhas que custam meia hora de debug cada:

- **Bootloader antigo.** Quase todo Nano clone fala 57600 baud, não 115200.
  Com o FQBN padrão o upload morre em `stk500_recv(): programmer is not
  responding`. O script tenta os dois, então você não precisa saber qual tem.
- **Porta ocupada.** Se o daemon estiver rodando ele segura a COM aberta e o
  `avrdude` não consegue gravar. O script detecta e avisa antes de tentar.

Tamanho do firmware: 1960 bytes de flash (6%), 208 bytes de RAM (10%).

### Por que não um teclado USB de verdade

Nano, Uno e Mega não têm USB HID nativo — o USB deles é uma ponte serial
(CH340 no Nano, ATmega16u2 no Uno/Mega). Eles não conseguem se passar por
teclado, por isso existe o daemon no PC.

Dá pra reflashar o 16u2 do Uno/Mega com firmware HID (HoodLoader2), mas você
perde a programação normal até reverter. Pra um teclado de verdade, sem
software nenhum no PC e funcionando até na BIOS, o chip certo é um
ATmega32u4 (Pro Micro / Leonardo) ou um ESP32-S3.

## Linux (Ubuntu)

> Verificado em Ubuntu 24.04.4, GNOME 46 no Wayland, teclado ABNT2 (layout
> `br`), com Uno clone (CH340). O botão físico funciona ponta a ponta.

No Windows o `SendInput` entrega o **caractere** e o layout não importa. No
Linux não existe equivalente: no Wayland, injetar em outra janela é
justamente o que o protocolo impede, e a única saída é `/dev/uinput` — um
teclado virtual no nível do kernel, que fala **keycode**. O compositor aplica
o layout depois. Ou seja, o layout volta a importar.

O backend é `InjetorUinput`, que abre `/dev/uinput` direto via `python3-evdev`.
Sem daemon auxiliar e sem um subprocess por tecla.

```bash
sudo apt install python3-evdev libxkbcommon-tools python3-serial

# acesso ao uinput (injeção) e à serial (placa)
sudo groupadd -f uinput
sudo usermod -aG uinput,dialout $USER
echo 'KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/80-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

**Faça logout/login** — grupo novo não vale na sessão atual, e abrir outro
terminal não resolve. Pra testar sem deslogar: `sg uinput -c 'python3 injetor.py'`.

### Por que não `ydotool`

O README antigo mandava usar `ydotool key` com keycode cru. Não dá, pelo menos
não com o pacote do Ubuntu:

- O 24.04 empacota a **0.1.8**, que espera **nome** de tecla (`shift+ro`). A
  sintaxe `keycode:1` / `keycode:0` só existe da **1.0** pra frente.
- O pacote não inclui o `ydotoold` — só `/usr/bin/ydotool`. Não há o que
  habilitar com `systemctl --user enable ydotoold`.

Sem o daemon, cada invocação cria um uinput novo e perde as primeiras teclas.
Compilar a 1.0.4 do fonte resolveria; usar `/dev/uinput` direto resolve com
menos peças. O `InjetorYdotool` continua no código como plano B pra quem já
tem a 1.0+ instalada.

### Confira o mapa de teclas antes de confiar

```bash
python3 injetor.py
```

```
backend: linux/uinput
layout ativo: ('br', None)
mapa de teclas descoberto:
  '/' -> keycode 89, mods nenhum
  '?' -> keycode 89, mods [42]
  '°' -> keycode 18, mods [100]
```

Se o `?` vier com `keycode 53`, ele resolveu pelo layout US e vai digitar
errado — a detecção precisa de ajuste.

Duas coisas que essa detecção esconde, e que custaram debug:

- **O `xkbcli how-to-type` quer codepoint, não caractere.** Passar `?` faz ele
  imprimir o usage e sair diferente de zero; o código caía calado no mapa fixo
  de ABNT2. Ficava *certo por coincidência* — a detecção de layout nunca rodava.
  Agora manda `0x3F`.
- **Ele responde com várias linhas.** No ABNT2 o `?` sai em `Shift+AB11` e
  também em `AltGr+W`. Pegar a primeira linha daria AltGr+W. E linhas com
  `Lock` só valem com Caps Lock ligado — o daemon não sabe o estado do Caps,
  então são descartadas. O código junta os candidatos e escolhe o de menos
  modificador, desempatando a favor do Shift.

### brltty: não precisa remover

Conselho comum na internet, e o README antigo repetia: remover o `brltty`
porque ele sequestra CH340. No Ubuntu 24.04 (brltty 6.6) a regra é estreita:

```
ENV{PRODUCT}=="1a86/7523/*", ATTRS{idVendor}=="1a40", ATTRS{idProduct}=="0101", ...
```

Só dispara se o CH340 estiver atrás daquele hub USB específico que os displays
braille usam. Placa Arduino comum não é afetada — confira com
`ls -l /dev/ttyUSB0` alguns segundos depois de plugar antes de desinstalar
suporte a braille da máquina.

### Autostart

```ini
# ~/.config/systemd/user/tecla-fantasma.service
[Unit]
Description=Tecla Fantasma
After=graphical-session.target
PartOf=graphical-session.target

[Service]
WorkingDirectory=%h/Documentos/tecla-fantasma
ExecStart=/usr/bin/python3 tecla_fantasma.py
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
```

```bash
systemctl --user daemon-reload && systemctl --user enable --now tecla-fantasma
journalctl --user -u tecla-fantasma -f
```

### Atalho global no Wayland: não resolvido

Não existe `RegisterHotKey` aqui, e nenhum app captura tecla global — de
propósito. O caminho óbvio é cadastrar um atalho customizado em
**Configurações → Teclado → Atalhos personalizados** chamando

```
curl -s http://127.0.0.1:8127/k/interrogacao
```

**Isso não funcionou nesta máquina.** O atalho dispara e o daemon injeta — o
log mostra `http -> '?'` — mas nada aparece na tela. O mesmo endpoint chamado
pelo botão físico funciona, então a injeção está boa; algo entre o `uinput` e
a janela engole o caractere quando o gatilho é uma tecla.

Hipótese não confirmada: com Ctrl+Alt segurados, o compositor lê o keycode
injetado como `Ctrl+Alt+Shift+89`, que não é `?`. Tentei zerar os
modificadores antes de injetar — pressiona+solta no teclado virtual, porque
`solta` sozinho é filtrado pelo `input_handle_event()` do kernel quando o
dispositivo nunca pressionou a tecla — e **não resolveu**. Pode ser o grab que
o GNOME mantém enquanto o atalho está ativo.

Fica em aberto. Não é bloqueante: o botão físico é o uso diário.

## HTTP

Escuta em `127.0.0.1:8127` por padrão.

| Rota | O que faz |
|---|---|
| `GET /k/<apelido>` | digita um caractere nomeado (`interrogacao`, `barra`, `graus`) |
| `GET /t?texto=...` | digita texto arbitrário (url-encoded) |

⚠️ `127.0.0.1` aceita só conexões da própria máquina. Pra um dispositivo da
rede alcançar (NodeMCU), troque `HOST` pra `0.0.0.0` — e nesse instante
**qualquer coisa no seu WiFi pode digitar na sua máquina**. Se fizer isso,
defina `TOKEN`. É um token em HTTP puro: serve contra acidente, não contra
alguém determinado dentro da rede.

## Roadmap

- [x] Injetor + atalho global (o atalho só no Windows — veja a seção Linux)
- [x] Botão físico via serial (Arduino Nano/Uno)
- [ ] Alexa via NodeMCU — o ESP8266 se anuncia como lâmpada Hue (`Espalexa`)
      e chama o endpoint HTTP. Roundtrip pela nuvem: 2–4 s. Boa demo,
      ruim pra escrever de verdade.
- [ ] Gesto pela webcam — por último. Falso positivo em gesto é fatal: você
      gesticula falando ao telefone e aparecem `?????` no documento.

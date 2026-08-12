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

- [x] Injetor + atalho global
- [x] Botão físico via serial (Arduino Nano)
- [ ] Alexa via NodeMCU — o ESP8266 se anuncia como lâmpada Hue (`Espalexa`)
      e chama o endpoint HTTP. Roundtrip pela nuvem: 2–4 s. Boa demo,
      ruim pra escrever de verdade.
- [ ] Gesto pela webcam — por último. Falso positivo em gesto é fatal: você
      gesticula falando ao telefone e aparecem `?????` no documento.

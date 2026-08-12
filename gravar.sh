#!/usr/bin/env bash
#
# Compila e grava o firmware nas placas. Equivalente Linux do gravar.ps1.
#
#     ./gravar.sh                          # nano, detecta a porta
#     ./gravar.sh -p uno -m                # uno, abre o serial depois
#     ./gravar.sh -p nodemcu               # firmware da Alexa
#     ./gravar.sh -p nodemcu -s scan_wifi -m
#     ./gravar.sh -P /dev/ttyUSB1          # forca a porta
#     ./gravar.sh -c                       # so compila, sem placa plugada
#
# Duas coisas que ele resolve sozinho e custam debug se voce nao souber:
#
#   - Nano clone quase sempre tem bootloader antigo (57600 baud). Com o FQBN
#     padrao o avrdude morre em "stk500_recv(): programmer is not responding".
#     O script tenta os dois.
#   - O daemon segura /dev/ttyUSB* aberto e o upload falha sem dizer por que.
#     Se o servico do systemd estiver de pe, o script para, grava e sobe de
#     volta.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PLACA="nano"
SKETCH_ARG=""
PORTA=""
BAUD=""
MONITOR=0
SO_COMPILAR=0

# Imprime o cabecalho ate a primeira linha que nao e comentario, em vez de um
# intervalo fixo de linhas que sai do lugar assim que alguem edita o cabecalho.
uso() {
  awk 'NR==1 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "${BASH_SOURCE[0]}"
  exit "${1:-0}"
}
erro() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--placa)       PLACA="${2:-}"; shift 2 ;;
    -s|--sketch)      SKETCH_ARG="${2:-}"; shift 2 ;;
    -P|--porta)       PORTA="${2:-}"; shift 2 ;;
    -b|--baud)        BAUD="${2:-}"; shift 2 ;;
    -m|--monitor)     MONITOR=1; shift ;;
    -c|--so-compilar) SO_COMPILAR=1; shift ;;
    -h|--help)        uso 0 ;;
    *) echo "opcao desconhecida: $1" >&2; uso 1 ;;
  esac
done

case "$PLACA" in
  nano)    FQBNS=("arduino:avr:nano" "arduino:avr:nano:cpu=atmega328old")
           SKETCH_PADRAO="botao_interrogacao"; BAUD_PADRAO=9600 ;;
  uno)     FQBNS=("arduino:avr:uno")
           SKETCH_PADRAO="botao_interrogacao"; BAUD_PADRAO=9600 ;;
  mega)    FQBNS=("arduino:avr:mega:cpu=atmega2560")
           SKETCH_PADRAO="botao_interrogacao"; BAUD_PADRAO=9600 ;;
  nodemcu) FQBNS=("esp8266:esp8266:nodemcuv2")
           SKETCH_PADRAO="alexa_interrogacao"; BAUD_PADRAO=115200 ;;
  *) erro "placa desconhecida: '$PLACA' (use nano, uno, mega ou nodemcu)" ;;
esac

SKETCH="$REPO/${SKETCH_ARG:-$SKETCH_PADRAO}"
[ -d "$SKETCH" ] || erro "sketch nao encontrado: $SKETCH"
[ -n "$BAUD" ] || BAUD="$BAUD_PADRAO"

# ------------------------------------------------------------------ arduino-cli

CLI=""
for c in arduino-cli "$HOME/.local/bin/arduino-cli" /usr/local/bin/arduino-cli; do
  if command -v "$c" >/dev/null 2>&1; then CLI="$(command -v "$c")"; break; fi
done
[ -n "$CLI" ] || erro "arduino-cli nao encontrado. Instale com:
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \\
    | BINDIR=\$HOME/.local/bin sh
  (e garanta que \$HOME/.local/bin esta no PATH)"

echo "arduino-cli: $CLI"

# O core so precisa ser instalado uma vez, mas checar e barato e a mensagem do
# compilador quando falta core nao diz o que fazer.
NUCLEO="arduino:avr"
[ "$PLACA" = "nodemcu" ] && NUCLEO="esp8266:esp8266"
if ! "$CLI" core list 2>/dev/null | grep -q "^${NUCLEO} "; then
  echo "core $NUCLEO nao instalado, instalando..."
  if [ "$NUCLEO" = "esp8266:esp8266" ]; then
    "$CLI" config add board_manager.additional_urls \
      https://arduino.esp8266.com/stable/package_esp8266com_index.json || true
    "$CLI" core update-index
  fi
  "$CLI" core install "$NUCLEO"
fi

if [ "$PLACA" = "nodemcu" ] && ! "$CLI" lib list 2>/dev/null | grep -qi espalexa; then
  echo "instalando a biblioteca Espalexa..."
  "$CLI" lib install Espalexa
fi

# --------------------------------------------------------------------- compilar

# O config.h nao esta no repo (leva senha de wifi e token). Sem ele o gcc
# reclama de "config.h: No such file or directory", que nao diz o que fazer.
if [ -f "$SKETCH/config.h.exemplo" ] && [ ! -f "$SKETCH/config.h" ]; then
  erro "falta o config.h em $SKETCH
  Copie o exemplo e preencha wifi, IPs dos PCs e token:
    cp '$SKETCH/config.h.exemplo' '$SKETCH/config.h'"
fi

echo
echo "Compilando para $PLACA..."
"$CLI" compile --fqbn "${FQBNS[0]}" "$SKETCH"
printf '\033[32mcompilou ok\033[0m\n'

[ "$SO_COMPILAR" -eq 1 ] && { echo; echo "-c: parando aqui."; exit 0; }

# ---------------------------------------------------------------------- porta

achar_porta() {
  local json
  json="$("$CLI" board list --format json 2>/dev/null || true)"
  [ -n "$json" ] || return 1
  printf '%s' "$json" | python3 -c '
import json, sys
# Mesmos VIDs que o daemon usa pro autodetect
VIDS = {"0x1a86", "0x0403", "0x2341", "0x2a03", "0x1b4f", "0x10c4"}
try:
    portas = json.load(sys.stdin).get("detected_ports") or []
except Exception:
    sys.exit(1)
# 1a escolha: placa que o proprio arduino-cli reconheceu
for p in portas:
    if p.get("matching_boards"):
        print(p["port"]["address"]); sys.exit(0)
# 2a: clone que o cli nao identifica, mas o VID entrega
for p in portas:
    port = p.get("port") or {}
    vid = ((port.get("properties") or {}).get("vid") or "").lower()
    if port.get("protocol") == "serial" and vid in VIDS:
        print(port["address"]); sys.exit(0)
sys.exit(1)
'
}

if [ -z "$PORTA" ]; then
  echo
  echo "Procurando a placa..."
  PORTA="$(achar_porta || true)"
fi
[ -n "$PORTA" ] || erro "nenhuma placa encontrada. Pluga a placa ($PLACA) no USB,
  ou passa -P /dev/ttyUSB0. Se ela JA esta plugada:
    ls -l /dev/ttyUSB* /dev/ttyACM*   nada aqui = o kernel nao viu a placa
    dmesg | tail -20                  mostra o que aconteceu ao plugar"
echo "    porta: $PORTA"

if [ ! -w "$PORTA" ]; then
  erro "sem permissao de escrita em $PORTA.
  Voce esta no grupo dialout? Rode ./instalar-linux.sh e faca logout/login.
  Pra testar sem deslogar:  sg dialout -c './gravar.sh -p $PLACA'"
fi

# ------------------------------------------------------- liberar a porta

# O daemon abre a serial e segura; o avrdude precisa dela livre.
PAREI_SERVICO=0
if systemctl --user is-active --quiet tecla-fantasma 2>/dev/null; then
  echo "    parando o servico tecla-fantasma (ele segura a porta)"
  systemctl --user stop tecla-fantasma
  PAREI_SERVICO=1
elif pgrep -f "tecla_fantasma.py" >/dev/null 2>&1; then
  echo "    [!] tecla_fantasma.py esta rodando fora do systemd (PID $(pgrep -f tecla_fantasma.py | tr '\n' ' '))."
  echo "        Ele segura $PORTA e o upload vai falhar. Feche antes."
fi

restaurar() {
  if [ "$PAREI_SERVICO" -eq 1 ]; then
    echo "religando o servico tecla-fantasma"
    systemctl --user start tecla-fantasma || true
    PAREI_SERVICO=0
  fi
}
trap restaurar EXIT

# --------------------------------------------------------------------- gravar

for fqbn in "${FQBNS[@]}"; do
  echo
  echo "Gravando em $PORTA  [$fqbn]"
  if "$CLI" upload -p "$PORTA" --fqbn "$fqbn" "$SKETCH"; then
    printf '\n\033[32mgravado com sucesso [%s]\033[0m\n' "$fqbn"
    if [ "$MONITOR" -eq 1 ]; then
      restaurar
      trap - EXIT
      echo "abrindo o serial em $PORTA a $BAUD (Ctrl+C pra sair)"
      # A placa acabou de resetar pelo upload; sem esse respiro o monitor abre
      # no meio do boot e as primeiras linhas saem truncadas.
      sleep 0.8
      exec "$CLI" monitor -p "$PORTA" -c "baudrate=$BAUD"
    fi
    echo "Pra ver a saida da placa:  ./gravar.sh -p $PLACA -m"
    exit 0
  fi
  echo "  falhou com $fqbn"
done

erro "nao gravou em $PORTA. Confira se a porta esta livre e se o cabo transfere dados."

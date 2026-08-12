#!/usr/bin/env bash
#
# Instala as dependencias e permissoes do tecla-fantasma no Linux.
#
#     ./instalar-linux.sh                 # deps + permissoes + autostart
#     ./instalar-linux.sh --sem-servico   # sem o autostart do systemd
#
# Idempotente: rodar duas vezes nao quebra nada. Pede sudo quando precisa.
#
# O que ele NAO faz: gravar o firmware na placa (veja gravar.ps1) e nada no
# Windows, que nao precisa de permissao nenhuma - lá o SendInput entrega o
# caractere direto.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICO=1
[ "${1:-}" = "--sem-servico" ] && SERVICO=0

# Rodar como root faria $USER virar root: os grupos iriam pro usuario errado e
# o service acabaria em /root. O script chama sudo sozinho onde precisa.
if [ "$(id -u)" -eq 0 ]; then
  echo "ERRO: rode como seu usuario normal, sem sudo." >&2
  echo "      O script pede sudo nos pontos que precisam." >&2
  exit 1
fi

if ! command -v apt-get >/dev/null; then
  echo "ERRO: este script assume apt (Debian/Ubuntu)." >&2
  echo "      Em outra distro instale o equivalente a:" >&2
  echo "      python3-evdev libxkbcommon-tools python3-serial" >&2
  echo "      e siga a secao Linux do README pro resto." >&2
  exit 1
fi

echo "==> 1/5  pacotes"
# python3-evdev  = o backend de injecao (obrigatorio)
# libxkbcommon-tools = xkbcli, descobre o keycode no layout ATIVO (recomendado:
#                      sem ele o codigo cai num mapa fixo de ABNT2)
# python3-serial = pyserial, so pro botao fisico
sudo apt-get install -y python3-evdev libxkbcommon-tools python3-serial

echo
echo "==> 2/5  modulo uinput"
# Em muitos kernels (incluindo o do Ubuntu) uinput e builtin e nao ha nada a
# fazer. Onde for modulo, garante o carregamento no boot - senao /dev/uinput
# some no proximo reboot e a injecao para.
if [ "$(modinfo -F filename uinput 2>/dev/null || true)" = "(builtin)" ]; then
  echo "    uinput e builtin no kernel, nada a carregar"
else
  sudo modprobe uinput || true
  echo uinput | sudo tee /etc/modules-load.d/uinput.conf >/dev/null
  echo "    uinput e modulo: registrado em /etc/modules-load.d/uinput.conf"
fi

echo
echo "==> 3/5  grupos"
# uinput  -> escrever em /dev/uinput (injetar)
# dialout -> abrir /dev/ttyUSB* ou /dev/ttyACM* (ler a placa)
sudo groupadd -f uinput
sudo usermod -aG uinput,dialout "$USER"
echo "    $USER agora nos grupos: uinput, dialout"

echo
echo "==> 4/5  regra de udev pro /dev/uinput"
# Sem isso o device nasce root:root 0600 a cada boot e so root injeta.
echo 'KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/80-uinput.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "    $(ls -l /dev/uinput)"

echo
echo "==> 5/5  autostart"
if [ "$SERVICO" -eq 1 ]; then
  UNIT="$HOME/.config/systemd/user/tecla-fantasma.service"
  mkdir -p "$(dirname "$UNIT")"
  # WorkingDirectory sai do lugar onde ESTE script esta, entao o unit funciona
  # em qualquer caminho de clone.
  cat > "$UNIT" <<UNITEOF
[Unit]
Description=Tecla Fantasma
After=graphical-session.target
PartOf=graphical-session.target

[Service]
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 tecla_fantasma.py
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
UNITEOF
  systemctl --user daemon-reload
  systemctl --user enable tecla-fantasma.service >/dev/null
  echo "    habilitado: $UNIT"
  echo "    (sobe sozinho no proximo login; 'systemctl --user disable"
  echo "     tecla-fantasma' desfaz)"
else
  echo "    pulado (--sem-servico)"
fi

echo
echo "-------------------------------------------------------------"
echo "Instalado. FALTA UM LOGOUT/LOGIN."
echo
echo "Grupo novo nao vale na sessao atual, e abrir outro terminal nao"
echo "resolve. Depois do login o daemon sobe sozinho; confira com:"
echo
echo "    systemctl --user status tecla-fantasma"
echo
echo "Pra testar agora, sem deslogar:"
echo
echo "    sg uinput -c 'python3 $REPO/injetor.py'"
echo
echo "Confira o mapa que ele imprime ANTES de confiar - e onde se"
echo "descobre se o layout foi detectado certo. Num teclado ABNT2 o"
echo "'?' tem que sair em 'keycode 89, mods [42]'. Se vier 53, ele"
echo "resolveu pelo layout US e vai digitar errado."
echo "-------------------------------------------------------------"

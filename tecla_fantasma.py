"""
Tecla Fantasma - injeta caracteres perdidos de um teclado com defeito.

Tres formas de acionar o mesmo injetor:
  1) Atalho de teclado global (funciona sem hardware nenhum)
  2) Serial - botao fisico no Arduino Nano/Uno/Mega  <- o uso diario
  3) HTTP em localhost - pro NodeMCU / webcam / Alexa

Windows e Linux. Python 3.8+. pyserial e opcional (so pro item 2).
    python tecla_fantasma.py

A injecao em si mora no injetor.py, um backend por plataforma. O atalho
global (item 1) e so Windows: no Wayland nenhum app captura tecla global, e
la o caminho e cadastrar um atalho do GNOME chamando o endpoint HTTP - veja
o README.
"""

import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from injetor import criar_injetor

WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------- config

# Atalhos globais -> caractere injetado.
# Ctrl+Alt+Q = ?   Ctrl+Alt+W = /   Ctrl+Alt+E = graus
ATALHOS = {
    ("ctrl+alt", "Q"): "?",
    ("ctrl+alt", "W"): "/",
    ("ctrl+alt", "E"): "°",
}

# Apelidos aceitos pelo HTTP: GET /k/<apelido>
APELIDOS = {
    "interrogacao": "?",
    "barra": "/",
    "graus": "°",
}

# Veja NOTA DE REDE no fim do arquivo antes de abrir pra LAN.
#
# Vem do ambiente pra o token nao acabar num commit - este repo e publico:
#   Windows    setx TECLA_FANTASMA_TOKEN "..."   (abra um terminal novo depois)
#   Linux      export TECLA_FANTASMA_TOKEN=...   (no ~/.profile pro systemd ver)
HOST = os.environ.get("TECLA_FANTASMA_HOST", "127.0.0.1")
PORTA = int(os.environ.get("TECLA_FANTASMA_PORTA", "8127"))
TOKEN = os.environ.get("TECLA_FANTASMA_TOKEN", "")

SERIAL_PORTA = None   # None = autodetecta. Ou fixe: "COM3" / "/dev/ttyUSB0"
SERIAL_BAUD = 9600

# VIDs de USB-serial comuns em placas Arduino, pro autodetect
_VIDS_ARDUINO = {
    0x1A86,  # CH340/CH341 - maioria dos Nano/Uno clone
    0x0403,  # FTDI - Nano mais antigo
    0x2341,  # Arduino oficial (Uno, Mega)
    0x2A03,  # Arduino.org
    0x1B4F,  # SparkFun
    0x10C4,  # CP210x - varios NodeMCU
}

# ------------------------------------------------------------------ injecao

_INJETOR = None


def digitar(texto):
    """Injeta texto na janela em foco, pelo backend da plataforma."""
    return _INJETOR.digitar(texto)


# --------------------------------------------------- atalhos globais (Windows)

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 1, 2, 4, 8, 0x4000
WM_HOTKEY = 0x0312

_MODS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL,
         "shift": MOD_SHIFT, "win": MOD_WIN}


def _parse_mods(spec):
    valor = MOD_NOREPEAT
    for parte in spec.lower().split("+"):
        parte = parte.strip()
        if parte not in _MODS:
            raise ValueError("modificador desconhecido: %r" % parte)
        valor |= _MODS[parte]
    return valor


def loop_atalhos():
    """Registra os hotkeys e bombeia mensagens. Bloqueia a thread principal.

    So Windows: RegisterHotKey e Win32, e no Wayland nao existe equivalente
    de proposito - captura global de tecla e justamente o que o protocolo
    impede. No Linux o atalho vai pelo GNOME chamando o HTTP (veja README).
    """
    # ctypes.wintypes nem importa fora do Windows, por isso o import e aqui
    import ctypes
    import ctypes.wintypes as w
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    registrados = {}
    for i, ((mods, tecla), texto) in enumerate(ATALHOS.items(), start=1):
        vk = ord(tecla.upper())
        if not user32.RegisterHotKey(None, i, _parse_mods(mods), vk):
            print("  [!] falhou registrar %s+%s (ja em uso por outro app?)"
                  % (mods, tecla))
            continue
        registrados[i] = texto
        print("  %s+%s  ->  %s" % (mods.upper(), tecla, texto))

    if not registrados:
        print("  [!] nenhum atalho registrado - so o HTTP vai funcionar")

    msg = w.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                texto = registrados.get(msg.wParam)
                if texto:
                    digitar(texto)
    finally:
        for i in registrados:
            user32.UnregisterHotKey(None, i)


# ------------------------------------------------------------------- HTTP

PAGINA = """<!doctype html><meta charset=utf-8>
<title>Tecla Fantasma</title>
<style>body{font:16px system-ui;max-width:34em;margin:3em auto;padding:0 1em}
code{background:#eee;padding:.15em .4em;border-radius:3px}</style>
<h1>Tecla Fantasma</h1>
<p>Ativo. Endpoints:</p>
<ul>
<li><code>GET /k/&lt;apelido&gt;</code> &mdash; %s</li>
<li><code>GET /t?texto=&lt;url-encoded&gt;</code> &mdash; qualquer texto</li>
</ul>
<p>Exemplo pro NodeMCU: <code>GET /k/interrogacao</code></p>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)

        if TOKEN and query.get("token", [""])[0] != TOKEN:
            return self._responder(403, "token invalido")

        if url.path in ("/", "/index.html"):
            return self._responder(
                200, PAGINA % ", ".join(sorted(APELIDOS)), "text/html")

        if url.path.startswith("/k/"):
            apelido = urllib.parse.unquote(url.path[3:])
            texto = APELIDOS.get(apelido)
            if texto is None:
                return self._responder(404, "apelido desconhecido: " + apelido)
        elif url.path == "/t":
            texto = query.get("texto", [""])[0]
            if not texto:
                return self._responder(400, "faltou ?texto=")
        else:
            return self._responder(404, "rota desconhecida")

        digitar(texto)
        print("  http -> %r" % texto)
        return self._responder(200, "ok")

    def _responder(self, codigo, corpo, tipo="text/plain"):
        dados = corpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args):
        pass  # o print acima ja diz o que interessa


# ------------------------------------------------------------------ serial

def _achar_porta():
    """Primeira porta COM que parece uma placa Arduino."""
    from serial.tools import list_ports
    candidatas = [p for p in list_ports.comports() if p.vid in _VIDS_ARDUINO]
    return candidatas[0] if candidatas else None


def loop_serial():
    """Le apelidos linha a linha da placa e injeta. Reconecta sozinho.

    Roda numa thread separada; se pyserial nao estiver instalado ou nenhuma
    placa aparecer, so fica quieto tentando - os outros gatilhos continuam.
    """
    try:
        import serial
    except ImportError:
        print("  serial: pyserial nao instalado (pip install pyserial)")
        return

    avisou = False
    while True:
        porta = SERIAL_PORTA
        if porta is None:
            achada = _achar_porta()
            porta = achada.device if achada else None

        if porta is None:
            if not avisou:
                print("  serial: nenhuma placa detectada, aguardando...")
                avisou = True
            time.sleep(2.0)
            continue

        try:
            # Abrir a porta puxa DTR e reseta Nano/Uno: a placa reinicia e
            # cospe lixo do bootloader. Por isso o sleep + flush antes de ler.
            with serial.Serial(porta, SERIAL_BAUD, timeout=1.0) as ser:
                time.sleep(2.0)
                ser.reset_input_buffer()
                print("  serial: conectado em %s" % porta)
                avisou = False

                while True:
                    linha = ser.readline()
                    if not linha:
                        continue  # so timeout, a placa esta viva
                    apelido = linha.decode("utf-8", "replace").strip()
                    if not apelido:
                        continue
                    texto = APELIDOS.get(apelido)
                    if texto is None:
                        print("  serial: apelido desconhecido %r" % apelido)
                        continue
                    digitar(texto)
                    print("  serial -> %r" % texto)

        except Exception as e:
            if not avisou:
                print("  serial: %s (%s) - tentando de novo" % (e, porta))
                avisou = True
            time.sleep(2.0)


# -------------------------------------------------------------------- main

def main():
    try:  # console do Windows nem sempre e utf-8; nao vale travar por causa de print
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    global _INJETOR
    print("Tecla Fantasma")

    _INJETOR = criar_injetor()
    print("injetor: %s" % _INJETOR.nome)

    if HOST not in ("127.0.0.1", "localhost") and not TOKEN:
        print("\n  [!] ESCUTANDO EM %s SEM TOKEN." % HOST)
        print("      Qualquer dispositivo da sua rede pode digitar nesta")
        print("      maquina. Defina TECLA_FANTASMA_TOKEN.")

    servidor = HTTPServer((HOST, PORTA), Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    threading.Thread(target=loop_serial, daemon=True).start()
    print("\nHTTP: http://%s:%d/  (Ctrl+C pra sair)" % (HOST, PORTA))

    try:
        if WINDOWS:
            print("\nAtalhos:")
            loop_atalhos()
        else:
            print("\nAtalho global: cadastre no GNOME chamando"
                  " curl -s http://%s:%d/k/interrogacao\n" % (HOST, PORTA))
            threading.Event().wait()   # so espera; serial e HTTP ja rodam
    except KeyboardInterrupt:
        pass
    finally:
        servidor.shutdown()
        print("\ntchau")


if __name__ == "__main__":
    main()


# NOTA DE REDE
# --------------------------------------------------------------------------
# HOST = "127.0.0.1" aceita so conexoes da propria maquina. O NodeMCU esta na
# LAN, entao pra ele alcancar voce troca pra "0.0.0.0" - e nesse instante
# qualquer dispositivo do wifi passa a poder digitar na sua maquina. Se fizer
# isso, defina TOKEN com uma string aleatoria e mande ?token=... nas requisicoes.
# E um token em HTTP puro, nao criptografia; serve contra acidente, nao contra
# alguem determinado dentro da sua rede.

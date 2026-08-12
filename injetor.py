"""
Injecao de caractere, com um backend por plataforma.

    from injetor import criar_injetor
    inj = criar_injetor()
    inj.digitar("?")

Windows e Linux resolvem isso de formas fundamentalmente diferentes:

  Windows  SendInput com KEYEVENTF_UNICODE entrega o CARACTERE direto pro app
           em foco. Nao existe tecla fisica envolvida, entao o layout do
           teclado e irrelevante.

  Linux    Nao existe equivalente. No Wayland nenhum processo comum consegue
           injetar em outra janela - e o ponto de seguranca do protocolo. A
           unica saida e /dev/uinput, um teclado virtual no nivel do kernel,
           que fala KEYCODE. O compositor e quem aplica o layout depois. Ou
           seja: pra sair "?" a gente precisa saber qual tecla, no layout
           DESTE teclado, produz "?" - problema que no Windows nao existia.
"""

import re
import shutil
import subprocess
import sys

# Keycodes evdev usados aqui (/usr/include/linux/input-event-codes.h)
KEY_LEFTSHIFT = 42
KEY_RIGHTALT = 100   # AltGr

# Fallback pra teclado ABNT2 quando o xkbcli nao estiver disponivel.
#
# No ABNT2 o "/ ? °" fica numa tecla EXTRA, entre o ponto-e-virgula e o shift
# direito, que o kernel chama de KEY_RO (89) - nao e a mesma tecla do "/" de
# um teclado US. Por isso hardcodar keycode de layout US daria caractere
# errado aqui.
#
#   caractere -> (keycode, [modificadores])
_ABNT2 = {
    "?": (89, [KEY_LEFTSHIFT]),
    "/": (89, []),
    "°": (89, [KEY_RIGHTALT]),
}


class ErroInjecao(Exception):
    pass


# ------------------------------------------------------------------ Windows

class InjetorWindows:
    """SendInput + KEYEVENTF_UNICODE. Independe do layout."""

    nome = "windows/SendInput"

    def __init__(self):
        import ctypes
        import ctypes.wintypes as w

        self._ctypes = ctypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                        ("dwFlags", w.DWORD), ("time", w.DWORD),
                        ("dwExtraInfo", w.WPARAM)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", w.WORD), ("wScan", w.WORD),
                        ("dwFlags", w.DWORD), ("time", w.DWORD),
                        ("dwExtraInfo", w.WPARAM)]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD),
                        ("wParamH", w.WORD)]

        class _UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT),
                        ("hi", HARDWAREINPUT)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("u",)
            _fields_ = [("type", w.DWORD), ("u", _UNION)]

        self._INPUT = INPUT
        self._KEYBDINPUT = KEYBDINPUT

    def digitar(self, texto):
        INPUT_KEYBOARD, KEYUP, UNICODE = 1, 0x0002, 0x0004
        eventos = []
        for ch in texto:
            for cp in _utf16_units(ch):
                for flags in (UNICODE, UNICODE | KEYUP):
                    ev = self._INPUT(type=INPUT_KEYBOARD)
                    ev.ki = self._KEYBDINPUT(wVk=0, wScan=cp, dwFlags=flags,
                                             time=0, dwExtraInfo=0)
                    eventos.append(ev)
        if not eventos:
            return 0

        arr = (self._INPUT * len(eventos))(*eventos)
        n = self._user32.SendInput(len(eventos), arr,
                                   self._ctypes.sizeof(self._INPUT))
        if n != len(eventos):
            raise self._ctypes.WinError(self._ctypes.get_last_error())
        return n


def _utf16_units(ch):
    """Emojis e afins ocupam dois surrogates; SendInput quer um por evento."""
    b = ch.encode("utf-16-le")
    return [b[i] | (b[i + 1] << 8) for i in range(0, len(b), 2)]


# -------------------------------------------------------------------- Linux

class InjetorYdotool:
    """uinput via ydotool. Funciona em X11 e Wayland.

    Usa `ydotool key` com keycode cru, nao `ydotool type`. O `type` mapeia
    caractere->tecla assumindo layout US: pedir "?" nele apertaria a tecla que
    no ABNT2 e o ";", e sairia ":" na tela.
    """

    nome = "linux/ydotool"

    def __init__(self, mapa=None):
        self._exe = shutil.which("ydotool")
        if not self._exe:
            raise ErroInjecao(
                "ydotool nao encontrado. Instale com: sudo apt install ydotool")
        self._mapa = mapa if mapa is not None else descobrir_mapa()

    def digitar(self, texto):
        for ch in texto:
            combo = self._mapa.get(ch)
            if combo is None:
                raise ErroInjecao(
                    "nao sei que tecla produz %r neste layout. Rode "
                    "`xkbcli how-to-type %r` e adicione em _ABNT2." % (ch, ch))
            keycode, mods = combo

            # ydotool key aceita "codigo:1" = pressiona, "codigo:0" = solta.
            # Modificador tem que descer antes e subir depois da tecla.
            seq = ["%d:1" % m for m in mods]
            seq += ["%d:1" % keycode, "%d:0" % keycode]
            seq += ["%d:0" % m for m in reversed(mods)]

            r = subprocess.run([self._exe, "key"] + seq,
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise ErroInjecao(
                    "ydotool falhou (%s). O ydotoold esta rodando e voce tem "
                    "acesso a /dev/uinput? %s"
                    % (r.returncode, (r.stderr or "").strip()))
        return len(texto)


def descobrir_mapa(chars=("?", "/", "°")):
    """Descobre keycode+modificadores de cada caractere no layout ATIVO.

    Usa `xkbcli how-to-type`, que consulta o keymap de verdade em vez de
    chutar. Se nao estiver instalado (pacote libxkbcommon-tools) ou se o
    layout nao for detectavel, cai pro mapa fixo de ABNT2.
    """
    if not shutil.which("xkbcli"):
        return dict(_ABNT2)

    layout, variante = layout_ativo()
    mapa = {}
    for ch in chars:
        combo = _perguntar_xkbcli(ch, layout, variante)
        if combo:
            mapa[ch] = combo
        elif ch in _ABNT2:
            mapa[ch] = _ABNT2[ch]
    return mapa


def layout_ativo():
    """(layout, variante) do teclado ativo, ex: ("br", "abnt2").

    Precisa ser explicito: sem --layout o xkbcli responde pelo layout PADRAO
    (us), nao pelo seu. No US o "?" e Shift+KEY_SLASH (53); no ABNT2 e
    Shift+KEY_RO (89). Aceitar o default silenciosamente daria a tecla errada.
    """
    # GNOME, tanto em Wayland quanto em X11
    try:
        r = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            m = re.search(r"\('xkb',\s*'([^']+)'\)", r.stdout)
            if m:
                spec = m.group(1)            # ex: "br+abnt2" ou "us"
                if "+" in spec:
                    layout, variante = spec.split("+", 1)
                    return layout, variante
                return spec, None
    except (OSError, subprocess.SubprocessError):
        pass

    # X11 sem GNOME
    try:
        r = subprocess.run(["setxkbmap", "-query"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            lay = re.search(r"^layout:\s*(\S+)", r.stdout, re.M)
            var = re.search(r"^variant:\s*(\S+)", r.stdout, re.M)
            if lay:
                return (lay.group(1).split(",")[0],
                        var.group(1).split(",")[0] if var else None)
    except (OSError, subprocess.SubprocessError):
        pass

    return None, None


def _perguntar_xkbcli(ch, layout=None, variante=None):
    cmd = ["xkbcli", "how-to-type"]
    if layout:
        cmd += ["--layout", layout]
    if variante:
        cmd += ["--variant", variante]
    cmd.append(ch)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None

    # Tabela:  KEYCODE  KEY NAME  LAYOUT#  LAYOUT NAME  LEVEL#  MODIFIERS
    #          97       <AB11>    1        Portuguese (Brazil)  2  [ Shift ]
    #
    # Nao da pra fatiar por coluna: "Portuguese (Brazil)" tem espaco e o
    # numero de colunas varia entre versoes. Ancoro no que e estavel - a
    # linha comeca com o keycode e os modificadores vem entre colchetes.
    for linha in r.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s", linha)
        if not m:
            continue

        # xkb numera keycode com offset de 8 em relacao ao evdev - heranca do
        # X11. O ydotool fala evdev, entao desconta.
        keycode = int(m.group(1)) - 8

        colchetes = re.search(r"\[([^\]]*)\]", linha)
        texto_mods = (colchetes.group(1) if colchetes else "").lower()

        mods = []
        if "shift" in texto_mods:
            mods.append(KEY_LEFTSHIFT)
        if "level3" in texto_mods or "alt" in texto_mods or "mod5" in texto_mods:
            mods.append(KEY_RIGHTALT)
        return keycode, mods
    return None


# ------------------------------------------------------------------ fabrica

def criar_injetor():
    if sys.platform == "win32":
        return InjetorWindows()
    if sys.platform.startswith("linux"):
        return InjetorYdotool()
    raise ErroInjecao("plataforma nao suportada: %s" % sys.platform)


if __name__ == "__main__":
    # Diagnostico: python injetor.py
    inj = criar_injetor()
    print("backend:", inj.nome)
    if isinstance(inj, InjetorYdotool):
        print("mapa de teclas descoberto:")
        for ch, (kc, mods) in sorted(inj._mapa.items()):
            print("  %r -> keycode %d, mods %s" % (ch, kc, mods or "nenhum"))

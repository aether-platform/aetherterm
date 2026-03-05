"""ANSIエスケープシーケンス除去

正規表現ベースでCSI, OSC, SGR等の主要ANSIシーケンスを除去し、
PTY出力からプレーンテキストを抽出する。
"""

import re

# ANSIエスケープシーケンスの正規表現パターン
# CSI (Control Sequence Introducer): ESC [ ... final_byte
# OSC (Operating System Command): ESC ] ... ST
# SGR等の一般的なエスケープ: ESC (... | [#(] ...)
_ANSI_ESCAPE_RE = re.compile(
    rb"(?:"
    # CSI sequences: ESC[ + params + intermediate + final byte
    rb"\x1b\[[0-9;?]*[ -/]*[@-~]"
    rb"|"
    # OSC sequences: ESC] ... (ST=ESC\ or BEL)
    rb"\x1b\].*?(?:\x1b\\|\x07)"
    rb"|"
    # DCS/PM/APC sequences: ESC P/^/_ ... ST
    rb"\x1b[P^_].*?(?:\x1b\\|\x07)"
    rb"|"
    # Two-character ESC sequences: ESC + single byte
    rb"\x1b[()#][A-Z0-9]"
    rb"|"
    # Simple ESC sequences: ESC + [space-/]* + final byte
    rb"\x1b[ -/]*[0-~]"
    rb"|"
    # Standalone control chars (BEL, BS, etc.) except newline/tab/CR
    rb"[\x00-\x08\x0b\x0c\x0e-\x1f]"
    rb")",
    re.DOTALL,
)


def strip_ansi(data: bytes) -> str:
    """ANSIエスケープシーケンスを除去してプレーンテキストを返す

    Args:
        data: PTYからのraw bytesデータ

    Returns:
        ANSIエスケープ除去済みのプレーンテキスト
    """
    cleaned = _ANSI_ESCAPE_RE.sub(b"", data)
    return cleaned.decode("utf-8", errors="replace")

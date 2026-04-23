"""Auto-atualização via GitHub Releases — EncomendasEdy."""
from __future__ import annotations

import os
import sys
import subprocess
import signal
from pathlib import Path
from typing import Callable, Optional, Tuple

# VERSION é gerado em _version.py pelo build_exe.py e embutido no .exe.
# Em modo de desenvolvimento (python run_app.py), cai no fallback abaixo.
try:
    from ._version import VERSION  # type: ignore[import]
except ImportError:
    _vfile = Path(__file__).resolve().parent.parent.parent / "version.txt"
    VERSION = _vfile.read_text(encoding="utf-8").strip() if _vfile.exists() else "0.0.0"

# ── Configure aqui após criar o repositório no GitHub ──────────────────────
GITHUB_REPO = "kev-wmv/automacao-compras-edyplaneajdos"
# ───────────────────────────────────────────────────────────────────────────

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
TIMEOUT = 8  # segundos — se o GitHub não responder, o app abre normalmente


def get_current_version() -> str:
    """Retorna a versão embutida no build."""
    return VERSION


def _parse_version(v: str) -> Tuple[int, ...]:
    """Converte '1.2.3' em (1, 2, 3) para comparação numérica."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def check_for_update() -> Optional[Tuple[str, str]]:
    """
    Consulta a API do GitHub para verificar se há uma versão mais nova.

    Retorna (versao_mais_nova, url_download) se houver atualização,
    ou None se já estiver na versão mais recente.

    Lança exceção se a verificação falhar (sem internet, SSL, timeout, etc.)
    — o chamador decide se silencia ou mostra ao usuário.
    """
    import requests  # noqa: PLC0415
    import certifi

    # Dentro do .exe (PyInstaller), certifi precisa de caminho explícito
    ca_bundle = certifi.where()
    if not os.path.exists(ca_bundle):
        ca_bundle = False  # type: ignore[assignment]

    try:
        resp = requests.get(
            API_URL,
            timeout=TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
            verify=ca_bundle,
        )
    except Exception:
        # Fallback sem verificação SSL (ambientes com CA bundle ausente)
        resp = requests.get(
            API_URL,
            timeout=TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
            verify=False,
        )
    resp.raise_for_status()
    data = resp.json()

    latest_tag = data.get("tag_name", "").lstrip("v")
    if not latest_tag:
        return None

    # Procura o asset .exe na release
    exe_url: Optional[str] = None
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".exe"):
            exe_url = asset["browser_download_url"]
            break

    if not exe_url:
        return None

    if _parse_version(latest_tag) > _parse_version(get_current_version()):
        return (latest_tag, exe_url)

    return None


def download_update(
    url: str,
    progress_callback: Callable[[int, int], None],
) -> Optional[Path]:
    """
    Baixa o novo .exe para EncomendasEdy_update.exe na mesma pasta do .exe atual.

    progress_callback(bytes_baixados, total_bytes) é chamado periodicamente.
    Retorna o Path do arquivo baixado, ou None em caso de falha.
    """
    try:
        import requests  # noqa: PLC0415

        if getattr(sys, "frozen", False):
            current_exe = Path(sys.executable)
        else:
            # Modo dev: salva em dist/ para não poluir o projeto
            current_exe = Path(__file__).resolve().parent.parent.parent / "dist" / "EncomendasEdy.exe"
            current_exe.parent.mkdir(parents=True, exist_ok=True)

        dest = current_exe.parent / "EncomendasEdy_update.exe"

        import certifi
        resp = requests.get(url, stream=True, timeout=120, verify=certifi.where())
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with dest.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        progress_callback(downloaded, total)

        return dest

    except Exception:
        return None


def apply_update(new_exe_path: Path) -> None:
    """
    Cria um script .bat que:
      1. Aguarda 2 segundos para o .exe atual fechar completamente
      2. Substitui EncomendasEdy.exe pelo arquivo baixado
      3. Abre a nova versão
      4. Se auto-deleta

    Em seguida lança o .bat em modo detached e encerra este processo.
    Só executa quando rodando como .exe compilado (sys.frozen).
    """
    if not getattr(sys, "frozen", False):
        # Modo dev: não faz nada perigoso
        return

    current_exe = Path(sys.executable)
    bat_path = current_exe.parent / "update_helper.bat"

    bat_content = (
        "@echo off\r\n"
        "timeout /t 2 /nobreak > NUL\r\n"
        f'move /y "{new_exe_path}" "{current_exe}"\r\n'
        f'start "" "{current_exe}"\r\n'
        'del "%~f0"\r\n'
    )
    bat_path.write_text(bat_content, encoding="ascii")

    # Lança o .bat desacoplado do processo atual
    subprocess.Popen(
        ["cmd.exe", "/c", str(bat_path)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )

    # os._exit encerra o processo inteiro independente de qual thread chama.
    # sys.exit() levanta SystemExit que é capturado pela thread atual, não mata o processo.
    os._exit(0)

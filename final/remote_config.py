"""Config central via Gist secreto — EncomendasEdy.

O `lojas.config` (lojas, e-mails, fornecedores) vive num Gist secreto do
GitHub. Todos os usuários BAIXAM a config no startup; só a máquina do
administrador (que tem um token de escrita local) consegue SALVAR de volta.
Assim, uma edição feita na sessão adm propaga para todos no próximo startup.

Prioridade de leitura:
    1. Gist remoto (online)  -> atualiza o cache local
    2. Cache local (%APPDATA%\\EncomendasEdy\\lojas.config) -> offline
    3. None -> o chamador cai no fallback embutido no .exe

Escrita (só admin):
    PATCH no Gist + atualização do cache. Requer token com escopo `gist`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# ── Localização do Gist central (secreto) ───────────────────────────────────
# O ID/URL do gist NÃO ficam no código (o repositório é público e a URL do gist
# é a própria credencial de leitura). Vêm de `remote.json`, que é gitignored e
# embutido no .exe pelo build (igual ao lojas.config), ou de variáveis de
# ambiente em desenvolvimento.
FETCH_TIMEOUT = 6  # s — se o GitHub não responder, cai no cache/embutido
ADMIN_TOKEN_FILENAME = ".admin_token"
REMOTE_SETTINGS_FILENAME = "remote.json"


def _base_dir() -> Path:
    """Pasta base: _MEIPASS no .exe empacotado, raiz do projeto em dev."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def _remote_settings() -> dict:
    """Lê gist_id/raw_url do remote.json (embutido/local) ou de env vars."""
    gist_id = os.environ.get("EDY_GIST_ID", "").strip()
    raw_url = os.environ.get("EDY_GIST_RAW_URL", "").strip()
    filename = "lojas.config"
    if not (gist_id and raw_url):
        try:
            data = json.loads((_base_dir() / REMOTE_SETTINGS_FILENAME).read_text(encoding="utf-8"))
            gist_id = gist_id or str(data.get("gist_id", "")).strip()
            raw_url = raw_url or str(data.get("raw_url", "")).strip()
            filename = str(data.get("gist_filename", filename)).strip() or filename
        except (OSError, json.JSONDecodeError):
            pass
    return {"gist_id": gist_id, "raw_url": raw_url, "gist_filename": filename}


def _raw_url() -> Optional[str]:
    return _remote_settings()["raw_url"] or None


def _gist_api() -> Optional[str]:
    gid = _remote_settings()["gist_id"]
    return f"https://api.github.com/gists/{gid}" if gid else None


def _gist_filename() -> str:
    return _remote_settings()["gist_filename"]


def _app_data_dir() -> Path:
    """Pasta gravável por-usuário: %APPDATA%\\EncomendasEdy (ou ~ em fallback)."""
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home()
    d = root / "EncomendasEdy"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path() -> Path:
    return _app_data_dir() / _gist_filename()


def _ca_bundle():
    """Caminho do CA bundle do certifi (ou False se ausente, p/ não quebrar)."""
    try:
        import certifi

        path = certifi.where()
        return path if os.path.exists(path) else False
    except Exception:
        return False


# ── Leitura ────────────────────────────────────────────────────────────────
def fetch_remote_text() -> Optional[str]:
    """Baixa o conteúdo bruto do gist. Retorna None em qualquer falha."""
    url = _raw_url()
    if not url:
        return None
    try:
        import requests  # noqa: PLC0415

        resp = requests.get(url, timeout=FETCH_TIMEOUT, verify=_ca_bundle())
        resp.raise_for_status()
        text = resp.text
        # valida que é JSON antes de aceitar/cachear
        json.loads(text)
        return text
    except Exception:
        return None


def _read_cache() -> Optional[str]:
    try:
        text = _cache_path().read_text(encoding="utf-8")
        json.loads(text)
        return text
    except Exception:
        return None


def _write_cache(text: str) -> None:
    try:
        _cache_path().write_text(text, encoding="utf-8")
    except OSError:
        pass


def load_config_text() -> Optional[str]:
    """Texto da config seguindo a prioridade remoto > cache > None.

    None sinaliza ao chamador para usar o fallback embutido no .exe.
    """
    remote = fetch_remote_text()
    if remote is not None:
        _write_cache(remote)
        return remote
    return _read_cache()


# ── Escrita (admin) ─────────────────────────────────────────────────────────
def _admin_token() -> Optional[str]:
    """Token de escrita — presente só na máquina do administrador.

    Ordem: arquivo .admin_token em %APPDATA%\\EncomendasEdy, depois a env var
    GITHUB_TOKEN (útil em dev). Ausência => máquina não-admin (só leitura).
    """
    token_file = _app_data_dir() / ADMIN_TOKEN_FILENAME
    try:
        if token_file.exists():
            tok = token_file.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    return env or None


def has_admin_access() -> bool:
    """True se esta máquina tem token de escrita (é a estação de admin)."""
    return _admin_token() is not None


def save_config_text(text: str) -> None:
    """Publica a config no gist (propaga a todos) e atualiza o cache local.

    Levanta PermissionError se não houver token, ou RuntimeError na falha da API.
    """
    json.loads(text)  # valida antes de publicar
    token = _admin_token()
    if not token:
        raise PermissionError(
            "Esta máquina não tem credencial de administrador para salvar a "
            "configuração central."
        )
    api = _gist_api()
    if not api:
        raise RuntimeError("Localização do gist central não configurada (remote.json).")

    import requests  # noqa: PLC0415

    payload = {"files": {_gist_filename(): {"content": text}}}
    resp = requests.patch(
        api,
        json=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "encomendas-edy",
        },
        timeout=30,
        verify=_ca_bundle(),
    )
    if not resp.ok:
        raise RuntimeError(
            f"Falha ao salvar a configuração central (HTTP {resp.status_code})."
        )
    _write_cache(text)

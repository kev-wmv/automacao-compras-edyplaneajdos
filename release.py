"""
Publica uma nova release no GitHub com o .exe compilado.

Uso:
    python release.py

Requer:
    - version.txt atualizado com a nova versão
    - dist/EncomendasEdy.exe compilado pelo build_exe.py
    - Token do GitHub em .env (GITHUB_TOKEN=ghp_...) ou na variável de ambiente

Instale a dependência (só na máquina de desenvolvimento, uma vez):
    pip install requests
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / "version.txt"
EXE_PATH = PROJECT_ROOT / "dist" / "EncomendasEdy.exe"

# ── Configure com o seu usuário e repositório do GitHub ────────────────────
GITHUB_REPO = "kev-wmv/automacao-compras-edyplaneajdos"
# ───────────────────────────────────────────────────────────────────────────

API_BASE = "https://api.github.com"


def _get_token() -> str:
    """Lê o token do GitHub da variável de ambiente ou do arquivo .env."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise SystemExit(
        "\nGITHUB_TOKEN nao encontrado.\n"
        "Crie um arquivo .env na raiz do projeto com o conteudo:\n"
        "  GITHUB_TOKEN=ghp_seu_token_aqui\n"
        "\nPara gerar o token: GitHub → Settings → Developer settings\n"
        "→ Personal access tokens → Tokens (classic) → Generate new token\n"
        "Marque o escopo: repo\n"
    )


def main() -> None:
    try:
        import requests
    except ImportError:
        raise SystemExit(
            "Biblioteca 'requests' nao instalada.\n"
            "Execute: pip install requests"
        )

    if not VERSION_FILE.exists():
        raise SystemExit("version.txt nao encontrado.")

    if not EXE_PATH.exists():
        raise SystemExit(
            f"Executavel nao encontrado em:\n  {EXE_PATH}\n"
            "Execute build_exe.py primeiro."
        )

    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("version.txt esta vazio. Adicione um numero de versao (ex: 1.0.1).")

    tag = f"v{version}"
    token = _get_token()
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }

    print(f"\nPublicando release {tag} para {GITHUB_REPO}...")

    # 1. Criar tag git local e fazer push
    result = subprocess.run(["git", "tag", tag], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        if "already exists" in result.stderr:
            raise SystemExit(
                f"A tag {tag} ja existe.\n"
                "Atualize o version.txt para um numero maior antes de publicar."
            )
        raise SystemExit(f"Erro ao criar tag git:\n{result.stderr}")

    result = subprocess.run(["git", "push", "origin", tag], cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        # Desfaz a tag local para não ficar inconsistente
        subprocess.run(["git", "tag", "-d", tag], cwd=PROJECT_ROOT)
        raise SystemExit(f"Erro ao fazer push da tag:\n{result.stderr}")

    print(f"  Tag {tag} criada e enviada.")

    # 2. Criar a release no GitHub
    resp = requests.post(
        f"{API_BASE}/repos/{GITHUB_REPO}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": f"EncomendasEdy {version}",
            "body": f"Versao {version}.",
            "draft": False,
            "prerelease": False,
        },
        timeout=30,
    )
    if not resp.ok:
        raise SystemExit(f"Erro ao criar release ({resp.status_code}):\n{resp.text}")

    release_data = resp.json()
    upload_url = release_data["upload_url"].replace("{?name,label}", "")
    print(f"  Release criada: {release_data['html_url']}")

    # 3. Fazer upload do .exe como asset da release
    exe_size_mb = EXE_PATH.stat().st_size / 1_048_576
    print(f"  Enviando {EXE_PATH.name} ({exe_size_mb:.1f} MB)...")

    with EXE_PATH.open("rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={**headers, "Content-Type": "application/octet-stream"},
            params={"name": "EncomendasEdy.exe"},
            data=f,
            timeout=300,
        )

    if not upload_resp.ok:
        raise SystemExit(f"Erro no upload ({upload_resp.status_code}):\n{upload_resp.text}")

    print(f"  Upload concluido: {upload_resp.json()['browser_download_url']}")
    print(f"\nRelease {tag} publicada com sucesso!\n")


if __name__ == "__main__":
    main()

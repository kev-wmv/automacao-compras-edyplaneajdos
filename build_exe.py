import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY_POINT = PROJECT_ROOT / "run_app.py"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
CONFIG_PATH = PROJECT_ROOT / "lojas.config"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
BUILD_LOG_PATH = PROJECT_ROOT / "build_log.txt"
FLET_RUNTIME_ARCHIVE = PROJECT_ROOT / "flet-windows.zip"
GENERATED_PATHS = (
    DIST_DIR,
    BUILD_DIR,
    PROJECT_ROOT / "nuitka_dist",
    PROJECT_ROOT / "__pycache__",
    PROJECT_ROOT / ".pytest_cache",
    PROJECT_ROOT / "EncomendasEdy.spec",
    PROJECT_ROOT / "run_app.spec",
    BUILD_LOG_PATH,
    FLET_RUNTIME_ARCHIVE,
    PROJECT_ROOT / "nuitka-crash-report.xml",
)
GENERATED_GLOBS = (
    "pytest-cache-files-*",
)
REQUIRED_MODULES = (
    ("PyInstaller", "PyInstaller"),
    ("flet", "flet"),
    ("flet_desktop", "flet-desktop"),
    ("playwright", "playwright"),
    ("pdfplumber", "pdfplumber"),
    ("PIL", "Pillow"),
)


def _preferred_python() -> Path:
    if VENV_PYTHON.exists():
        return VENV_PYTHON
    return Path(sys.executable)


def _remove_path(path: Path) -> None:
    def _onerror(func, path_str, exc_info):
        error = exc_info[1]
        if isinstance(error, PermissionError):
            Path(path_str).chmod(stat.S_IWRITE | stat.S_IREAD)
            func(path_str)
        else:
            raise error

    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, onerror=_onerror)
    else:
        path.unlink()


def _iter_generated_paths() -> Iterable[Path]:
    for path in GENERATED_PATHS:
        yield path
    for pattern in GENERATED_GLOBS:
        yield from PROJECT_ROOT.glob(pattern)


def _cleanup_previous_build() -> None:
    for path in _iter_generated_paths():
        if not path.exists():
            continue
        try:
            _remove_path(path)
        except PermissionError:
            if path in {DIST_DIR, BUILD_DIR}:
                print(
                    f"Aviso: nao foi possivel remover {path} por falta de permissao. "
                    "Feche programas usando a pasta."
                )
                raise
            print(f"Aviso: limpeza ignorada para {path} por falta de permissao.")


def _validate_build_environment(python_executable: Path) -> None:
    check_script = (
        "import importlib.util\n"
        "required = ["
        + ", ".join(f"({module!r}, {label!r})" for module, label in REQUIRED_MODULES)
        + "]\n"
        "missing = [label for module, label in required if importlib.util.find_spec(module) is None]\n"
        "print('\\n'.join(missing))\n"
        "raise SystemExit(1 if missing else 0)\n"
    )
    result = subprocess.run(
        [str(python_executable), "-c", check_script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return
    missing = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    missing_text = ", ".join(missing) if missing else "dependencias obrigatorias"
    raise SystemExit(
        f"Ambiente de build incompleto em {python_executable}. "
        f"Instale: {missing_text}."
    )


def _prepare_flet_runtime_archive(python_executable: Path) -> Path:
    script = (
        "import json\n"
        "import flet_desktop\n"
        "cache_dir = flet_desktop.ensure_client_cached()\n"
        "data = {\n"
        "    'artifact': flet_desktop.__get_artifact_filename(),\n"
        "    'cache_dir': str(cache_dir),\n"
        "}\n"
        "print(json.dumps(data))\n"
    )
    result = subprocess.run(
        [str(python_executable), "-c", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
        raise SystemExit(f"Nao foi possivel preparar o runtime do Flet: {details}")

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise SystemExit("Nao foi possivel obter metadados do runtime do Flet.")

    try:
        metadata = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "Nao foi possivel interpretar os metadados do runtime do Flet."
        ) from exc

    artifact_name = str(metadata.get("artifact", "")).strip()
    cache_dir = Path(str(metadata.get("cache_dir", "")).strip())
    if not artifact_name or not cache_dir.exists():
        raise SystemExit(
            "Runtime do Flet indisponivel. Garanta que o cliente desktop esteja em cache."
        )

    archive_path = PROJECT_ROOT / artifact_name
    base_name = archive_path.with_suffix("")
    shutil.make_archive(str(base_name), "zip", root_dir=str(cache_dir))
    return archive_path


def _build_command(python_executable: Path, runtime_archive: Path) -> Sequence[str]:
    exclude_modules = [
        "torch", "torchvision", "torchaudio", "torchtext", "matplotlib",
        "pandas", "numpy", "transformers", "openai", "langchain",
        "llama_index", "llama_cpp", "PySide6", "shiboken6",
        "notebook", "jupyter", "ipython", "cv2", "gradio", "huggingface_hub",
        "scipy", "scikit-learn", "sklearn",
    ]

    command = [
        str(python_executable),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--noupx",
        "--log-level=DEBUG",
        "--windowed",
        "--onefile",
        "--icon",
        "NONE",
        "--collect-data",
        "flet.controls.material",
        "--collect-data",
        "flet.controls.cupertino",
        "--add-data",
        f"{runtime_archive}{os.pathsep}flet_desktop/app",
        "--name",
        "EncomendasEdy",
    ]

    for module_name in exclude_modules:
        command.extend(["--exclude-module", module_name])

    command.extend([
        str(ENTRY_POINT),
    ])
    return command


def _copy_public_config() -> None:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Arquivo de configuracao nao encontrado: {CONFIG_PATH}")
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG_PATH, DIST_DIR / CONFIG_PATH.name)


def _run_build_command(command: Sequence[str]) -> int:
    with BUILD_LOG_PATH.open("w", encoding="utf-8", errors="replace") as log_file:
        log_file.write("Comando:\n")
        log_file.write(" ".join(command))
        log_file.write("\n\n")
        log_file.flush()

        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )

        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)

        return process.wait()


def main() -> None:
    if not ENTRY_POINT.exists():
        raise SystemExit(f"Arquivo de entrada nao encontrado: {ENTRY_POINT}")

    python_executable = _preferred_python()
    print("Preparando ambiente de build...")
    print(f"Python selecionado: {python_executable}")
    _validate_build_environment(python_executable)
    _cleanup_previous_build()
    runtime_archive = _prepare_flet_runtime_archive(python_executable)
    print(f"Runtime Flet embutido a partir de: {runtime_archive}")

    command = list(_build_command(python_executable, runtime_archive))
    print("Iniciando compilacao. Isso pode levar alguns minutos...")
    print("Comando:", " ".join(command))
    print(f"Log do build: {BUILD_LOG_PATH}")

    returncode = _run_build_command(command)
    if returncode != 0:
        raise SystemExit(
            f"Falha na geracao do executavel (codigo {returncode}). "
            f"Consulte o log em: {BUILD_LOG_PATH}"
        )

    exe_path = DIST_DIR / "EncomendasEdy.exe"
    if not exe_path.exists():
        raise SystemExit("Build concluido, mas nao foi possivel localizar o executavel em dist/.")

    _copy_public_config()
    print("================================================================")
    print("BUILD CONCLUIDO COM SUCESSO!")
    print(f"O executavel esta em: {exe_path}")
    print("Arquivo publico de configuracao copiado para dist/lojas.config.")
    print(f"Log salvo em: {BUILD_LOG_PATH}")
    print("================================================================")


if __name__ == "__main__":
    main()

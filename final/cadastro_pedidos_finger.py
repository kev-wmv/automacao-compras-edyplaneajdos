import asyncio
import contextlib
import json
import os
import hashlib
import logging
from typing import Callable, Iterator, Mapping, MutableMapping, Optional, Sequence, Tuple
from pathlib import Path
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright
import time

logger = logging.getLogger(__name__)

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - apenas usado em ambientes Unix
    import fcntl

try:
    from .cadastro_clientes_finger import CONFIG_FILENAME, ensure_config
except ImportError:  # pragma: no cover
    from cadastro_clientes_finger import CONFIG_FILENAME, ensure_config  # type: ignore

try:
    from .models import ProcessoCancelado
except ImportError:  # pragma: no cover
    from models import ProcessoCancelado  # type: ignore

_FINGER_BROWSER_VISIBLE: Optional[bool] = None


def _finger_browser_visible() -> bool:
    import os
    env_val = os.environ.get("FINGER_BROWSER_VISIBLE")
    if env_val:
        return env_val != "N"
    global _FINGER_BROWSER_VISIBLE
    if _FINGER_BROWSER_VISIBLE is None:
        try:
            config_data = ensure_config(include_meta=True)  # type: ignore[arg-type]
        except Exception:
            _FINGER_BROWSER_VISIBLE = True
        else:
            settings = config_data.get("settings", {}) if isinstance(config_data, dict) else {}
            value = str(settings.get("finger_browser_visible", "Y")).strip().upper()
            _FINGER_BROWSER_VISIBLE = value != "N"
    return _FINGER_BROWSER_VISIBLE

# Dicionário para mapear palavras-chave do nome do arquivo para as classificações
GRUPO_MAPPING = {
    # HOME OFFICE
    "office": "HOME OFFICE",
    "escritorio": "HOME OFFICE",
    "home office": "HOME OFFICE",
    "estudio": "HOME OFFICE",
    
    # HOME THEATER
    "theater": "HOME THEATHER",
    "cinema": "HOME THEATHER",
    "sala": "HOME THEATHER",
    "entretenimento": "HOME THEATHER",
    "home theater": "HOME THEATHER",
    "living": "HOME THEATHER",
    "home": "HOME THEATHER",

    
    # DORMITORIO
    "dormitorio": "DORMITORIO",
    "quarto": "DORMITORIO",
    "suite": "DORMITORIO",
    "master": "DORMITORIO",
    "dorm.": "DORMITORIO",
    
    # COZINHA
    "cozinha": "COZINHA",
    "kitchen": "COZINHA",
    
    # CLOSET
    "closet": "CLOSET",
    "guardaroupa": "CLOSET",
    "armario": "CLOSET",
    
    # BANHEIROS
    "wc": "BANHEIROS",
    "banheiro": "BANHEIROS",
    "banheiros": "BANHEIROS",
    "toilet": "BANHEIROS",
    "lavabo": "BANHEIROS",
    
    # AREA DE SERVIÇO
    "servico": "AREA DE SERVICO",
    "serviço": "AREA DE SERVICO",
    "area": "AREA DE SERVICO",
    "área": "AREA DE SERVICO",
    "lavanderia": "AREA DE SERVICO",
    "utilidades": "AREA DE SERVICO",
}


PENDING_TIMEOUT_SECONDS = 1800.0


def _registry_paths(base_dir: Path) -> Tuple[Path, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "pedidos_importados.json", base_dir / "pedidos_importados.lock"


def _compute_file_key(txt_path: Path) -> str:
    """Retorna um identificador estável baseado no conteúdo do arquivo."""
    hasher = hashlib.sha256()
    with txt_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@contextlib.contextmanager
def _acquire_registry_lock(base_dir: Path) -> Iterator[None]:
    _, lock_path = _registry_paths(base_dir)
    with lock_path.open("a+b") as lock_handle:
        if os.name == "nt":
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover - Unix
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Unix
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _load_registry(base_dir: Path) -> Mapping[str, Mapping[str, object]]:
    registry_path, _ = _registry_paths(base_dir)
    if not registry_path.exists():
        return {}
    try:
        with registry_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_registry(base_dir: Path, data: Mapping[str, Mapping[str, object]]) -> None:
    registry_path, _ = _registry_paths(base_dir)
    temp_path = registry_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2)
    temp_path.replace(registry_path)


def _reserve_txt(txt_path: Path, base_dir: Path) -> Optional[Tuple[str, Mapping[str, object]]]:
    file_key = _compute_file_key(txt_path)
    now = time.time()
    meta = {
        "path": str(txt_path),
        "size": txt_path.stat().st_size,
        "mtime": txt_path.stat().st_mtime,
    }
    with _acquire_registry_lock(base_dir):
        registry = dict(_load_registry(base_dir))
        entry = registry.get(file_key)
        if entry:
            status = entry.get("status")
            timestamp = float(entry.get("timestamp", 0.0))
            if status == "completed":
                return None
            if status == "pending" and (now - timestamp) < PENDING_TIMEOUT_SECONDS:
                return None
        registry[file_key] = {
            "status": "pending",
            "timestamp": now,
            **meta,
        }
        _write_registry(base_dir, registry)
    return file_key, meta


def _mark_txt_completed(file_key: str, base_dir: Path) -> None:
    with _acquire_registry_lock(base_dir):
        registry = dict(_load_registry(base_dir))
        entry = registry.get(file_key)
        if not entry:
            registry[file_key] = {"status": "completed", "timestamp": time.time()}
        else:
            entry["status"] = "completed"
            entry["completed_at"] = time.time()
        _write_registry(base_dir, registry)


def _release_txt_reservation(file_key: str, base_dir: Path) -> None:
    with _acquire_registry_lock(base_dir):
        registry = dict(_load_registry(base_dir))
        entry = registry.get(file_key)
        if entry and entry.get("status") == "pending":
            registry.pop(file_key, None)
            _write_registry(base_dir, registry)


def _cleanup_registry(base_dir: Path) -> None:
    registry_path, lock_path = _registry_paths(base_dir)
    with contextlib.suppress(FileNotFoundError):
        registry_path.unlink()
    with contextlib.suppress(FileNotFoundError):
        lock_path.unlink()


def _is_txt_marked_completed(file_key: str, base_dir: Path) -> bool:
    with _acquire_registry_lock(base_dir):
        registry = dict(_load_registry(base_dir))
        entry = registry.get(file_key)
        return bool(entry and entry.get("status") == "completed")


def determinar_grupo_por_arquivo(txt_path: str) -> str:
    """
    Determina o grupo baseado no nome do arquivo TXT.
    
    Args:
        txt_path: Caminho para o arquivo TXT
        
    Returns:
        Nome do grupo correspondente ou "AREA DE SERVIÇO" como padrão
    """
    nome_arquivo = Path(txt_path).stem.lower()  # Remove extensão e converte para minúsculas
    
    # Procura por palavras-chave no nome do arquivo
    for palavra_chave, grupo in GRUPO_MAPPING.items():
        if palavra_chave in nome_arquivo:
            return grupo
    
    # Retorna padrão se nenhuma palavra-chave for encontrada
    return "AREA DE SERVICO"


async def _preparar_formulario_pedidos(
    page,
    usuario: str,
    senha: str,
    nome_cliente: str,
    comprador_nome: str,
    numero_contrato: str,
    ordem_compra: str,
    grupo: str,
) -> None:
    await page.goto("http://187.45.123.235:18914/pedidos3/login.asp")
    await page.get_by_role("textbox", name="Usu\u00e1rio:").fill(usuario)
    await page.get_by_role("textbox", name="Senha:").fill(senha)
    await page.get_by_role("link", name="logar no sistema").click()
    try:
        menu = page.get_by_text("Cadastros Clientes Pedidos")
        await menu.wait_for(timeout=5000)
        await menu.click()
    except Exception as exc:
        raise RuntimeError(
            "Timeout ao acessar menu Cadastros Clientes Pedidos. Reabra a aplicacao e tente novamente."
        ) from exc

    await page.get_by_role("link", name="Pedidos").click()
    await page.wait_for_load_state("networkidle")
    await page.get_by_role("textbox", name="Cliente :").wait_for(timeout=5000)
    await page.get_by_label("Tipo de Embarque :").select_option("L")
    await page.get_by_role("textbox", name="Cliente :").click()
    await page.get_by_role("textbox", name="Cliente :").fill(nome_cliente)
    cliente_locator = page.get_by_text(nome_cliente, exact=False)
    try:
        await cliente_locator.wait_for(timeout=5000)
        await cliente_locator.first.click()
    except Exception as exc:
        raise RuntimeError(f"Cliente '{nome_cliente}' nao encontrado na lista.") from exc

    alerta = page.get_by_text("Aten\u00e7\u00e3o! - Este cliente")
    try:
        await alerta.wait_for(timeout=1500)
    except PlaywrightTimeoutError:
        pass
    else:
        try:
            await alerta.click()
        except Exception:
            pass

    await page.get_by_role("textbox", name="Comprador :").click()
    await page.get_by_role("textbox", name="Comprador :").fill(comprador_nome)
    ordem_input = page.get_by_role("textbox", name="Ordem de Compra :")
    await ordem_input.wait_for(timeout=5000)
    await ordem_input.click()
    await ordem_input.fill(ordem_compra)
    await page.get_by_role("textbox", name="Pd.Consumidor :").click()
    await page.get_by_role("textbox", name="Pd.Consumidor :").fill(numero_contrato)

    await page.locator("#consultagrupo").click()
    await page.get_by_role("gridcell", name=grupo).click()


async def _click_until_success(locator, retry_delay: float = 1.0, ensure_enabled: bool = False, max_retries: int = 30) -> None:
    for attempt in range(max_retries):
        try:
            await locator.wait_for(state="attached", timeout=5000)
            await locator.wait_for(state="visible", timeout=5000)
            if ensure_enabled:
                try:
                    if not await locator.is_enabled():
                        raise RuntimeError("Locator not enabled yet")
                except Exception as exc:
                    logger.debug("Locator check failed (tentativa %d/%d): %s", attempt + 1, max_retries, exc)
                    await asyncio.sleep(retry_delay)
                    continue
            await locator.click()
            return
        except Exception as exc:
            logger.debug("Click falhou (tentativa %d/%d): %s", attempt + 1, max_retries, exc)
            try:
                await locator.wait_for(state="visible", timeout=2000)
            except Exception:
                pass
            await asyncio.sleep(retry_delay)
    raise TimeoutError(f"Elemento nao respondeu apos {max_retries} tentativas.")


NAVIGATOR_STAGGER_SECONDS = 10.0
MAX_CONCURRENT_BROWSERS = 5


async def _set_import_file(page, file_path: Path) -> None:
    if not file_path.is_file():
        raise FileNotFoundError(f"Arquivo TXT '{file_path}' nao encontrado.")

    file_input = page.locator("input[type='file']").last
    try:
        await file_input.wait_for(state="attached", timeout=5000)
        await file_input.set_input_files(str(file_path))
        return
    except Exception:
        pass

    # Fallback para implementacoes que so expõem o chooser nativo via clique.
    async with page.expect_file_chooser() as file_chooser_info:
        await page.locator("input[type='file'], button, label").filter(has_text="File").last.click(force=True)
    file_chooser = await file_chooser_info.value
    await file_chooser.set_files(str(file_path))


async def _processar_item_async(
    playwright,
    item: MutableMapping[str, object],
    usuario: str,
    senha: str,
    nome_cliente: str,
    comprador_nome: str,
    numero_contrato: str,
    registro_base: Path,
    delay_seconds: float = 0.0,
    finalizar: bool = False,
    cancel_event=None,
) -> None:
    browser = None
    context = None
    try:
        if cancel_event is not None and cancel_event.is_set():
            raise ProcessoCancelado("Processo cancelado pelo usuario.")

        file_key = str(item["file_key"])
        if item.get("completed") or _is_txt_marked_completed(file_key, registro_base):
            item["completed"] = True
            return
        if delay_seconds > 0:
            elapsed = 0.0
            while elapsed < delay_seconds:
                if cancel_event is not None and cancel_event.is_set():
                    raise ProcessoCancelado("Processo cancelado pelo usuario.")
                step = min(1.0, delay_seconds - elapsed)
                await asyncio.sleep(step)
                elapsed += step
            if item.get("completed") or _is_txt_marked_completed(file_key, registro_base):
                item["completed"] = True
                return
        
        if cancel_event is not None and cancel_event.is_set():
            raise ProcessoCancelado("Processo cancelado pelo usuario.")

        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            if cancel_event is not None and cancel_event.is_set():
                raise ProcessoCancelado("Processo cancelado pelo usuario.")
            browser = await playwright.chromium.launch(channel='chrome', headless=not _finger_browser_visible())
            context = await browser.new_context()
            page = await context.new_page()
            
            # Ajusta o Controle do Representante(Ordem de Compra) na repeticao
            ordem_compra_atual = str(item["ordem"])
            if attempt > 1:
                ordem_compra_atual = f"{ordem_compra_atual}-{attempt}"
                # Ajusta para não ficar imenso em casos raros
                if len(ordem_compra_atual) > 20: 
                    ordem_compra_atual = ordem_compra_atual[:18] + f"-{attempt}"

            await _preparar_formulario_pedidos(
                page,
                usuario,
                senha,
                nome_cliente,
                comprador_nome,
                numero_contrato,
                ordem_compra_atual,
                str(item["grupo"]),
            )
            await page.get_by_role("link", name="Itens").click()
            await _click_until_success(page.get_by_role("button", name="Importar"))
            await asyncio.sleep(1)

            await _set_import_file(page, Path(str(item["path"])))

            await _click_until_success(page.get_by_role("button", name="Importar").last, ensure_enabled=True)
            await page.wait_for_load_state("networkidle")
            
            # Checa se deu o infame "Pedido já existe"
            erro_locator = page.locator("td.tdErro", has_text="- Pedido j\u00e1 existe")
            if await erro_locator.count() > 0:
                logger.warning("Pedido ja existe detectado para %s. Iniciando tentativa %d...", item['ordem'], attempt + 1)
                await context.close()
                await browser.close()
                continue
                
            # Se nao deu erro e eh o ultimo...
            if finalizar:
                try:
                    await page.wait_for_selector("text=Controles Finaliza e Envia", state="visible", timeout=5000)
                    await page.get_by_text("Controles Finaliza e Envia").click()
                    await page.wait_for_selector("text=Finaliza e Envia Pedidos", state="visible", timeout=5000)
                except Exception:
                    pass

            item["completed"] = True
            _mark_txt_completed(file_key, registro_base)
            break
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass


async def _executar_importacoes_concorrentes(
    prepared_items: Sequence[MutableMapping[str, object]],
    usuario: str,
    senha: str,
    nome_cliente: str,
    comprador_nome: str,
    numero_contrato: str,
    registro_base: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event=None,
) -> None:
    ordered_items = list(prepared_items)
    total = len(ordered_items)
    completed_count = [0]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BROWSERS)

    async def _item_with_progress(playwright, item, idx: int) -> None:
        async with semaphore:
            await _processar_item_async(
                playwright,
                item,
                usuario,
                senha,
                nome_cliente,
                comprador_nome,
                numero_contrato,
                registro_base,
                delay_seconds=idx * NAVIGATOR_STAGGER_SECONDS,
                finalizar=idx == (total - 1),
                cancel_event=cancel_event,
            )
        completed_count[0] += 1
        logger.info("Finger: item %d/%d concluido (%s)", completed_count[0], total, item.get("ordem", ""))
        if progress_callback:
            try:
                progress_callback(completed_count[0], total)
            except Exception:
                pass

    async with async_playwright() as playwright:
        await asyncio.gather(
            *(_item_with_progress(playwright, item, idx) for idx, item in enumerate(ordered_items))
        )


def cadastrar_pedidos(
    loja: str,
    credenciais: Mapping[str, str],
    dados_ocr: Optional[Mapping[str, str]] = None,
    comprador: str = "",
    itens: Sequence[Tuple[str, str]] = (),
    registro_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event=None,
) -> None:
    if not itens:
        raise ValueError("Informe ao menos um arquivo TXT para importar.")
    if not registro_dir:
        raise ValueError("Informe a pasta selecionada para registrar as importacoes.")

    registro_base = Path(registro_dir).resolve()

    usuario = credenciais.get("username", "").strip()
    senha = credenciais.get("password", "").strip()

    if not usuario or not senha:
        raise ValueError(f"Credenciais de {loja} nao preenchidas em {CONFIG_FILENAME}.")

    nome_cliente = ""
    numero_contrato = ""
    if dados_ocr:
        nome_cliente = str(dados_ocr.get("cliente", "")).strip()
        numero_contrato = str(dados_ocr.get("numero_contrato", "")).strip()
    if not nome_cliente:
        raise ValueError("Nome do cliente nao disponivel. Execute o OCR antes de cadastrar o pedido.")
    if not numero_contrato:
        raise ValueError("Numero de contrato nao disponivel. Execute o OCR antes de cadastrar o pedido.")

    comprador_nome = comprador.strip()
    if not comprador_nome:
        raise ValueError("Informe o comprador antes de cadastrar o pedido.")
    comprador_nome = " ".join(comprador_nome.upper().split())

    prepared_items = []
    for ordem_compra, txt_path in itens:
        ordem_compra_valor = str(ordem_compra or "").strip().upper()
        if not ordem_compra_valor:
            raise ValueError("Informe a ordem de compra para o pedido.")
        arquivo_txt = Path(txt_path).resolve()
        if not arquivo_txt.is_file():
            raise FileNotFoundError(f"Arquivo TXT '{arquivo_txt}' nao encontrado.")
        reservation = _reserve_txt(arquivo_txt, registro_base)
        if not reservation:
            continue
        file_key, _meta = reservation
        prepared_items.append(
            {
                "ordem": ordem_compra_valor,
                "path": arquivo_txt,
                "grupo": determinar_grupo_por_arquivo(str(arquivo_txt)),
                "file_key": file_key,
                "completed": False,
            }
        )

    if not prepared_items:
        raise RuntimeError("Nenhum novo arquivo TXT disponivel para importacao.")

    all_completed = True
    try:
        asyncio.run(
            _executar_importacoes_concorrentes(
                prepared_items,
                usuario,
                senha,
                nome_cliente,
                comprador_nome,
                numero_contrato,
                registro_base,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )
        )
    except Exception:
        all_completed = False
        raise
    finally:
        if all_completed and all(entry["completed"] for entry in prepared_items):
            _cleanup_registry(registro_base)
        else:
            for item in prepared_items:
                if not item["completed"]:
                    _release_txt_reservation(item["file_key"], registro_base)

def cadastrar_pedido(
    loja: str,
    credenciais: Mapping[str, str],
    dados_ocr: Optional[Mapping[str, str]] = None,
    comprador: str = "",
    ordem_compra: str = "",
    txt_path: str = "",
    registro_dir: Optional[str] = None,
) -> None:
    base_dir = registro_dir
    if base_dir is None:
        if not txt_path:
            raise ValueError("Informe o caminho do arquivo TXT para cadastrar o pedido.")
        base_dir = str(Path(txt_path).resolve().parent)
    cadastrar_pedidos(
        loja,
        credenciais,
        dados_ocr=dados_ocr,
        comprador=comprador,
        itens=[(ordem_compra, txt_path)],
        registro_dir=base_dir,
    )

import atexit
import contextlib
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set, Tuple

from playwright.sync_api import Frame, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

try:
    from .cadastro_clientes_finger import CONFIG_FILENAME, ensure_config
except ImportError:  # pragma: no cover
    from cadastro_clientes_finger import CONFIG_FILENAME, ensure_config  # type: ignore

try:
    from .models import ProcessoCancelado
except ImportError:  # pragma: no cover
    from models import ProcessoCancelado  # type: ignore

try:
    from .finger_ocr import extract_contrato_data
except ImportError:  # pragma: no cover
    from finger_ocr import extract_contrato_data  # type: ignore

PORTAL_URL = "https://portal.nobilia.com.br/"
_CODE_PATTERN = re.compile(r"([0-9]{4}[A-Z]{2})", re.I)
_RANGE_SUFFIX_PATTERN = re.compile(r"[^A-Z0-9]([A-Z]{2})(?:[^A-Z0-9]|$)")

logger = logging.getLogger(__name__)


class BrowserClosedError(Exception):
    """Erro lancado quando o navegador foi fechado manualmente pelo usuario."""
    pass


class PromobDesatualizadoError(Exception):
    """Erro lancado quando o portal informa que o PROMOB esta desatualizado."""
    pass


def _is_browser_closed_error(exc: Exception) -> bool:
    """Verifica se a excecao indica que o navegador foi fechado manualmente."""
    msg = str(exc).lower()
    indicators = [
        "browser has been closed",
        "target closed",
        "target page, context or browser has been closed",
        "connection closed",
        "browser.close",
        "protocol error",
        "channel closed",
        "ns_error_",
        "session closed",
    ]
    return any(indicator in msg for indicator in indicators)


def _normalize_spaces(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_only.casefold()


def _resolve_child_dir(parent: Path, target_name: str) -> Path:
    if not parent.exists():
        return parent / target_name
    target_key = _normalize_key(target_name)
    for child in parent.iterdir():
        if child.is_dir() and _normalize_key(child.name) == target_key:
            return child
    return parent / target_name


def _extract_codigo_from_xml(xml_path: Path) -> str:
    """Usa regex r'([0-9]{4}[A-Z]{2})' para encontrar o codigo"""
    match = _CODE_PATTERN.search(xml_path.stem.upper())
    if not match:
        raise ValueError(f"Codigo nao encontrado no arquivo {xml_path.name}.")
    return match.group(1).upper()


def _extract_code_from_path(path: Path) -> Optional[str]:
    try:
        return _extract_codigo_from_xml(path)
    except ValueError:
        return None


def _extract_all_codes_from_promob(promob_path: Path) -> List[str]:
    """Extrai todos os codigos de um arquivo PROMOB, incluindo ranges.

    Exemplos:
      '0000AA.promob'        -> ['0000AA']
      '0000AA - AB.promob'   -> ['0000AA', '0000AB']
      '0000AA-AB-AC.promob'  -> ['0000AA', '0000AB', '0000AC']
      '0000AA 0000AB.promob' -> ['0000AA', '0000AB']
    """
    stem = promob_path.stem.upper()

    # Encontrar todos os codigos completos (4 digitos + 2 letras)
    full_codes = [m.upper() for m in _CODE_PATTERN.findall(stem)]

    if len(full_codes) >= 2:
        # Ja tem 2+ codigos completos no nome
        return list(dict.fromkeys(full_codes))  # preservar ordem, remover duplicatas

    if not full_codes:
        return []

    # Um unico codigo completo encontrado: verificar se ha sufixos de range
    # Ex: '0000AA - AB' → prefixo '0000' + sufixos extras 'AB'
    base_code = full_codes[0]
    prefix = base_code[:4]  # parte numerica

    pos = stem.index(base_code) + len(base_code)
    remainder = stem[pos:]

    extra_suffixes = _RANGE_SUFFIX_PATTERN.findall(remainder)

    codes = [base_code]
    for suffix in extra_suffixes:
        new_code = prefix + suffix.upper()
        if new_code not in codes:
            codes.append(new_code)

    return codes


def _find_xml_and_promob_files(base_dir: Path) -> List[Tuple[Path, Optional[Path]]]:
    """Retorna lista de tuplas (xml_path, Optional[promob_path]).

    Um unico arquivo PROMOB pode servir multiplos XMLs quando o nome
    contem um range de codigos (ex: '0000AA - AB.promob' serve tanto
    '0000AA.xml' quanto '0000AB.xml').
    """
    base_dir = base_dir.resolve()
    executivo_dir = _resolve_child_dir(base_dir, "EXECUTIVO")
    compra_dir = _resolve_child_dir(executivo_dir, "COMPRA")
    xml_root = _resolve_child_dir(compra_dir, "PEDIDOS FABRICAS")
    promob_root = _resolve_child_dir(compra_dir, "PROMOBS ENCOMENDADOS")

    xml_paths: List[Path] = []
    if xml_root.exists():
        xml_paths = sorted(p for p in xml_root.rglob("*.xml") if p.is_file())

    # Indexar PROMOBs: cada codigo encontrado no nome do arquivo aponta
    # para o mesmo caminho. Um PROMOB com range gera multiplas entradas.
    promob_index: Dict[str, Path] = {}
    if promob_root.exists():
        for promob_path in sorted(promob_root.rglob("*.promob")):
            codes = _extract_all_codes_from_promob(promob_path)
            for code in codes:
                if code not in promob_index:
                    promob_index[code] = promob_path
                    logger.info(
                        "PROMOB indexado: codigo %s -> %s", code, promob_path.name,
                    )

    pairs: List[Tuple[Path, Optional[Path]]] = []
    for xml_path in xml_paths:
        try:
            code = _extract_codigo_from_xml(xml_path)
        except ValueError:
            logger.warning("Codigo ausente no XML %s.", xml_path.name)
            code = ""
        promob_path = promob_index.get(code) if code else None
        if promob_path is None and code:
            logger.warning(
                "PROMOB nao localizado para o codigo %s (XML %s).",
                code,
                xml_path.name,
            )
        pairs.append((xml_path, promob_path))

    return pairs


def _wait_for_frame(page: Page) -> Frame:
    iframe_handle = page.wait_for_selector("iframe[name='janela']")
    frame = iframe_handle.content_frame()
    if frame is None:
        raise RuntimeError("Nao foi possivel acessar o iframe 'janela'.")
    return frame


def _login_vitta(page: Page, empresa: str, usuario: str, senha: str) -> None:
    logger.info("Realizando login no portal Vitta.")
    page.goto(PORTAL_URL)

    page.get_by_role("textbox", name=re.compile("Empresa", re.I)).fill(empresa)
    page.get_by_role("textbox", name=re.compile("Usu", re.I)).fill(usuario)
    page.get_by_role("textbox", name=re.compile("Senha", re.I)).fill(senha)
    page.get_by_role("button", name=re.compile("Continuar", re.I)).click()
    page.wait_for_load_state("networkidle")


def _acessar_novo_pedido(page: Page) -> None:
    logger.info("Acessando tela de novo pedido.")
    novo_pedido = page.get_by_role("link", name=re.compile("Novo Pedido", re.I))
    novo_pedido.wait_for()
    novo_pedido.click()


def _selecionar_cliente(page: Page, nome_cliente: str) -> None:
    logger.info("Selecionando cliente '%s'.", nome_cliente)
    buscar_btn = page.get_by_role("button", name="")
    buscar_btn.wait_for()
    buscar_btn.click()

    frame = _wait_for_frame(page)

    filtro = frame.locator("#txtFiltroCliente")
    filtro.wait_for()
    filtro.click()
    filtro.fill(nome_cliente)

    confirmar_btn = frame.get_by_role("button", name="")
    confirmar_btn.wait_for()
    confirmar_btn.click()

    cliente_cell = frame.get_by_role("cell", name=re.compile(re.escape(nome_cliente), re.I))
    cliente_cell.first.wait_for()
    cliente_cell.first.dblclick()
    page.wait_for_load_state("networkidle")


def _preencher_comprador(page: Page, nome_comprador: str) -> None:
    comprador_input = page.get_by_role(
        "textbox",
        name=re.compile(r"Informa\u00e7\u00e3o do Comprador", re.I),
    )
    comprador_input.wait_for()
    comprador_input.click()
    comprador_input.fill(nome_comprador)


def _selecionar_deposito(page: Page) -> None:
    logger.info("Selecionando dep\u00f3sito padr\u00e3o.")
    deposito_link = page.get_by_role("link", name="Selecione o Dep\u00f3sito")
    deposito_link.wait_for()
    deposito_link.click()

    option = page.locator("#select2-result-label-2")
    option.wait_for()
    option.click()


def _prepare_item_form(page: Page, primeira_iteracao: bool) -> Frame:
    if primeira_iteracao:
        incluir_btn = page.get_by_role("button", name="+ Incluir")
        incluir_btn.wait_for()
        incluir_btn.click()

    frame = _wait_for_frame(page)
    descricao = frame.locator("#descricao")
    descricao.wait_for()
    descricao.click()
    return frame


def _upload_arquivo(page: Page, frame: Frame, label: str, file_path: Path) -> None:
    if not file_path.is_file():
        raise FileNotFoundError(f"Arquivo nao encontrado: {file_path}")
    logger.info("Anexando %s: %s", label, file_path.name)
    with page.expect_file_chooser() as chooser_info:
        frame.get_by_text(label, exact=False).click()
    chooser_info.value.set_files(str(file_path))


def _salvar_e_criar_novo(frame: Frame) -> None:
    salvar_btn = frame.get_by_role("button", name=" Salvar e Criar Novo")
    salvar_btn.wait_for()
    salvar_btn.click()


def _check_error_dialog(
    page: Page,
    frame: Frame,
) -> Optional[str]:
    """Verifica se apareceu um dialogo de erro apos salvar.

    Retorna a mensagem de erro se encontrada, None caso contrario.
    Fecha o dialogo automaticamente se encontrado.
    """
    # O dialogo jQuery UI pode aparecer na page ou no frame
    for context in (page, frame):
        try:
            dialog = context.query_selector("#dialogInfo")
            if dialog is None:
                continue
            msg_el = context.locator("#dialogInfo #message")
            msg_text = (msg_el.text_content() or "").strip()
            if msg_text:
                # Fechar o dialogo clicando no botao 'Fechar'
                with contextlib.suppress(Exception):
                    context.locator(
                        ".ui-dialog-buttonset button, .ui-dialog-titlebar-close"
                    ).first.click()
                return msg_text
        except PlaywrightTimeoutError:
            continue
    return None


def _finalizar_operacao(page: Page, ui_confirm=None) -> bool:
    """Pergunta ao usuario se deseja finalizar o pedido.

    Retorna True se o navegador deve ser fechado (usuario confirmou),
    False se o usuario optou por manter o navegador aberto.

    Se ``ui_confirm`` for fornecido, usa esse callback para exibir a
    pergunta na UI Flet em vez de usar tkinter.
    """
    if ui_confirm is not None:
        try:
            resposta = ui_confirm(
                "Finalizar pedido",
                "Todos os itens foram importados.\n\nDeseja finalizar e salvar o pedido no portal Vitta?",
            )
        except Exception as exc:
            logger.warning("Nao foi possivel exibir o prompt de confirmacao: %s", exc)
            resposta = True
    else:
        import tkinter as tk
        from tkinter import messagebox

        resposta = True
        root: Optional[tk.Tk] = None
        try:
            root = tk.Tk()
            root.withdraw()
            resposta = messagebox.askyesno(
                "Finalizar pedido",
                "Todos os itens foram importados.\n\nDeseja finalizar e salvar o pedido no portal Vitta?",
            )
        except Exception as exc:
            logger.warning("Nao foi possivel exibir o prompt de confirmacao: %s", exc)
        finally:
            if root is not None:
                with contextlib.suppress(Exception):
                    root.destroy()

    if resposta:
        # Fechar iframe aberto (se houver) e salvar o pedido
        try:
            frame = _wait_for_frame(page)
        except PlaywrightTimeoutError:
            frame = None

        if frame is not None:
            try:
                fechar_btn = frame.get_by_role("button", name=" Fechar")
                fechar_btn.wait_for()
                fechar_btn.click()
                with contextlib.suppress(PlaywrightTimeoutError):
                    page.wait_for_load_state("domcontentloaded")
            except PlaywrightTimeoutError:
                logger.warning("Botao 'Fechar' nao localizado apos processamento.")
            except Exception as exc:
                logger.exception("Falha ao acionar botao 'Fechar': %s", exc)

        try:
            salvar_btn = page.get_by_role("button", name=" Salvar")
            salvar_btn.wait_for()
            salvar_btn.click()
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle")
        except PlaywrightTimeoutError:
            logger.warning("Botao 'Salvar' nao localizado apos finalizar pedidos.")
        except Exception as exc:
            logger.exception("Falha ao acionar botao 'Salvar': %s", exc)

        # Usuario confirmou: fechar navegador
        return True
    else:
        logger.info(
            "Usuario optou por nao salvar automaticamente; navegador permanecera aberto para conferencia."
        )
        # Usuario nao confirmou: manter navegador aberto
        return False


def _processar_item(
    page: Page,
    xml_path: Path,
    promob_path: Optional[Path],
    primeira_iteracao: bool,
) -> None:
    frame = _prepare_item_form(page, primeira_iteracao)
    # Usar apenas o nome do arquivo sem a extensao .xml na descricao
    frame.locator("#descricao").fill(xml_path.stem)

    try:
        _upload_arquivo(page, frame, "Inserir .XML", xml_path)
        if promob_path is None:
            raise FileNotFoundError(f"Arquivo PROMOB correspondente nao encontrado para {xml_path.name}.")
        _upload_arquivo(page, frame, "Inserir .PROMOB", promob_path)

        # Verificar sem espera fixa apos importar o PROMOB.
        error_msg = _check_error_dialog(page, frame)
        if error_msg:
            if "promob" in error_msg.lower() or "desatualizado" in error_msg.lower():
                raise PromobDesatualizadoError(
                    f"PROMOB desatualizado para {xml_path.stem}: {error_msg}"
                )
            else:
                raise RuntimeError(f"Erro ao processar {xml_path.stem}: {error_msg}")

        _salvar_e_criar_novo(frame)

        # Verificar tambem apos salvar (outros erros possiveis)
        error_msg = _check_error_dialog(page, frame)
        if error_msg:
            raise RuntimeError(f"Erro ao salvar {xml_path.stem}: {error_msg}")

    except (PromobDesatualizadoError, FileNotFoundError):
        raise
    except Exception:
        with contextlib.suppress(Exception):
            frame.get_by_role("button", name=re.compile("Cancelar|Fechar", re.I)).click()
        raise


def _write_execution_log(base_dir: Path, itens: List[Dict[str, str]]) -> Path:
    payload = {
        "data_execucao": datetime.now(timezone.utc).isoformat(),
        "itens_processados": itens,
    }
    log_path = base_dir / "pedidos_vitta_log.json"
    log_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    logger.info("Log de execucao gravado em %s", log_path)
    return log_path


def cadastrar_pedidos_vitta(
    credenciais: Mapping[str, str],
    base_dir: Path,
    nome_comprador: str,
    nome_cliente: str,
    ui_confirm=None,
    ui_warn=None,
    cancel_event=None,
) -> None:
    """Fluxo principal de importacao dos pedidos Vitta"""
    if not isinstance(base_dir, Path):
        base_dir = Path(base_dir)
    if not base_dir.is_dir():
        raise NotADirectoryError(f"{base_dir} nao e uma pasta valida.")

    config_data = ensure_config(include_meta=True)
    ocr_config = config_data.get("ocr", {})
    vitta_config = config_data.get("vitta", {})
    settings_config = config_data.get("settings", {}) if isinstance(config_data, dict) else {}

    resolved_creds: Dict[str, str] = {}
    for key in ("empresa", "username", "password"):
        candidate = _normalize_spaces(str(credenciais.get(key, ""))) if credenciais else ""
        if not candidate and isinstance(vitta_config, Mapping):
            candidate = _normalize_spaces(str(vitta_config.get(key, "")))
        if not candidate:
            raise ValueError(f"Campo '{key}' de Vitta nao definido em {CONFIG_FILENAME}.")
        resolved_creds[key] = candidate

    logger.info("Processando pasta base: %s", base_dir)
    pdf_path, ocr_results = extract_contrato_data(base_dir, ocr_config)
    logger.info("Contrato identificado: %s", pdf_path.name)

    nome_cliente_ocr = _normalize_spaces(ocr_results.get("cliente", ""))
    cliente_final = nome_cliente_ocr or _normalize_spaces(nome_cliente)
    if not cliente_final:
        raise ValueError("Nao foi possivel identificar o nome do cliente a partir do contrato.")
    if not nome_cliente_ocr and nome_cliente:
        logger.warning("Nome do cliente do OCR nao encontrado; utilizando valor informado manualmente.")
    else:
        logger.info("Nome do cliente via OCR: %s", cliente_final)

    comprador_final = _normalize_spaces(nome_comprador) or cliente_final
    if not comprador_final:
        raise ValueError("Informe o nome do comprador para o cadastro Vitta.")

    xml_pairs = _find_xml_and_promob_files(base_dir)

    duplicates: List[Tuple[Path, Optional[Path]]] = []
    filtered_pairs: List[Tuple[Path, Optional[Path]]] = []
    seen_xml: Set[str] = set()
    for xml_path, promob_path in xml_pairs:
        key = xml_path.name.lower()
        if key in seen_xml:
            duplicates.append((xml_path, promob_path))
            logger.warning("Arquivo XML duplicado ignorado: %s", xml_path.name)
            continue
        seen_xml.add(key)
        filtered_pairs.append((xml_path, promob_path))

    xml_pairs = filtered_pairs
    if not xml_pairs:
        raise RuntimeError("Nenhum arquivo XML encontrado em PEDIDOS FABRICAS.")

    itens_log: List[Dict[str, str]] = []
    promob_errors: List[str] = []
    import os
    _env_val = os.environ.get("VITTA_BROWSER_VISIBLE")
    browser_visible = (_env_val != "N") if _env_val else (
        str(settings_config.get("vitta_browser_visible", "Y")).strip().upper() != "N"
    )

    # Usar gerenciamento manual do Playwright para poder manter o navegador aberto
    # quando o usuario optar por nao finalizar o pedido automaticamente.
    playwright_inst = sync_playwright().start()
    browser = None
    context = None
    page = None
    should_close = True  # Por padrao fecha tudo ao terminar

    try:
        browser = playwright_inst.chromium.launch(
            channel='chrome',
            headless=not browser_visible,
            slow_mo=50 if browser_visible else 0,
        )
        context = browser.new_context()
        page = context.new_page()

        _login_vitta(page, resolved_creds["empresa"], resolved_creds["username"], resolved_creds["password"])
        _acessar_novo_pedido(page)
        _selecionar_cliente(page, cliente_final)
        _preencher_comprador(page, comprador_final)
        _selecionar_deposito(page)

        for idx, (xml_path, promob_path) in enumerate(xml_pairs):
            if cancel_event is not None and cancel_event.is_set():
                raise ProcessoCancelado("Processo cancelado pelo usuario.")

            try:
                codigo = _extract_codigo_from_xml(xml_path)
            except ValueError:
                codigo = ""
            promob_nome = promob_path.name if promob_path else (f"{codigo}.promob" if codigo else "")

            item_entry: Dict[str, str] = {
                "xml": xml_path.name,
                "promob": promob_nome,
                "status": "ok",
            }

            try:
                _processar_item(page, xml_path, promob_path, idx == 0)
            except PromobDesatualizadoError as exc:
                item_entry["status"] = "erro"
                item_entry["motivo"] = str(exc)
                itens_log.append(item_entry)
                promob_errors.append(f"{xml_path.stem}: PROMOB desatualizado")
                logger.error("PROMOB desatualizado para %s: %s", xml_path.name, exc)
                continue
            except FileNotFoundError as exc:
                item_entry["status"] = "erro"
                item_entry["motivo"] = str(exc)
                itens_log.append(item_entry)
                logger.error("Arquivo ausente para %s: %s", xml_path.name, exc)
                continue
            except PlaywrightTimeoutError as exc:
                item_entry["status"] = "erro"
                item_entry["motivo"] = f"Timeout: {exc}"
                itens_log.append(item_entry)
                logger.error("Timeout processando %s: %s", xml_path.name, exc)
                continue
            except Exception as exc:
                if _is_browser_closed_error(exc):
                    raise BrowserClosedError("Navegador fechado pelo usuario.") from exc
                item_entry["status"] = "erro"
                item_entry["motivo"] = str(exc)
                itens_log.append(item_entry)
                logger.exception("Falha ao processar %s", xml_path.name)
                continue
            else:
                itens_log.append(item_entry)

        # Se houve erros de PROMOB desatualizado, alertar o usuario
        if promob_errors:
            erros_texto = "\n".join(f"  - {e}" for e in promob_errors)
            msg_promob = (
                f"Alguns itens apresentaram erro de PROMOB desatualizado:\n\n"
                f"{erros_texto}\n\n"
                f"Verifique a atualizacao dos arquivos PROMOB."
            )
            if ui_warn is not None:
                try:
                    ui_warn("PROMOB Desatualizado", msg_promob)
                except Exception:
                    logger.warning("Falha ao exibir aviso PROMOB na UI: %s", msg_promob)
            else:
                import tkinter as tk
                from tkinter import messagebox
                alert_root: Optional[tk.Tk] = None
                try:
                    alert_root = tk.Tk()
                    alert_root.withdraw()
                    messagebox.showwarning("PROMOB Desatualizado", msg_promob)
                except Exception:
                    pass
                finally:
                    if alert_root is not None:
                        with contextlib.suppress(Exception):
                            alert_root.destroy()

        # Perguntar ao usuario se deseja finalizar o pedido.
        # Retorna True = fechar navegador, False = manter aberto.
        should_close = _finalizar_operacao(page, ui_confirm=ui_confirm)

    except ProcessoCancelado:
        should_close = True
        logger.info("Processo cancelado pelo usuario.")
        raise
    except BrowserClosedError:
        # Navegador fechado manualmente: nao mostrar popup de erro
        should_close = True
        logger.info("Navegador foi fechado manualmente pelo usuario.")
        raise
    except Exception as exc:
        if _is_browser_closed_error(exc):
            # Navegador fechado manualmente: nao mostrar popup de erro
            should_close = True
            logger.info("Navegador foi fechado manualmente pelo usuario.")
            raise BrowserClosedError("Navegador fechado pelo usuario.") from exc
        else:
            should_close = True
            raise
    finally:
        if should_close:
            if context is not None:
                with contextlib.suppress(Exception):
                    context.close()
            if browser is not None:
                with contextlib.suppress(Exception):
                    browser.close()
            with contextlib.suppress(Exception):
                playwright_inst.stop()
        else:
            logger.info("Navegador mantido aberto conforme escolha do usuario.")
            # Registrar cleanup para quando a aplicação encerrar,
            # evitando processos Chromium zumbis.
            _pi = playwright_inst
            def _cleanup_playwright() -> None:
                with contextlib.suppress(Exception):
                    _pi.stop()
            atexit.register(_cleanup_playwright)

    for xml_path, promob_path in duplicates:
        itens_log.append({
            "xml": xml_path.name,
            "promob": promob_path.name if promob_path else "",
            "status": "ignorado",
            "motivo": "arquivo xml duplicado ignorado",
        })

    _write_execution_log(base_dir, itens_log)

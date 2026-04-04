"""Camada de serviço — fachada sobre os módulos de backend."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .cadastro_clientes_finger import (
    STORES,
    OCR_FIELD_KEYS,
    OCR_FIELD_LABELS,
    cadastrar_cliente,
    ensure_config,
    get_contact_settings,
    open_config_file,
)
from .cadastro_clientes_vitta import cadastrar_cliente_vitta
from .cadastro_pedidos_finger import cadastrar_pedidos
from .cadastro_pedidos_vitta import cadastrar_pedidos_vitta, _find_xml_and_promob_files
from .finger_ocr import extract_contrato_data
from .enviar_pedidos_email import (
    scan_pdf_orders,
    extract_client_code,
    build_email_subject,
    build_email_body,
    send_pdf_email,
    mark_email_sent,
    unmark_email_sent,
)
from .models import AppState, ConfigData, FolderScanResult


def load_config() -> ConfigData:
    """Carrega lojas.config e retorna ConfigData."""
    raw = ensure_config(include_meta=True)
    contacts = dict(get_contact_settings(raw))
    return ConfigData(
        stores=raw["stores"],
        ocr=raw.get("ocr", {}),
        vitta=dict(raw.get("vitta", {"empresa": "", "username": "", "password": ""})),
        email_smtp=dict(raw.get("email_smtp", {
            "host": "smtp.exemplo.com.br", "port": 587,
            "use_tls": True, "destino_fixo": "pedidos@exemplo.com.br",
        })),
        usuarios_email=dict(raw.get("usuarios_email", {})),
        empresa_info=dict(raw.get("empresa_info", {"codigo": "274", "nome": "EDY SERVICOS EM MOVEIS LTDA"})),
        fornecedores_email=dict(raw.get("fornecedores_email", {})),
        settings=raw.get("settings", {}),
        contacts=contacts,
    )


def apply_browser_settings(cfg: ConfigData) -> None:
    """Aplica configurações de visibilidade do browser nas env vars."""
    finger = str(cfg.settings.get("finger_browser_visible", "Y")).strip().upper()
    vitta = str(cfg.settings.get("vitta_browser_visible", "Y")).strip().upper()
    os.environ["FINGER_BROWSER_VISIBLE"] = finger
    os.environ["VITTA_BROWSER_VISIBLE"] = vitta
    os.environ["NAVEGADOR_VISIVEL"] = finger


def scan_folder_files(folder_path: Path, cfg: ConfigData) -> FolderScanResult:
    """Escaneia arquivos do projeto sem rerodar OCR do contrato."""
    folder_path = folder_path.resolve()
    if not folder_path.is_dir():
        raise NotADirectoryError("Selecione uma pasta válida.")

    txt_files = sorted(folder_path.rglob("*.txt"))
    vitta_pairs = _find_xml_and_promob_files(folder_path)
    vitta_xml_files = [xml for (xml, _) in vitta_pairs]

    config_snap = {"fornecedores_email": dict(cfg.fornecedores_email)}
    found_pdfs = scan_pdf_orders(folder_path, config_snap)

    return FolderScanResult(
        txt_files=txt_files,
        vitta_xml_files=vitta_xml_files,
        pdf_orders=found_pdfs,
    )


def process_folder(folder_path: Path, cfg: ConfigData) -> FolderScanResult:
    """Processa pasta de projeto: OCR, TXT, XML, PDFs."""
    folder_path = folder_path.resolve()
    if not folder_path.is_dir():
        raise NotADirectoryError("Selecione uma pasta válida.")

    pdf_path, results = extract_contrato_data(folder_path, cfg.ocr)
    file_scan = scan_folder_files(folder_path, cfg)

    ocr_results = {key: results.get(key, "") for key in OCR_FIELD_KEYS}

    return FolderScanResult(
        ocr_results=ocr_results,
        txt_files=file_scan.txt_files,
        vitta_xml_files=file_scan.vitta_xml_files,
        contract_pdf_path=pdf_path,
        pdf_orders=file_scan.pdf_orders,
    )


def run_finger_clients(
    store: str,
    creds: Dict[str, str],
    ocr_snapshot: Dict[str, str],
) -> None:
    """Cadastra cliente no portal Finger."""
    cadastrar_cliente(store, creds, dados_ocr=ocr_snapshot)


def run_finger_orders(
    store: str,
    creds: Dict[str, str],
    ocr_snapshot: Dict[str, str],
    comprador: str,
    txt_files: List[Path],
    registro_dir: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_event=None,
) -> None:
    """Cadastra pedidos no portal Finger."""
    itens = [(Path(p).stem.upper(), str(p)) for p in txt_files]
    cadastrar_pedidos(
        store, creds, dados_ocr=ocr_snapshot,
        comprador=comprador, itens=itens,
        registro_dir=registro_dir,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )


def run_vitta_clients(
    creds: Dict[str, str],
    dados_cliente: Dict[str, str],
) -> None:
    """Cadastra cliente no portal Vitta."""
    cadastrar_cliente_vitta(creds, dados_cliente)


def run_vitta_orders(
    creds: Dict[str, str],
    base_path: Path,
    comprador: str,
    cliente_nome: str,
    ui_confirm=None,
    ui_warn=None,
    cancel_event=None,
) -> None:
    """Cadastra pedidos no portal Vitta."""
    cadastrar_pedidos_vitta(creds, base_path, comprador, cliente_nome,
                            ui_confirm=ui_confirm, ui_warn=ui_warn,
                            cancel_event=cancel_event)


def send_order_email(
    smtp_config: Dict[str, Any],
    sender: str,
    password: str,
    recipients: List[str],
    subject: str,
    body: str,
    pdf_path: Path,
) -> None:
    """Envia um e-mail de pedido PDF."""
    send_pdf_email(smtp_config, sender, password, recipients, subject, body, pdf_path)


def refresh_pdf_orders(folder_path: Path, cfg: ConfigData) -> List[Dict[str, Any]]:
    """Re-escaneia PDFs de pedido com status atualizado."""
    return scan_folder_files(folder_path, cfg).pdf_orders

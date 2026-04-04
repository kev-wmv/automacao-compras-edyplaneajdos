"""Dataclasses centralizadas para estado e configuração da aplicação."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProcessoCancelado(Exception):
    """Lançado quando o usuário cancela o processo em execução."""


@dataclass
class ConfigData:
    """Dados carregados do lojas.config."""
    stores: Dict[str, Dict[str, str]] = field(default_factory=dict)
    ocr: Dict[str, Any] = field(default_factory=dict)
    vitta: Dict[str, str] = field(default_factory=lambda: {"empresa": "", "username": "", "password": ""})
    email_smtp: Dict[str, Any] = field(default_factory=lambda: {
        "host": "smtp.exemplo.com.br", "port": 587,
        "use_tls": True, "destino_fixo": "pedidos@exemplo.com.br",
    })
    usuarios_email: Dict[str, str] = field(default_factory=dict)
    empresa_info: Dict[str, str] = field(default_factory=lambda: {"codigo": "274", "nome": "EDY SERVICOS EM MOVEIS LTDA"})
    fornecedores_email: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, str] = field(default_factory=lambda: {
        "finger_browser_visible": "Y",
        "vitta_browser_visible": "Y",
    })
    contacts: Dict[str, str] = field(default_factory=lambda: {
        "pedidos_email": "pedidos@exemplo.com.br",
        "fiscal_email": "fiscal@exemplo.com.br",
    })


@dataclass
class FolderScanResult:
    """Resultado do processamento de uma pasta de projeto."""
    ocr_results: Dict[str, str] = field(default_factory=dict)
    txt_files: List[Path] = field(default_factory=list)
    vitta_xml_files: List[Path] = field(default_factory=list)
    contract_pdf_path: Optional[Path] = None
    pdf_orders: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class AppState:
    """Estado mutável da aplicação."""
    selected_store: str = ""
    fabricante: str = "Finger"
    action: str = "clientes"
    vitta_action: str = "clientes"
    comprador: str = ""
    headless: bool = True

    # Resultado do scan de pasta
    folder_path: Optional[Path] = None
    ocr_results: Dict[str, str] = field(default_factory=dict)
    txt_files: List[Path] = field(default_factory=list)
    vitta_xml_files: List[Path] = field(default_factory=list)
    contract_pdf_path: Optional[Path] = None
    pdf_orders: List[Dict[str, Any]] = field(default_factory=list)

    # Config carregada
    config: Optional[ConfigData] = None

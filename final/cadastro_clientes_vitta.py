import contextlib
import re
from typing import Mapping, Optional
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

try:
    from .cadastro_clientes_finger import CONFIG_FILENAME, ensure_config, get_contact_settings
except ImportError:  # pragma: no cover
    from cadastro_clientes_finger import CONFIG_FILENAME, ensure_config, get_contact_settings  # type: ignore

PORTAL_URL = "https://portal.nobilia.com.br/"
ACTIVE_PLAYWRIGHT = None
ACTIVE_BROWSER = None
ACTIVE_CONTEXT = None
ACTIVE_PAGE = None

_VITTA_BROWSER_VISIBLE: Optional[bool] = None


def _vitta_browser_visible() -> bool:
    import os
    env_val = os.environ.get("VITTA_BROWSER_VISIBLE")
    if env_val:
        return env_val != "N"
    global _VITTA_BROWSER_VISIBLE
    if _VITTA_BROWSER_VISIBLE is None:
        try:
            config_data = ensure_config(include_meta=True)  # type: ignore[arg-type]
        except Exception:
            _VITTA_BROWSER_VISIBLE = True
        else:
            settings = config_data.get("settings", {}) if isinstance(config_data, dict) else {}
            value = str(settings.get("vitta_browser_visible", "Y")).strip().upper()
            _VITTA_BROWSER_VISIBLE = value != "N"
    return _VITTA_BROWSER_VISIBLE


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _fechar_browser_global() -> None:
    """Fecha e limpa todos os recursos globais do Playwright."""
    global ACTIVE_PLAYWRIGHT, ACTIVE_BROWSER, ACTIVE_CONTEXT, ACTIVE_PAGE
    with contextlib.suppress(Exception):
        if ACTIVE_PAGE is not None:
            ACTIVE_PAGE.close()
    with contextlib.suppress(Exception):
        if ACTIVE_CONTEXT is not None:
            ACTIVE_CONTEXT.close()
    with contextlib.suppress(Exception):
        if ACTIVE_BROWSER is not None:
            ACTIVE_BROWSER.close()
    with contextlib.suppress(Exception):
        if ACTIVE_PLAYWRIGHT is not None:
            ACTIVE_PLAYWRIGHT.stop()
    ACTIVE_PLAYWRIGHT = None
    ACTIVE_BROWSER = None
    ACTIVE_CONTEXT = None
    ACTIVE_PAGE = None


def cadastrar_cliente_vitta(
    credenciais: Mapping[str, str],
    dados_cliente: Mapping[str, str],
) -> None:
    empresa = _normalize_text(credenciais.get("empresa", ""))
    usuario = _normalize_text(credenciais.get("username", ""))
    senha = str(credenciais.get("password", ""))

    if not empresa or not usuario or not senha:
        raise ValueError(f"Credenciais de acesso Vitta nao definidas em {CONFIG_FILENAME}.")

    nome = _normalize_text(dados_cliente.get("nome") or dados_cliente.get("cliente"))
    if not nome:
        raise ValueError("Informe o nome do cliente antes de cadastrar no portal Vitta.")

    cpf = _normalize_digits(dados_cliente.get("cpf") or dados_cliente.get("cpf_cnpj"))
    if len(cpf) < 11:
        raise ValueError("Informe um CPF valido com pelo menos 11 digitos para cadastro Vitta.")

    contact_settings = get_contact_settings()
    contato = _normalize_text(
        dados_cliente.get("contato") or contact_settings.get("pedidos_email") or nome
    )
    telefone = _normalize_digits(dados_cliente.get("telefone"))
    celular = _normalize_digits(dados_cliente.get("celular"))
    email = _normalize_text(dados_cliente.get("email") or contact_settings.get("fiscal_email"))
    cep = _normalize_digits(dados_cliente.get("cep"))
    numero = _normalize_text(dados_cliente.get("numero"))
    complemento = _normalize_text(dados_cliente.get("complemento"))
    endereco = _normalize_text(
        dados_cliente.get("endereco") or dados_cliente.get("endereco_entrega")
    )
    bairro = _normalize_text(dados_cliente.get("bairro"))
    cidade = _normalize_text(dados_cliente.get("cidade"))
    estado = _normalize_text(dados_cliente.get("estado") or dados_cliente.get("uf")).upper()

    browser_visible = _vitta_browser_visible()

    if not telefone and not celular:
        raise ValueError("Informe ao menos um telefone ou celular para o cadastro Vitta.")
    if not email:
        raise ValueError("Informe um e-mail valido para o cadastro Vitta.")
    if len(cep) != 8:
        raise ValueError("Informe um CEP com 8 digitos para o cadastro Vitta.")

    global ACTIVE_PLAYWRIGHT, ACTIVE_BROWSER, ACTIVE_CONTEXT, ACTIVE_PAGE

    if ACTIVE_PLAYWRIGHT is None:
        ACTIVE_PLAYWRIGHT = sync_playwright().start()

    browser_connected = (
        ACTIVE_BROWSER is not None and getattr(ACTIVE_BROWSER, "is_connected", lambda: True)()
    )
    if not browser_connected:
        ACTIVE_BROWSER = ACTIVE_PLAYWRIGHT.chromium.launch(channel='chrome', headless=not browser_visible)
        ACTIVE_CONTEXT = None

    context_closed = (
        ACTIVE_CONTEXT is not None and getattr(ACTIVE_CONTEXT, "is_closed", lambda: False)()
    )
    if ACTIVE_CONTEXT is None or context_closed:
        ACTIVE_CONTEXT = ACTIVE_BROWSER.new_context()

    page = ACTIVE_CONTEXT.new_page()
    ACTIVE_PAGE = page

    _cpf_duplicado = False

    _browser_fechado = False
    _CLOSED_INDICATORS = [
        "browser has been closed", "target closed", "connection closed",
        "protocol error", "channel closed", "session closed",
    ]

    try:
        page.goto(PORTAL_URL)
        page.get_by_role("textbox", name=re.compile("Empresa", re.I)).fill(empresa)
        page.get_by_role("textbox", name=re.compile("Usu", re.I)).fill(usuario)
        page.get_by_role("textbox", name=re.compile("Senha", re.I)).fill(senha)
        page.get_by_role("button", name=re.compile("Continuar", re.I)).click()

        page.get_by_role("link", name=re.compile("Cadastro", re.I)).click()
        page.get_by_role("link", name=re.compile("Cliente", re.I)).click()
        page.get_by_role("button").filter(has_text=re.compile("Criar", re.I)).click()

        frame = page.frame(name="janela")
        if frame is None:
            raise RuntimeError("Nao foi possivel localizar o formulario de cliente (iframe 'janela').")

        frame.get_by_role("textbox", name=re.compile("Nome", re.I)).fill(nome)
        frame.get_by_role("textbox", name=re.compile("CPF", re.I)).fill(cpf)
        frame.get_by_role("textbox", name=re.compile("CPF", re.I)).press(" ")  # Forcar validacao do CPF

        # Verificar se o CPF ja esta cadastrado logo apos o preenchimento
        try:
            frame.wait_for_selector("#dialogInfo", timeout=100)
            msg_text = (frame.locator("#dialogInfo #message").text_content(timeout=100) or "").strip()
            if "cadastrado" in msg_text.lower():
                _cpf_duplicado = True
        except PlaywrightTimeoutError:
            pass

        if not _cpf_duplicado:
            frame.get_by_role("textbox", name=re.compile("Contato", re.I)).fill(contato)
            frame.get_by_role("textbox", name=re.compile("Telefone", re.I)).fill(telefone or celular)
            frame.get_by_role("textbox", name=re.compile("Telefone", re.I)).press(" ")  # Forcar validacao do telefone
            frame.get_by_role("textbox", name=re.compile("Celular", re.I)).fill(telefone or celular)
            frame.get_by_role("textbox", name=re.compile("Celular", re.I)).press(" ")  # Forcar validacao do celular
            frame.get_by_role("textbox", name=re.compile("Email", re.I)).fill(email)
            frame.get_by_role("textbox", name=re.compile("CEP", re.I)).fill(cep)
            frame = page.frame(name="janela")
            frame.get_by_role("button", name="").click()
            frame.get_by_role("textbox", name=re.compile("CEP", re.I)).press(" ")  # Forcar validacao do CEP
            frame.get_by_role("button", name=re.compile("Fechar", re.I))
            frame.get_by_role("textbox", name=re.compile("Nº", re.I)).fill(numero or "S/N")
            frame.get_by_role("textbox", name=re.compile("Complemento", re.I)).fill(complemento)
            frame.get_by_role("button", name=" Salvar", exact=True).click()

            # Verificar novamente apos o Salvar
            try:
                frame.wait_for_selector("#dialogInfo", timeout=100)
                msg_text = (frame.locator("#dialogInfo #message").text_content(timeout=100) or "").strip()
                if "cadastrado" in msg_text.lower():
                    _cpf_duplicado = True
            except PlaywrightTimeoutError:
                pass

    except Exception as exc:
        msg_lower = str(exc).lower()
        if any(ind in msg_lower for ind in _CLOSED_INDICATORS):
            _browser_fechado = True
            # Propagar o erro para que o UI não mostre mensagem de sucesso
            raise RuntimeError("Navegador fechado pelo usuario.") from exc
        else:
            raise
    finally:
        if not _browser_fechado:
            _fechar_browser_global()

    if _cpf_duplicado:
        raise ValueError("cpf ja cadastrado no portal vitta")

"""Sessão de administração — edita a config central (Gist) e propaga a todos.

Só abre em máquinas com credencial de admin (token de escrita local). Edita
fornecedores, credenciais de loja e e-mail; ao salvar, publica no Gist e o
próximo startup de cada usuário puxa a versão nova.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import flet as ft

from ..theme import (
    ACCENT, C_ON_SURFACE, C_ON_SURFACE_VARIANT, C_PRIMARY, C_ON_PRIMARY,
    C_OUTLINE, C_SURFACE_CONTAINER,
)
from ..state import AppController
from ...cadastro_clientes_finger import ensure_config, save_config, STORES
from ...services import load_config
from ...remote_config import has_admin_access


def _tf(label: str, value: str, width=None, password=False) -> ft.TextField:
    return ft.TextField(
        label=label,
        value=value or "",
        password=password,
        can_reveal_password=password,
        text_size=13,
        height=44,
        width=width,
        border_color=C_OUTLINE,
        focused_border_color=ACCENT,
        color=C_ON_SURFACE,
        label_style=ft.TextStyle(size=11, color=C_ON_SURFACE_VARIANT),
        border_radius=6,
        expand=width is None,
    )


def show_admin_dialog(ctrl: AppController) -> None:
    """Abre a sessão de administração da config central."""
    if not has_admin_access():
        ctrl._alert(
            "Acesso restrito",
            "Esta máquina não tem credencial de administrador.\n"
            "A configuração central só pode ser editada na estação autorizada.",
        )
        return

    # Config fresca do gist (não o snapshot em memória) para não sobrescrever
    # edições feitas de outra máquina no intervalo.
    try:
        data = ensure_config(include_meta=True)
    except Exception as exc:  # noqa: BLE001
        ctrl._alert("Erro", f"Não foi possível carregar a configuração:\n{exc}")
        return

    stores: Dict[str, dict] = data.setdefault("stores", {})
    fornecedores: Dict[str, list] = data.setdefault("fornecedores_email", {})
    smtp: Dict[str, object] = data.setdefault("email_smtp", {})
    usuarios: Dict[str, str] = data.setdefault("usuarios_email", {})

    # ── Aba Fornecedores ────────────────────────────────────────────────────
    forn_rows = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO)
    forn_refs: List[Tuple[ft.TextField, ft.TextField]] = []

    def _add_forn(nome: str = "", emails: str = "") -> None:
        nome_f = _tf("Fornecedor", nome, width=150)
        emails_f = _tf("E-mails (separados por vírgula)", emails)
        row_holder = ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ref = (nome_f, emails_f)
        forn_refs.append(ref)

        def _remove(_):
            forn_refs.remove(ref)
            forn_rows.controls.remove(row_holder)
            ctrl.page.update()

        row_holder.controls.extend([
            nome_f, emails_f,
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                          icon_color=C_ON_SURFACE_VARIANT, tooltip="Remover",
                          on_click=_remove),
        ])
        forn_rows.controls.append(row_holder)

    for nome, emails in sorted(fornecedores.items()):
        _add_forn(nome, ", ".join(str(e) for e in emails if str(e).strip()))

    forn_tab = ft.Column([
        ft.Text("Cada fornecedor e seus e-mails de CC no envio de pedidos.",
                size=11, color=C_ON_SURFACE_VARIANT),
        forn_rows,
        ft.TextButton(
            "Adicionar fornecedor", icon=ft.Icons.ADD,
            on_click=lambda _: (_add_forn(), ctrl.page.update()),
        ),
    ], spacing=8, scroll=ft.ScrollMode.AUTO)

    # ── Aba Lojas ────────────────────────────────────────────────────────────
    loja_refs: Dict[str, Dict[str, ft.TextField]] = {}
    loja_controls = []
    for store in STORES:
        block = stores.get(store, {})
        user_f = _tf("Usuário", str(block.get("username", "")), width=170)
        pass_f = _tf("Senha", str(block.get("password", "")), width=170, password=True)
        cf_f = _tf("Cliente fixo (Finger)", str(block.get("cliente_fixo", "")))
        cfv_f = _tf("Cliente fixo (Vitta)", str(block.get("cliente_fixo_vitta", "")))
        loja_refs[store] = {"username": user_f, "password": pass_f,
                            "cliente_fixo": cf_f, "cliente_fixo_vitta": cfv_f}
        loja_controls.append(ft.Container(
            content=ft.Column([
                ft.Text(store, size=12, weight=ft.FontWeight.W_600, color=C_ON_SURFACE),
                ft.Row([user_f, pass_f], spacing=6),
                ft.Row([cf_f, cfv_f], spacing=6),
            ], spacing=6),
            padding=10,
            border=ft.border.all(1, C_OUTLINE),
            border_radius=8,
        ))
    lojas_tab = ft.Column(loja_controls, spacing=8, scroll=ft.ScrollMode.AUTO)

    # ── Aba E-mail ───────────────────────────────────────────────────────────
    destino_f = _tf("Destino fixo (TO dos pedidos)", str(smtp.get("destino_fixo", "")))
    host_f = _tf("Servidor SMTP", str(smtp.get("host", "")), width=200)
    port_f = _tf("Porta", str(smtp.get("port", "")), width=90)

    usuarios_rows = ft.Column(spacing=6)
    usuarios_refs: List[Tuple[ft.TextField, ft.TextField]] = []

    def _add_user(email: str = "", senha: str = "") -> None:
        email_f = _tf("E-mail do liberador", email)
        senha_f = _tf("Senha SMTP", senha, width=170, password=True)
        holder = ft.Row(spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        ref = (email_f, senha_f)
        usuarios_refs.append(ref)

        def _remove(_):
            usuarios_refs.remove(ref)
            usuarios_rows.controls.remove(holder)
            ctrl.page.update()

        holder.controls.extend([
            email_f, senha_f,
            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_size=18,
                          icon_color=C_ON_SURFACE_VARIANT, tooltip="Remover",
                          on_click=_remove),
        ])
        usuarios_rows.controls.append(holder)

    for email, senha in usuarios.items():
        _add_user(email, str(senha))

    email_tab = ft.Column([
        destino_f,
        ft.Row([host_f, port_f], spacing=6),
        ft.Divider(height=1, color=C_OUTLINE),
        ft.Text("Liberadores e senhas de envio (remetentes SMTP).",
                size=11, color=C_ON_SURFACE_VARIANT),
        usuarios_rows,
        ft.TextButton("Adicionar liberador", icon=ft.Icons.ADD,
                      on_click=lambda _: (_add_user(), ctrl.page.update())),
    ], spacing=8, scroll=ft.ScrollMode.AUTO)

    def _section_header(text: str, icon: str) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                ft.Icon(icon, size=15, color=C_PRIMARY),
                ft.Text(text, size=13, weight=ft.FontWeight.W_700, color=C_ON_SURFACE),
            ], spacing=8),
            padding=ft.padding.only(top=6, bottom=2),
        )

    secoes = ft.Column([
        _section_header("Fornecedores", ft.Icons.LOCAL_SHIPPING_OUTLINED),
        forn_tab,
        ft.Divider(height=1, color=C_OUTLINE),
        _section_header("Lojas", ft.Icons.STOREFRONT_OUTLINED),
        lojas_tab,
        ft.Divider(height=1, color=C_OUTLINE),
        _section_header("E-mail", ft.Icons.ALTERNATE_EMAIL_OUTLINED),
        email_tab,
    ], spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    status_txt = ft.Text("", size=12, color=ACCENT)

    def _collect_into_data() -> None:
        # Fornecedores: nome -> lista de emails (mantém [""] se vazio p/ enviar sem CC)
        novos_forn: Dict[str, list] = {}
        for nome_f, emails_f in forn_refs:
            nome = nome_f.value.strip().upper()
            if not nome:
                continue
            emails = [e.strip() for e in emails_f.value.split(",") if e.strip()]
            novos_forn[nome] = emails or [""]
        data["fornecedores_email"] = novos_forn

        # Lojas: só sobrescreve os campos editados, preserva loja_email/ocr etc
        for store, refs in loja_refs.items():
            block = data["stores"].setdefault(store, {})
            block["username"] = refs["username"].value.strip()
            block["password"] = refs["password"].value.strip()
            block["cliente_fixo"] = refs["cliente_fixo"].value.strip()
            block["cliente_fixo_vitta"] = refs["cliente_fixo_vitta"].value.strip()

        # E-mail
        data["email_smtp"]["destino_fixo"] = destino_f.value.strip()
        data["email_smtp"]["host"] = host_f.value.strip()
        try:
            data["email_smtp"]["port"] = int(port_f.value.strip())
        except ValueError:
            data["email_smtp"]["port"] = smtp.get("port", 587)
        data["usuarios_email"] = {
            e.value.strip(): s.value.strip()
            for e, s in usuarios_refs if e.value.strip()
        }

    def on_save(_):
        _collect_into_data()
        status_txt.value = "Salvando e propagando..."
        status_txt.color = C_ON_SURFACE_VARIANT
        ctrl.page.update()
        try:
            save_config(data)
        except PermissionError as exc:
            ctrl._alert("Acesso restrito", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            ctrl._alert("Erro ao salvar", str(exc))
            return
        # Recarrega o config em memória e atualiza a UI principal
        ctrl.state.config = load_config()
        ctrl.notify()
        ctrl.close_dialog(dlg)
        ctrl.show_snackbar("Configuração salva e propagada para todos os usuários.")

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([
            ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, color=C_PRIMARY),
            ft.Text("Administração — configuração central"),
        ], spacing=8),
        content=ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Text(
                        "As alterações valem para TODOS os usuários no próximo início do app.",
                        size=11, color=C_ON_SURFACE_VARIANT),
                    padding=ft.padding.only(bottom=4),
                ),
                secoes,
                status_txt,
            ], spacing=8, tight=True),
            width=640,
            height=480,
        ),
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: ctrl.close_dialog(dlg)),
            ft.FilledButton("Salvar e propagar", icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
                            on_click=on_save),
        ],
    )
    ctrl.show_dialog(dlg)

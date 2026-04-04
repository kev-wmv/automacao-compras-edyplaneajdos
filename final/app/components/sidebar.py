"""Sidebar — painel lateral editorial com faixa accent e agrupamento visual."""
from __future__ import annotations

import flet as ft

from ..theme import (
    ACCENT, ACCENT_HOV, ACCENT_MUTED,
    SIDE_W, SIDEBAR_SHADOW,
    C_SURFACE_CONTAINER, C_ON_SURFACE, C_ON_SURFACE_VARIANT,
    C_PRIMARY, C_ON_PRIMARY, C_OUTLINE, C_OUTLINE_VARIANT,
)
from ..state import AppController
from ..updater import get_current_version
from ...cadastro_clientes_finger import STORES


def _section_label(text: str, icon: str = None) -> ft.Container:
    """Label de seção com estilo editorial."""
    children = []
    if icon:
        children.append(ft.Icon(icon, size=12, color=ACCENT_MUTED))
    children.append(
        ft.Text(
            text,
            size=9,
            color=C_ON_SURFACE_VARIANT,
            weight=ft.FontWeight.W_600,
            style=ft.TextStyle(letter_spacing=1.2),
        ),
    )
    return ft.Container(
        content=ft.Row(children, spacing=6),
        padding=ft.padding.only(top=4, bottom=2),
    )


def build_sidebar(ctrl: AppController) -> ft.Container:
    """Constrói sidebar com design editorial refinado."""

    # ── Campos ────────────────────────────────────────────────────────────────
    comprador_field = ft.TextField(
        label="Comprador",
        value=ctrl.state.comprador,
        text_size=13,
        height=44,
        border_color=C_OUTLINE,
        focused_border_color=ACCENT,
        color=C_ON_SURFACE,
        label_style=ft.TextStyle(size=11, color=C_ON_SURFACE_VARIANT),
        border_radius=6,
        expand=True,
        on_change=lambda e: setattr(ctrl.state, "comprador", e.control.value),
    )

    fabricante_dd = ft.Dropdown(
        label="Fabricante",
        value=ctrl.state.fabricante,
        options=[
            ft.dropdown.Option(key="Finger", text="Finger"),
            ft.dropdown.Option(key="Vitta", text="Vitta"),
        ],
        text_size=13,
        border_color=C_OUTLINE,
        focused_border_color=ACCENT,
        color=C_ON_SURFACE,
        label_style=ft.TextStyle(size=11, color=C_ON_SURFACE_VARIANT),
        border_radius=6,
        expand=True,
    )

    loja_dd = ft.Dropdown(
        label="Loja",
        value=ctrl.state.selected_store,
        options=[ft.dropdown.Option(key=s, text=s) for s in STORES],
        text_size=13,
        border_color=C_OUTLINE,
        focused_border_color=ACCENT,
        color=C_ON_SURFACE,
        label_style=ft.TextStyle(size=11, color=C_ON_SURFACE_VARIANT),
        border_radius=6,
        expand=True,
        on_select=lambda e: setattr(ctrl.state, "selected_store", e.control.value),
    )

    # ── Seções de ação ────────────────────────────────────────────────────────
    finger_action = ft.RadioGroup(
        value=ctrl.state.action,
        content=ft.Column([
            ft.Radio(value="clientes", label="Cadastrar clientes",
                     label_style=ft.TextStyle(size=12, color=C_ON_SURFACE)),
            ft.Radio(value="pedidos", label="Cadastrar pedidos",
                     label_style=ft.TextStyle(size=12, color=C_ON_SURFACE)),
        ], spacing=0),
        on_change=lambda e: setattr(ctrl.state, "action", e.control.value),
    )

    finger_section = ft.Column([
        loja_dd,
        _section_label("AÇÃO"),
        finger_action,
    ], spacing=8, visible=True)

    vitta_action = ft.RadioGroup(
        value=ctrl.state.vitta_action,
        content=ft.Column([
            ft.Radio(value="clientes", label="Cadastrar clientes",
                     label_style=ft.TextStyle(size=12, color=C_ON_SURFACE)),
            ft.Radio(value="pedidos", label="Cadastrar pedidos",
                     label_style=ft.TextStyle(size=12, color=C_ON_SURFACE)),
        ], spacing=0),
        on_change=lambda e: setattr(ctrl.state, "vitta_action", e.control.value),
    )

    vitta_section = ft.Column([
        _section_label("AÇÃO"),
        vitta_action,
    ], spacing=8, visible=False)

    # ── Lógica de fabricante ──────────────────────────────────────────────────
    def _apply_fabricante(value: str) -> None:
        is_finger = value == "Finger"
        finger_section.visible = is_finger
        vitta_section.visible = not is_finger
        loja_dd.disabled = not is_finger
        fabricante_dd.value = value

    def on_fabricante_change(e: ft.ControlEvent) -> None:
        ctrl.state.fabricante = e.control.value
        _apply_fabricante(e.control.value)
        ctrl.notify()
        ctrl.page.update()

    fabricante_dd.on_select = on_fabricante_change

    def on_state_change() -> None:
        new_fab = ctrl.state.fabricante
        if fabricante_dd.value != new_fab:
            _apply_fabricante(new_fab)

    ctrl.subscribe(on_state_change)

    # ── Opções ────────────────────────────────────────────────────────────────
    headless_cb = ft.Checkbox(
        label="Ocultar navegador",
        value=ctrl.state.headless,
        label_style=ft.TextStyle(size=11, color=C_ON_SURFACE_VARIANT),
        check_color=C_ON_PRIMARY,
        active_color=C_PRIMARY,
        on_change=lambda e: setattr(ctrl.state, "headless", e.control.value),
    )

    # ── Botão principal ───────────────────────────────────────────────────────
    start_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.PLAY_ARROW_ROUNDED, size=18, color=C_ON_PRIMARY),
            ft.Text("Iniciar processo", size=13, color=C_ON_PRIMARY,
                    weight=ft.FontWeight.W_600),
        ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=C_PRIMARY,
        width=float("inf"),
        height=44,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            overlay_color=ACCENT_HOV,
        ),
    )

    def on_start(e: ft.ControlEvent) -> None:
        start_btn.disabled = True
        ctrl.page.update()

        def on_done() -> None:
            start_btn.disabled = False
            ctrl.page.update()

        ctrl.do_start_process(on_done)

    start_btn.on_click = on_start

    # ── Botões secundários ────────────────────────────────────────────────────
    send_pdf_label = ft.Text(
        "Enviar PDFs (0 pendentes)",
        size=12,
        overflow=ft.TextOverflow.ELLIPSIS,
        text_align=ft.TextAlign.CENTER,
    )

    send_pdf_btn = ft.OutlinedButton(
        send_pdf_label,
        width=float("inf"),
        height=36,
        style=ft.ButtonStyle(
            color=C_ON_SURFACE_VARIANT,
            shape=ft.RoundedRectangleBorder(radius=6),
            side=ft.BorderSide(1, C_OUTLINE),
        ),
        disabled=True,
    )

    # Botões utilitários — ícone com tooltip
    _icon_btn_style = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=6),
    )

    log_toggle_btn = ft.IconButton(
        icon=ft.Icons.TERMINAL_OUTLINED,
        icon_size=16,
        tooltip="Logs",
        icon_color=C_ON_SURFACE_VARIANT,
        width=36,
        height=30,
        style=_icon_btn_style,
    )

    log_clear_btn = ft.IconButton(
        icon=ft.Icons.CLEAR_ALL_OUTLINED,
        icon_size=16,
        tooltip="Limpar logs",
        icon_color=C_ON_SURFACE_VARIANT,
        width=36,
        height=30,
        style=_icon_btn_style,
    )

    update_check_btn = ft.IconButton(
        icon=ft.Icons.SYSTEM_UPDATE_OUTLINED,
        icon_size=16,
        tooltip="Verificar atualização",
        icon_color=C_ON_SURFACE_VARIANT,
        width=36,
        height=30,
        style=_icon_btn_style,
    )

    # ── Contagem de PDFs ──────────────────────────────────────────────────────
    def update_pdf_count() -> None:
        pendentes = [o for o in ctrl.state.pdf_orders
                     if o["status"] == "pendente" and o.get("can_send")]
        n = len(pendentes)
        send_pdf_label.value = f"Enviar PDFs ({n} pendente{'s' if n != 1 else ''})"
        send_pdf_btn.disabled = n == 0

    ctrl.subscribe(update_pdf_count)

    # ── Layout do sidebar ─────────────────────────────────────────────────────
    sidebar_content = ft.Column([
        # ── Header com marca ──────────────────────────────────────────────
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Text("E", size=15, color=C_ON_PRIMARY,
                                        weight=ft.FontWeight.BOLD,
                                        text_align=ft.TextAlign.CENTER),
                        bgcolor=C_PRIMARY,
                        border_radius=6,
                        width=32, height=32,
                        alignment=ft.Alignment(0, 0),
                    ),
                    ft.Column([
                        ft.Text("Encomendas Edy", size=15,
                                weight=ft.FontWeight.BOLD, color=C_ON_SURFACE),
                        ft.Text(
                            f"v{get_current_version()} · Kevin Gomes",
                            size=9,
                            color=C_ON_SURFACE_VARIANT,
                        ),
                    ], spacing=0),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ]),
            padding=ft.padding.only(bottom=8),
        ),

        ft.Divider(height=1, color=C_OUTLINE_VARIANT),

        # ── Seção: configuração ───────────────────────────────────────────
        _section_label("CONFIGURAÇÃO", ft.Icons.TUNE_OUTLINED),
        comprador_field,
        fabricante_dd,

        ft.Divider(height=1, color=C_OUTLINE_VARIANT),

        # ── Seção: fabricante ─────────────────────────────────────────────
        finger_section,
        vitta_section,

        # Spacer
        ft.Container(expand=True),

        # ── Seção: ações ──────────────────────────────────────────────────
        ft.Divider(height=1, color=C_OUTLINE_VARIANT),
        headless_cb,
        start_btn,
        send_pdf_btn,
        ft.Row([log_toggle_btn, log_clear_btn, update_check_btn], spacing=4,
               alignment=ft.MainAxisAlignment.CENTER),
    ], spacing=10, expand=True)

    sidebar = ft.Container(
        width=SIDE_W,
        bgcolor=C_SURFACE_CONTAINER,
        padding=ft.padding.only(left=20, right=20, top=20, bottom=16),
        shadow=SIDEBAR_SHADOW,
        content=sidebar_content,
    )

    # Expor refs
    sidebar.log_toggle_btn = log_toggle_btn  # type: ignore[attr-defined]
    sidebar.log_clear_btn = log_clear_btn  # type: ignore[attr-defined]
    sidebar.send_pdf_btn = send_pdf_btn  # type: ignore[attr-defined]
    sidebar.update_check_btn = update_check_btn  # type: ignore[attr-defined]

    return sidebar

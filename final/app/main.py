"""Entry point da aplicação Flet — Encomendas Edy v6.0."""
from __future__ import annotations

import flet as ft

from .theme import BG, BORDER, THEME, DARK_THEME, C_SURFACE
from .state import AppController
from .components.sidebar import build_sidebar
from .components.folder_card import build_folder_card
from .components.project_card import build_project_card
from .components.client_card import build_client_card
from .components.log_panel import build_log_panel
from .components.email_dialog import show_email_dialog
from .components.loading import setup_loading

async def main(page: ft.Page) -> None:
    """Configura e renderiza a UI principal."""
    page.title = "Encomendas Edy"
    page.theme = THEME
    page.dark_theme = DARK_THEME
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.bgcolor = C_SURFACE
    page.window.width = 1120
    page.window.height = 700
    page.window.min_width = 900
    page.window.min_height = 560
    await page.window.center()
    page.padding = 0
    page.spacing = 0

    # ── Controller ────────────────────────────────────────────────────────────
    ctrl = AppController(page)

    # ── Loading overlay ───────────────────────────────────────────────────────
    setup_loading(ctrl)

    # ── Componentes ───────────────────────────────────────────────────────────
    sidebar = build_sidebar(ctrl)

    folder_card = build_folder_card(
        page,
        on_folder_selected=lambda path: ctrl.do_process_folder(path),
    )

    project_card = build_project_card(ctrl)
    client_card = build_client_card(ctrl)
    log_panel = build_log_panel(ctrl)

    # ── Conectar botões da sidebar ────────────────────────────────────────────
    sidebar.log_toggle_btn.on_click = lambda _: log_panel.toggle()  # type: ignore[attr-defined]
    sidebar.log_clear_btn.on_click = lambda _: log_panel.clear()  # type: ignore[attr-defined]
    sidebar.send_pdf_btn.on_click = lambda _: show_email_dialog(ctrl)  # type: ignore[attr-defined]

    # ── Layout principal ──────────────────────────────────────────────────────
    # Row superior: folder + projetos — altura fixa para simetria
    top_row = ft.Container(
        content=ft.Row([
            folder_card,
            project_card,
        ], spacing=16, expand=True,
           vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        height=250,
    )

    content_area = ft.Column([
        top_row,
        client_card,
        log_panel,
    ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO)

    content_container = ft.Container(
        content=content_area,
        expand=True,
        padding=20,
    )

    page.add(
        ft.Row([
            sidebar,
            content_container,
        ], spacing=0, expand=True),
    )

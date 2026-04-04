"""Card de projetos encontrados — lista com ícones de tipo e status badges."""
from __future__ import annotations

import flet as ft

from ..theme import (
    ACCENT, ACCENT_MUTED, SUCCESS, WARNING,
    C_SURFACE_CONTAINER, C_SURFACE_VARIANT, C_ON_SURFACE, C_ON_SURFACE_VARIANT,
    C_OUTLINE, C_OUTLINE_VARIANT,
)
from ..state import AppController


def _file_icon(name: str) -> ft.Icon:
    """Ícone contextual por tipo de arquivo."""
    lower = name.lower()
    if lower.endswith(".xml"):
        return ft.Icon(ft.Icons.CODE_OUTLINED, size=14, color=ACCENT_MUTED)
    if lower.endswith(".txt"):
        return ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=14, color=ACCENT_MUTED)
    if lower.endswith(".pdf"):
        return ft.Icon(ft.Icons.PICTURE_AS_PDF_OUTLINED, size=14, color="#c05050")
    return ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=14,
                   color=C_ON_SURFACE_VARIANT)


def build_project_card(ctrl: AppController) -> ft.Container:
    """Constrói card com lista de projetos encontrados."""

    count_text = ft.Text("Nenhum arquivo identificado", size=11,
                         color=C_ON_SURFACE_VARIANT)

    refresh_btn = ft.OutlinedButton(
        content=ft.Row([
            ft.Icon(ft.Icons.REFRESH_OUTLINED, size=14, color=C_ON_SURFACE_VARIANT),
            ft.Text("Atualizar", size=11, color=C_ON_SURFACE_VARIANT),
        ], spacing=4, alignment=ft.MainAxisAlignment.CENTER),
        height=30,
        disabled=True,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=6),
            side=ft.BorderSide(1, C_OUTLINE),
        ),
    )

    list_view = ft.ListView(
        spacing=4,
        auto_scroll=False,
        height=160,
    )

    def _build_list() -> None:
        list_view.controls.clear()
        s = ctrl.state
        fabricante = s.fabricante.lower()
        refresh_btn.disabled = s.folder_path is None

        if fabricante == "vitta":
            file_list = s.vitta_xml_files
            suffix = ".xml"
            empty_text = "Nenhum .xml identificado"
        else:
            file_list = s.txt_files
            suffix = ".txt"
            empty_text = "Nenhum .txt identificado"

        seen: set = set()
        unique: list = []
        for p in file_list:
            if p.name.lower() not in seen:
                seen.add(p.name.lower())
                unique.append(p)

        for p in unique:
            tile = ft.Container(
                content=ft.Row([
                    _file_icon(p.name),
                    ft.Text(p.name, size=11, color=C_ON_SURFACE, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=C_SURFACE_VARIANT,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6,
            )
            list_view.controls.append(tile)

        for o in s.pdf_orders:
            is_sent = o["status"] == "enviado"
            can_send = o.get("can_send", False)
            badge_bg = "#e8f5e9" if is_sent else "#e4f0e8" if can_send else "#fef3cd"
            badge_fg = SUCCESS if is_sent else ACCENT if can_send else WARNING
            badge_label = "ENVIADO" if is_sent else "PENDENTE" if can_send else "SEM E-MAIL"
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE if is_sent \
                else ft.Icons.MAIL_OUTLINE if can_send \
                else ft.Icons.WARNING_AMBER_OUTLINED

            tile = ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=14, color=badge_fg),
                    ft.Text(f"PEDIDO {o['supplier']}", size=11,
                            color=C_ON_SURFACE, expand=True),
                    ft.Container(
                        content=ft.Text(badge_label, size=8, color=badge_fg,
                                        weight=ft.FontWeight.W_600),
                        bgcolor=badge_bg,
                        border_radius=4,
                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                    ),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=C_SURFACE_VARIANT,
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=6,
            )
            list_view.controls.append(tile)

        parts = []
        if unique:
            parts.append(f"{len(unique)} arquivo(s) {suffix}")
        if s.pdf_orders:
            parts.append(f"{len(s.pdf_orders)} PDF(s)")
        count_text.value = " · ".join(parts) if parts else empty_text

    def _refresh(_: ft.ControlEvent) -> None:
        ctrl.do_refresh_folder()

    refresh_btn.on_click = _refresh

    ctrl.subscribe(lambda: _build_list())
    _build_list()

    header = ft.Row([
        ft.Row([
            ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=14, color=ACCENT_MUTED),
            ft.Text("PROJETOS", size=9, color=C_ON_SURFACE_VARIANT,
                    weight=ft.FontWeight.W_600,
                    style=ft.TextStyle(letter_spacing=1.2)),
        ], spacing=6, expand=True),
        refresh_btn,
    ], vertical_alignment=ft.CrossAxisAlignment.CENTER)

    card = ft.Container(
        content=ft.Column([
            header,
            ft.Container(content=count_text, padding=ft.padding.only(bottom=2)),
            list_view,
        ], spacing=8),
        bgcolor=C_SURFACE_CONTAINER,
        border=ft.border.all(1, C_OUTLINE_VARIANT),
        border_radius=12,
        padding=16,
        expand=True,
    )

    return card

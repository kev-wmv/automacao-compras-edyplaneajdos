"""Card de seleção de pasta — zona de drop com borda tracejada e ícone contextual."""
from __future__ import annotations

from pathlib import Path

import flet as ft

from ..theme import (
    ACCENT, ACCENT_SOFT, ACCENT_MUTED,
    C_SURFACE_CONTAINER, C_SURFACE_VARIANT, C_ON_SURFACE_VARIANT, C_OUTLINE_VARIANT,
)


def build_folder_card(
    page: ft.Page,
    on_folder_selected: callable,
) -> ft.Container:
    """Constrói card de seleção de pasta com FilePicker."""

    picker = ft.FilePicker()
    page.services.append(picker)

    async def _pick_directory() -> None:
        selected = await picker.get_directory_path(
            dialog_title="Selecionar pasta do projeto"
        )
        if selected:
            on_folder_selected(Path(selected))

    def _on_click(_: ft.ControlEvent) -> None:
        page.run_task(_pick_directory)

    drop_area = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Icon(ft.Icons.FOLDER_OPEN_OUTLINED, size=28, color=ACCENT),
                bgcolor=ACCENT_SOFT,
                border_radius=10,
                width=52, height=52,
                alignment=ft.Alignment(0, 0),
            ),
            ft.Text("Selecionar pasta", size=13,
                    weight=ft.FontWeight.W_600, color=ACCENT),
            ft.Text("Clique para abrir o projeto",
                    size=11, color=C_ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER),
        ], alignment=ft.MainAxisAlignment.CENTER,
           horizontal_alignment=ft.CrossAxisAlignment.CENTER,
           spacing=8),
        bgcolor=C_SURFACE_VARIANT,
        border=ft.border.all(1.5, ACCENT_MUTED),
        border_radius=10,
        height=160,
        alignment=ft.Alignment(0, 0),
        on_click=_on_click,
        ink=True,
    )

    header = ft.Row([
        ft.Icon(ft.Icons.SOURCE_OUTLINED, size=14, color=ACCENT_MUTED),
        ft.Text("PASTA DO PROJETO", size=9, color=C_ON_SURFACE_VARIANT,
                weight=ft.FontWeight.W_600,
                style=ft.TextStyle(letter_spacing=1.2)),
    ], spacing=6)

    card = ft.Container(
        content=ft.Column([header, drop_area], spacing=10),
        bgcolor=C_SURFACE_CONTAINER,
        border=ft.border.all(1, C_OUTLINE_VARIANT),
        border_radius=12,
        padding=16,
        expand=True,
    )

    return card

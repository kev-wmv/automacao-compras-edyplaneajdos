"""Card de informações do cliente — grid OCR com header iconizado."""
from __future__ import annotations

import flet as ft

from ..theme import (
    ACCENT, ACCENT_MUTED,
    C_SURFACE_CONTAINER, C_ON_SURFACE, C_ON_SURFACE_VARIANT, C_OUTLINE, C_OUTLINE_VARIANT,
)
from ..state import AppController
from ...cadastro_clientes_finger import OCR_FIELD_KEYS, OCR_FIELD_LABELS


def build_client_card(ctrl: AppController) -> ft.Container:
    """Constrói card com grid de campos OCR do cliente."""

    fields: dict[str, ft.TextField] = {}

    def _make_field(key: str) -> ft.TextField:
        tf = ft.TextField(
            label=OCR_FIELD_LABELS[key],
            value=ctrl.state.ocr_results.get(key, ""),
            text_size=12,
            height=42,
            border_color=C_OUTLINE,
            focused_border_color=ACCENT,
            color=C_ON_SURFACE,
            label_style=ft.TextStyle(size=10, color=C_ON_SURFACE_VARIANT),
            border_radius=6,
            on_change=lambda e, k=key: _on_field_change(k, e.control.value),
            expand=True,
        )
        fields[key] = tf
        return tf

    def _on_field_change(key: str, value: str) -> None:
        ctrl.state.ocr_results[key] = value

    # Grid: 2 campos por linha
    rows: list[ft.Row] = []
    for i in range(0, len(OCR_FIELD_KEYS), 2):
        row_fields = [_make_field(OCR_FIELD_KEYS[i])]
        if i + 1 < len(OCR_FIELD_KEYS):
            row_fields.append(_make_field(OCR_FIELD_KEYS[i + 1]))
        rows.append(ft.Row(row_fields, spacing=12))

    def on_state_change() -> None:
        for key, tf in fields.items():
            new_val = ctrl.state.ocr_results.get(key, "")
            if tf.value != new_val:
                tf.value = new_val

    ctrl.subscribe(on_state_change)

    header = ft.Row([
        ft.Icon(ft.Icons.PERSON_OUTLINE, size=14, color=ACCENT_MUTED),
        ft.Text("INFORMAÇÕES DO CLIENTE", size=9,
                color=C_ON_SURFACE_VARIANT,
                weight=ft.FontWeight.W_600,
                style=ft.TextStyle(letter_spacing=1.2)),
    ], spacing=6)

    card = ft.Container(
        content=ft.Column([header, *rows], spacing=8),
        bgcolor=C_SURFACE_CONTAINER,
        border=ft.border.all(1, C_OUTLINE_VARIANT),
        border_radius=12,
        padding=16,
    )

    return card

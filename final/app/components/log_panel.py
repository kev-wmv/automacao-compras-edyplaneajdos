"""Painel de logs — estética terminal escura contrastando com o tema claro."""
from __future__ import annotations

import logging
from typing import List

import flet as ft

from ..theme import (
    LOG_BG, LOG_TEXT, ACCENT_MUTED,
    C_SURFACE_CONTAINER, C_ON_SURFACE_VARIANT, C_OUTLINE_VARIANT,
)
from ..state import AppController

_MAX_LOG_LINES = 500


def build_log_panel(ctrl: AppController) -> ft.Container:
    """Constrói painel de logs com estética de terminal."""

    log_list = ft.ListView(
        spacing=1,
        height=160,
        auto_scroll=True,
    )

    terminal = ft.Container(
        content=ft.Column([
            # Barra de título do terminal
            ft.Container(
                content=ft.Row([
                    ft.Row([
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#e05050"),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#e0b040"),
                        ft.Container(width=8, height=8, border_radius=4, bgcolor="#50c060"),
                    ], spacing=5),
                    ft.Text("terminal", size=10, color="#6a7a70",
                            weight=ft.FontWeight.W_500),
                ], spacing=10, alignment=ft.MainAxisAlignment.START),
                bgcolor="#151e19",
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                border_radius=ft.border_radius.only(top_left=8, top_right=8),
            ),
            # Corpo do terminal
            ft.Container(
                content=log_list,
                bgcolor=LOG_BG,
                padding=ft.padding.only(left=12, right=12, top=8, bottom=8),
                border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8),
            ),
        ], spacing=0),
    )

    header = ft.Row([
        ft.Icon(ft.Icons.TERMINAL_OUTLINED, size=14, color=ACCENT_MUTED),
        ft.Text("LOGS DE EXECUÇÃO", size=9, color=C_ON_SURFACE_VARIANT,
                weight=ft.FontWeight.W_600,
                style=ft.TextStyle(letter_spacing=1.2)),
    ], spacing=6)

    log_container = ft.Container(
        content=ft.Column([header, terminal], spacing=10),
        bgcolor=C_SURFACE_CONTAINER,
        border=ft.border.all(1, C_OUTLINE_VARIANT),
        border_radius=12,
        padding=16,
        visible=False,
    )

    _LEVEL_COLORS = {
        "INFO": LOG_TEXT,
        "WARNING": "#e0c060",
        "ERROR": "#e06060",
        "DEBUG": "#607068",
    }

    def _append_log(level: str, msg: str) -> None:
        color = _LEVEL_COLORS.get(level, LOG_TEXT)
        text = ft.Text(msg, size=10, color=color, font_family="Consolas")
        log_list.controls.append(text)
        if len(log_list.controls) > _MAX_LOG_LINES:
            log_list.controls.pop(0)
        try:
            ctrl.page.update()
        except Exception:
            pass

    ctrl.subscribe_log(_append_log)

    # Registrar handler nos loggers do projeto
    class _FletLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level = record.levelname
                ts = self.formatter.formatTime(record, "%H:%M:%S") if self.formatter else ""
                msg = f"[{ts}] {level:7s} {record.getMessage()}"
                ctrl.page.run_thread(lambda m=msg, lv=level: _append_log(lv, m))
            except Exception:
                pass

    handler = _FletLogHandler()
    handler.setFormatter(logging.Formatter())
    handler.setLevel(logging.DEBUG)

    for logger_name in (
        "final.cadastro_pedidos_vitta",
        "final.cadastro_pedidos_finger",
        "cadastro_pedidos_vitta",
        "cadastro_pedidos_finger",
        "final.enviar_pedidos_email",
        "enviar_pedidos_email",
    ):
        lg = logging.getLogger(logger_name)
        lg.addHandler(handler)
        if not lg.level or lg.level > logging.DEBUG:
            lg.setLevel(logging.DEBUG)

    def toggle() -> None:
        log_container.visible = not log_container.visible
        ctrl.page.update()

    def clear() -> None:
        log_list.controls.clear()
        ctrl.page.update()

    log_container.toggle = toggle  # type: ignore[attr-defined]
    log_container.clear = clear  # type: ignore[attr-defined]

    return log_container

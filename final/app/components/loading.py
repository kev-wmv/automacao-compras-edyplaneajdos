"""Overlay de loading — dialog polido com ícone contextual e botão de cancelar."""
from __future__ import annotations

from typing import Optional

import flet as ft

from ..theme import BG_CARD, BORDER, TEXT, TEXT_DIM, ACCENT, ACCENT_SOFT, ACCENT_MUTED, ERROR
from ..state import AppController


def setup_loading(ctrl: AppController) -> None:
    """Registra o handler de loading no controller."""

    loading_dlg: list = [None]
    progress_bar: list = [None]
    message_text: list = [None]

    def _handle_loading(
        message: Optional[str],
        current: Optional[int],
        total: Optional[int],
    ) -> None:
        if message is None:
            if loading_dlg[0] is not None:
                try:
                    ctrl.close_dialog(loading_dlg[0])
                except Exception:
                    pass
                loading_dlg[0] = None
            try:
                ctrl.page.update()
            except Exception:
                pass
            return

        if loading_dlg[0] is None:
            msg_text = ft.Text(message, size=13, weight=ft.FontWeight.W_600, color=TEXT)
            sub_text = ft.Text("Por favor, aguarde...", size=11, color=TEXT_DIM)
            pb = ft.ProgressBar(color=ACCENT, bgcolor=BORDER)

            message_text[0] = msg_text
            progress_bar[0] = pb

            cancel_btn = ft.OutlinedButton(
                content=ft.Row([
                    ft.Icon(ft.Icons.STOP_CIRCLE_OUTLINED, size=14, color=ERROR),
                    ft.Text("Cancelar", size=12, color=ERROR,
                            weight=ft.FontWeight.W_500),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                width=float("inf"),
                height=36,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    side=ft.BorderSide(1, ERROR),
                ),
                on_click=lambda _: ctrl.do_cancel_process(),
            )

            dlg = ft.AlertDialog(
                modal=True,
                content=ft.Container(
                    width=320,
                    content=ft.Column([
                        ft.Row([
                            ft.Container(
                                content=ft.Icon(ft.Icons.HOURGLASS_TOP_OUTLINED,
                                                size=20, color=ACCENT),
                                bgcolor=ACCENT_SOFT,
                                border_radius=8,
                                width=38, height=38,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Column([msg_text, sub_text], spacing=2, expand=True),
                        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        pb,
                        cancel_btn,
                    ], spacing=14, tight=True),
                    padding=ft.padding.only(top=10),
                ),
            )
            loading_dlg[0] = dlg
            ctrl.show_dialog(dlg)
        else:
            message_text[0].value = message

        if current is not None and total is not None and total > 0:
            progress_bar[0].value = current / total
        else:
            progress_bar[0].value = None

        try:
            ctrl.page.update()
        except Exception:
            pass

    ctrl._on_loading = _handle_loading

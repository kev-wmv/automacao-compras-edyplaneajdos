"""Dialog de envio de pedidos PDF por e-mail — UI editorial refinada."""
from __future__ import annotations

import threading
from typing import Dict, List

import flet as ft

from ..theme import (
    BG_ENTRY, ACCENT, ACCENT_HOV, ACCENT_SOFT, SUCCESS, WARNING, ERROR,
    C_ON_SURFACE, C_ON_SURFACE_VARIANT, C_PRIMARY, C_ON_PRIMARY,
    C_OUTLINE, C_OUTLINE_VARIANT,
)

# Aliases locais para referências legadas ainda presentes no arquivo
TEXT     = C_ON_SURFACE
TEXT_DIM = C_ON_SURFACE_VARIANT
BORDER   = C_OUTLINE
from ..state import AppController
from ...services import (
    refresh_pdf_orders,
    send_order_email,
    extract_client_code,
    build_email_subject,
    build_email_body,
)
from ...enviar_pedidos_email import mark_email_sent as _mark_sent


# ── Helpers de UI ─────────────────────────────────────────────────────────────

def _status_badge(status: str, can_send: bool) -> ft.Container:
    """Cria um badge de status com cor e ícone contextual."""
    config = {
        "pendente": (
            (ACCENT_SOFT, ACCENT, "PENDENTE") if can_send
            else ("#fef3cd", WARNING, "SEM E-MAIL")
        ),
        "enviado": ("#e8f5e9", SUCCESS, "ENVIADO"),
        "sem_email": ("#fef3cd", WARNING, "SEM E-MAIL"),
    }
    bg, fg, label = config.get(status, (BG_ENTRY, TEXT_DIM, status.upper()))

    return ft.Container(
        content=ft.Text(label, size=9, color=fg, weight=ft.FontWeight.W_600),
        bgcolor=bg,
        border_radius=4,
        padding=ft.padding.symmetric(horizontal=8, vertical=3),
    )


def _order_row(
    o: dict,
    cb: ft.Checkbox,
) -> ft.Container:
    """Cria uma linha de pedido estilizada como card inline."""
    icon_name = ft.Icons.MARK_EMAIL_READ_OUTLINED if o["status"] == "enviado" \
        else ft.Icons.MAIL_OUTLINE if o.get("can_send") \
        else ft.Icons.WARNING_AMBER_OUTLINED

    icon_color = SUCCESS if o["status"] == "enviado" \
        else ACCENT if o.get("can_send") \
        else WARNING

    return ft.Container(
        content=ft.Row([
            cb,
            ft.Icon(icon_name, size=18, color=icon_color),
            ft.Text(
                o["supplier"],
                size=12,
                weight=ft.FontWeight.W_500,
                color=TEXT,
                expand=True,
            ),
            _status_badge(o["status"], o.get("can_send", False)),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor=BG_ENTRY,
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=12, vertical=8),
    )


# ── Dialog principal ──────────────────────────────────────────────────────────

def show_email_dialog(ctrl: AppController) -> None:
    """Abre dialog refinado para envio de PDFs de pedido."""
    s = ctrl.state
    cfg = ctrl.cfg

    if not s.pdf_orders or not s.folder_path:
        return

    # Atualizar status
    updated = refresh_pdf_orders(s.folder_path, cfg)
    checked_ids = {o["id"] for o in s.pdf_orders if o.get("checked")}
    for o in updated:
        o["checked"] = o["id"] in checked_ids and o["status"] == "pendente"

    pendentes = [o for o in updated if o["status"] == "pendente" and o.get("can_send")]
    enviados = [o for o in updated if o["status"] == "enviado"]

    if not pendentes and not any(o["status"] != "enviado" for o in updated):
        ctrl.show_snackbar("Todos os pedidos ja foram enviados.")
        return

    orders = updated
    s.pdf_orders = updated

    # ── Header ────────────────────────────────────────────────────────────────
    header = ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.FORWARD_TO_INBOX_OUTLINED, size=22,
                                color=C_ON_PRIMARY),
                bgcolor=C_PRIMARY,
                border_radius=8,
                width=40,
                height=40,
                alignment=ft.Alignment(0, 0),
            ),
            ft.Column([
                ft.Text(
                    "Enviar Pedidos por E-mail",
                    size=16,
                    weight=ft.FontWeight.W_600,
                    color=C_ON_SURFACE,
                ),
                ft.Text(
                    f"{len(pendentes)} pendente{'s' if len(pendentes) != 1 else ''}"
                    f"  ·  {len(enviados)} enviado{'s' if len(enviados) != 1 else ''}",
                    size=11,
                    color=C_ON_SURFACE_VARIANT,
                ),
            ], spacing=2, expand=True),
        ], spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.only(bottom=6),
    )

    # ── Remetente ─────────────────────────────────────────────────────────────
    user_list = list(cfg.usuarios_email.keys())
    remetente_dd = ft.Dropdown(
        label="Remetente",
        value=user_list[0] if user_list else "",
        options=[ft.dropdown.Option(u) for u in user_list],
        text_size=12,
        border_color=C_OUTLINE,
        focused_border_color=ACCENT,
        color=C_ON_SURFACE,
        label_style=ft.TextStyle(size=10, color=C_ON_SURFACE_VARIANT),
        border_radius=8,
        width=float("inf"),
    )

    # ── Lista de pedidos ──────────────────────────────────────────────────────
    checkboxes: Dict[str, ft.Checkbox] = {}
    order_controls: List[ft.Container] = []

    for o in orders:
        can_check = o["status"] == "pendente" and bool(o.get("can_send"))
        cb = ft.Checkbox(
            value=o.get("checked", False),
            disabled=not can_check,
            active_color=ACCENT,
            check_color="#ffffff",
            on_change=lambda e, order=o: order.__setitem__("checked", e.control.value),
        )
        checkboxes[o["id"]] = cb
        order_controls.append(_order_row(o, cb))

    order_list = ft.ListView(
        controls=order_controls,
        spacing=6,
        height=210,
    )

    # ── Ações em lote ─────────────────────────────────────────────────────────
    def _mark_all(_: ft.ControlEvent) -> None:
        for o in orders:
            if o["status"] == "pendente" and o.get("can_send"):
                o["checked"] = True
                checkboxes[o["id"]].value = True
        ctrl.page.update()

    def _unmark_all(_: ft.ControlEvent) -> None:
        for o in orders:
            o["checked"] = False
            checkboxes[o["id"]].value = False
        ctrl.page.update()

    batch_actions = ft.Row([
        ft.TextButton(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_BOX_OUTLINED, size=14, color=ACCENT),
                ft.Text("Marcar todos", size=11, color=ACCENT),
            ], spacing=4),
            on_click=_mark_all,
        ),
        ft.TextButton(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_BOX_OUTLINE_BLANK, size=14, color=TEXT_DIM),
                ft.Text("Desmarcar", size=11, color=TEXT_DIM),
            ], spacing=4),
            on_click=_unmark_all,
        ),
    ], spacing=4)

    # ── Progresso ─────────────────────────────────────────────────────────────
    progress_bar = ft.ProgressBar(
        color=ACCENT,
        bgcolor=BORDER,
        value=0,
        visible=False,
    )
    progress_text = ft.Text("", size=11, color=TEXT_DIM)

    progress_section = ft.Container(
        content=ft.Column([
            progress_text,
            progress_bar,
        ], spacing=6, tight=True),
    )

    # ── Botões de ação ────────────────────────────────────────────────────────
    send_btn = ft.Button(
        content=ft.Row([
            ft.Icon(ft.Icons.SEND_OUTLINED, size=16, color=C_ON_PRIMARY),
            ft.Text("Enviar selecionados", size=13, color=C_ON_PRIMARY,
                    weight=ft.FontWeight.W_500),
        ], spacing=8, alignment=ft.MainAxisAlignment.CENTER),
        bgcolor=C_PRIMARY,
        height=42,
        expand=True,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=8),
            overlay_color=ACCENT_HOV,
        ),
    )

    cancel_btn = ft.OutlinedButton(
        "Fechar",
        height=42,
        style=ft.ButtonStyle(
            color=C_ON_SURFACE_VARIANT,
            shape=ft.RoundedRectangleBorder(radius=8),
            side=ft.BorderSide(1, C_OUTLINE),
        ),
    )

    # ── Composição do dialog ──────────────────────────────────────────────────
    dlg = ft.AlertDialog(
        modal=True,
        content=ft.Container(
            width=500,
            content=ft.Column([
                header,
                ft.Divider(height=1, color=C_OUTLINE_VARIANT),
                remetente_dd,
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("PEDIDOS", size=10, color=C_ON_SURFACE_VARIANT,
                                    weight=ft.FontWeight.W_600,
                                    style=ft.TextStyle(letter_spacing=1.2),
                                    expand=True),
                            batch_actions,
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        order_list,
                    ], spacing=6),
                ),
                progress_section,
                ft.Container(height=2),
                ft.Row([send_btn, cancel_btn], spacing=10),
            ], spacing=12, tight=True),
            padding=ft.padding.only(top=8),
        ),
    )

    # ── Handlers ──────────────────────────────────────────────────────────────
    def _close(_: ft.ControlEvent = None) -> None:
        ctrl.close_dialog(dlg)
        ctrl.notify()
        ctrl.page.update()

    cancel_btn.on_click = _close

    def _do_send(_: ft.ControlEvent) -> None:
        remetente = remetente_dd.value or ""
        if not remetente:
            ctrl.show_snackbar("Selecione o remetente.")
            return
        senha = cfg.usuarios_email.get(remetente, "")
        if not senha:
            ctrl.show_snackbar(f"Credenciais nao encontradas para '{remetente}'.")
            return

        selecionados = [
            o for o in orders
            if o.get("checked") and o["status"] == "pendente" and o.get("can_send")
        ]
        if not selecionados:
            ctrl.show_snackbar("Nenhum pedido marcado para envio.")
            return

        send_btn.disabled = True
        cancel_btn.disabled = True
        progress_bar.visible = True
        progress_bar.value = 0
        progress_text.value = f"Preparando envio de {len(selecionados)} pedido(s)..."
        ctrl.page.update()

        loja_nome = cfg.stores.get(s.selected_store, {}).get("loja_email", s.selected_store)
        client_code = extract_client_code(s.folder_path) if s.folder_path else ""
        ocr_snap = dict(s.ocr_results)
        smtp_snap = dict(cfg.email_smtp)
        emp_snap = dict(cfg.empresa_info)

        total = len(selecionados)
        sent = [0]

        def _email_worker() -> None:
            for i, o in enumerate(selecionados):
                try:
                    progress_text.value = f"Enviando {i + 1}/{total}: {o['supplier']}..."
                    progress_bar.value = i / total
                    try:
                        ctrl.page.update()
                    except Exception:
                        pass

                    subj = build_email_subject(
                        client_code,
                        ocr_snap.get("cliente", ""),
                        ocr_snap.get("numero_contrato", ""),
                    )
                    body = build_email_body(
                        o["supplier"], ocr_snap, client_code, emp_snap, loja_nome,
                    )
                    send_order_email(
                        smtp_snap, remetente, senha,
                        o["emails_cc"], subj, body, o["path"],
                    )
                    _mark_sent(o["path"], s.folder_path, remetente, o["supplier"])
                    o["status"] = "enviado"
                    o["checked"] = False
                    sent[0] += 1

                    # Atualizar UI da linha para refletir status enviado
                    progress_bar.value = (i + 1) / total
                    try:
                        ctrl.page.update()
                    except Exception:
                        pass

                except Exception as exc:
                    ctrl.show_snackbar(f"Erro ao enviar {o['supplier']}: {exc}")
                    try:
                        ctrl.page.update()
                    except Exception:
                        pass

            def _done() -> None:
                send_btn.disabled = False
                cancel_btn.disabled = False
                progress_bar.visible = False
                progress_bar.value = 0
                progress_text.value = ""

                if sent[0] == total:
                    progress_text.value = f"{sent[0]} e-mail(s) enviado(s) com sucesso."
                    ctrl.show_snackbar(f"{sent[0]} e-mail(s) enviado(s) com sucesso.")
                    _close()
                else:
                    progress_text.value = (
                        f"{sent[0]} de {total} enviado(s). Verifique os erros."
                    )
                    ctrl.page.update()

            ctrl.page.run_thread(_done)

        threading.Thread(target=_email_worker, daemon=True).start()

    send_btn.on_click = _do_send

    ctrl.show_dialog(dlg)

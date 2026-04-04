"""Estado reativo centralizado da aplicação Flet."""
from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import flet as ft

from ..models import AppState, ConfigData, FolderScanResult, ProcessoCancelado
from ..services import (
    load_config,
    apply_browser_settings,
    process_folder,
    scan_folder_files,
)
from ..cadastro_clientes_finger import STORES, OCR_FIELD_KEYS, _config_path


class AppController:
    """Controlador central — conecta estado, serviços e UI."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = AppState(selected_store=STORES[0] if STORES else "")
        self.state.config = load_config()
        apply_browser_settings(self.state.config)

        # Callbacks de UI registrados pelos componentes
        self._on_state_change: List[Callable[[], None]] = []
        self._on_log: List[Callable[[str, str], None]] = []
        self._on_loading: Optional[Callable[[Optional[str], Optional[int], Optional[int]], None]] = None

        # Cancel event para o processo em andamento
        self._cancel_event: Optional[threading.Event] = None

    @property
    def cfg(self) -> ConfigData:
        return self.state.config  # type: ignore[return-value]

    def subscribe(self, callback: Callable[[], None]) -> None:
        self._on_state_change.append(callback)

    def subscribe_log(self, callback: Callable[[str, str], None]) -> None:
        self._on_log.append(callback)

    def notify(self) -> None:
        for cb in self._on_state_change:
            cb()

    def log(self, level: str, msg: str) -> None:
        import time
        ts = time.strftime("%H:%M:%S")
        formatted = f"[{ts}] {level:7s} {msg}"
        for cb in self._on_log:
            cb(level, formatted)

    def show_loading(self, message: Optional[str], current: Optional[int] = None, total: Optional[int] = None) -> None:
        if self._on_loading:
            self._on_loading(message, current, total)

    def hide_loading(self) -> None:
        if self._on_loading:
            self._on_loading(None, None, None)

    def show_dialog(self, dialog: Any) -> None:
        self.page.show_dialog(dialog)
        self.page.update()

    def close_dialog(self, dialog: Optional[Any] = None) -> None:
        if dialog is None:
            self.page.pop_dialog()
        else:
            dialog.open = False
            dialog.update()
        self.page.update()

    def show_snackbar(self, message: str) -> None:
        self.show_dialog(ft.SnackBar(content=ft.Text(message)))

    # ── Ações de negócio ──────────────────────────────────────────────────────

    def do_process_folder(self, folder_path: Path) -> None:
        """Processa pasta selecionada (OCR + scan de arquivos)."""
        self._clear_scan()
        try:
            result = process_folder(folder_path, self.cfg)
        except Exception as exc:
            self._alert("Erro", str(exc))
            return
        self.state.folder_path = folder_path.resolve()
        self.state.ocr_results = result.ocr_results
        self.state.contract_pdf_path = result.contract_pdf_path
        self._apply_file_scan(result)

        self.notify()
        self.page.update()

    def do_refresh_folder(self) -> None:
        """Atualiza a lista de arquivos da pasta selecionada sem rerodar OCR."""
        folder_path = self.state.folder_path
        if folder_path is None:
            return

        try:
            result = scan_folder_files(folder_path, self.cfg)
        except Exception as exc:
            self._alert("Erro", str(exc))
            return

        self._apply_file_scan(result)
        self.notify()
        self.page.update()

    def do_reload_config(self) -> None:
        """Recarrega lojas.config do disco."""
        try:
            self.state.config = load_config()
            apply_browser_settings(self.cfg)
        except ValueError as exc:
            self._alert("Erro", str(exc))
            return
        self.notify()
        self.page.update()
        self.show_snackbar("Configuracao recarregada com sucesso.")

    def do_select_config_file(self, path: Path) -> None:
        """Substitui o lojas.config pelo arquivo selecionado e recarrega."""
        target = _config_path()
        try:
            shutil.copy2(str(path), str(target))
        except Exception as exc:
            self._alert("Erro ao copiar config", str(exc))
            return
        self.do_reload_config()

    def do_open_config(self) -> None:
        """Abre lojas.config no editor padrão (legado)."""
        from ..cadastro_clientes_finger import open_config_file
        try:
            open_config_file()
        except Exception as exc:
            self._alert("Erro", str(exc))

    def do_cancel_process(self) -> None:
        """Sinaliza cancelamento do processo em andamento."""
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.show_snackbar("Cancelando processo...")

    def do_start_process(self, on_done: Callable[[], None]) -> None:
        """Inicia processo Finger ou Vitta em thread separada."""
        from ..services import (
            run_finger_clients, run_finger_orders,
            run_vitta_clients, run_vitta_orders,
        )

        s = self.state
        cfg = self.cfg

        # Fix 2: chamar on_done em TODAS as saídas de validação
        if s.contract_pdf_path is None:
            self._warn("Selecione e processe um contrato antes de continuar.")
            on_done()
            return

        os.environ["FINGER_BROWSER_VISIBLE"] = "N" if s.headless else "Y"
        os.environ["VITTA_BROWSER_VISIBLE"] = "N" if s.headless else "Y"

        # Criar evento de cancelamento para este processo
        self._cancel_event = threading.Event()
        cancel_event = self._cancel_event

        ocr_snap = dict(s.ocr_results)

        if s.fabricante.lower() == "finger":
            store = s.selected_store
            creds = cfg.stores.get(store, {"username": "", "password": ""})
            action = s.action

            if action == "pedidos":
                if not s.txt_files:
                    self._warn("Nenhum arquivo .txt identificado na pasta selecionada.")
                    on_done()
                    return
                if not s.folder_path:
                    self._warn("Selecione novamente a pasta com os arquivos TXT.")
                    on_done()
                    return
                if not s.comprador.strip():
                    self._warn("Informe o comprador antes de cadastrar pedidos.")
                    on_done()
                    return
                if not ocr_snap.get("numero_contrato", "").strip():
                    self._warn("Numero de contrato nao encontrado no OCR.")
                    on_done()
                    return

                comprador = " ".join(s.comprador.strip().upper().split())
                txt_snap = list(s.txt_files)
                total = len(txt_snap)
                self.show_loading("Importando pedidos...", 0, total)

                def progress_cb(current: int, total: int) -> None:
                    self.show_loading(f"Importando pedidos... {current}/{total}", current, total)

                def worker() -> None:
                    try:
                        run_finger_orders(store, creds, ocr_snap, comprador,
                                          txt_snap, str(s.folder_path), progress_cb,
                                          cancel_event=cancel_event)
                    except Exception as exc:
                        self.page.run_thread(lambda e=exc: self._handle_error(e, on_done))
                    else:
                        self.page.run_thread(lambda: self._finish_success(
                            f"Processo de pedidos finalizado para {store}.", on_done))

                threading.Thread(target=worker, daemon=True).start()
            else:
                self.show_loading("Processando cadastro...")

                def worker() -> None:
                    try:
                        run_finger_clients(store, creds, ocr_snap)
                    except Exception as exc:
                        self.page.run_thread(lambda e=exc: self._handle_error(e, on_done))
                    else:
                        self.page.run_thread(lambda: self._finish_success(
                            f"Processo de clientes finalizado para {store}.", on_done))

                threading.Thread(target=worker, daemon=True).start()

        else:  # Vitta
            action = s.vitta_action
            empresa = cfg.vitta.get("empresa", "").strip()
            usuario = cfg.vitta.get("username", "").strip()
            senha = cfg.vitta.get("password", "").strip()
            if not (empresa and usuario and senha):
                self._warn("Preencha as credenciais Vitta no arquivo de configuracao.")
                on_done()
                return

            cred_snap = dict(cfg.vitta)

            if action == "pedidos":
                if not s.folder_path:
                    self._warn("Selecione a pasta do projeto antes de continuar.")
                    on_done()
                    return
                if not s.vitta_xml_files:
                    self._warn("Nenhum .xml localizado em EXECUTIVO/COMPRA/PEDIDOS FABRICAS.")
                    on_done()
                    return
                comprador = " ".join(s.comprador.strip().upper().split())
                if not comprador:
                    self._warn("Informe o nome do comprador.")
                    on_done()
                    return
                cliente_nome = " ".join(s.ocr_results.get("cliente", "").strip().split())
                if not cliente_nome:
                    self._warn("Nome do cliente nao identificado pelo OCR.")
                    on_done()
                    return

                self.show_loading("Importando pedidos Vitta...")
                folder_snap = s.folder_path

                # Callbacks para exibir dialogs Flet a partir da worker thread
                ui_confirm = self._make_ui_confirm()
                ui_warn = self._make_ui_warn()

                def worker() -> None:
                    try:
                        run_vitta_orders(cred_snap, folder_snap, comprador, cliente_nome,
                                         ui_confirm=ui_confirm, ui_warn=ui_warn,
                                         cancel_event=cancel_event)
                    except Exception as exc:
                        self.page.run_thread(lambda e=exc: self._handle_error(e, on_done))
                    else:
                        self.page.run_thread(lambda: self._finish_success(
                            "Pedidos Vitta processados com sucesso.", on_done))

                threading.Thread(target=worker, daemon=True).start()
            else:
                contacts = cfg.contacts
                dados_cliente = {
                    "nome": ocr_snap.get("cliente", ""),
                    "cpf": ocr_snap.get("cpf_cnpj", ""),
                    "contato": contacts.get("pedidos_email", ""),
                    "telefone": ocr_snap.get("telefone", ""),
                    "celular": "",
                    "email": contacts.get("fiscal_email", ""),
                    "cep": ocr_snap.get("cep", ""),
                    "numero": ocr_snap.get("numero", ""),
                    "complemento": ocr_snap.get("complemento", ""),
                    "endereco": ocr_snap.get("endereco_entrega", ""),
                    "bairro": ocr_snap.get("bairro", ""),
                    "cidade": ocr_snap.get("cidade", ""),
                    "estado": ocr_snap.get("estado", ""),
                }

                for field_val, label in [
                    (dados_cliente["nome"], "nome do cliente"),
                    (dados_cliente["cpf"], "CPF"),
                    (dados_cliente["telefone"], "telefone"),
                    (dados_cliente["email"], "e-mail fiscal"),
                    (dados_cliente["cep"], "CEP"),
                    (dados_cliente["endereco"], "endereco"),
                ]:
                    if not field_val.strip():
                        self._warn(f"Informe o {label} para o cadastro Vitta.")
                        on_done()
                        return

                self.show_loading("Processando cadastro Vitta...")

                def worker() -> None:
                    try:
                        run_vitta_clients(cred_snap, dados_cliente)
                    except Exception as exc:
                        self.page.run_thread(lambda e=exc: self._handle_error(e, on_done))
                    else:
                        self.page.run_thread(lambda: self._finish_success(
                            "Cadastro de cliente realizado no portal Vitta.", on_done))

                threading.Thread(target=worker, daemon=True).start()

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _make_ui_confirm(self):
        """Cria um callback bloqueante que exibe um dialog Sim/Não na UI Flet.

        Retorna uma função ``confirm(title, message) -> bool`` que pode ser
        chamada de uma worker thread. A thread fica bloqueada até o usuário
        responder.
        """
        import threading as _th

        def confirm(title: str, message: str) -> bool:
            event = _th.Event()
            result = [True]  # mutable ref

            def _show() -> None:
                from .theme import ACCENT, BORDER, TEXT_LABEL

                def _answer(yes: bool) -> None:
                    result[0] = yes
                    self.close_dialog(dlg)
                    event.set()

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text(title, weight=ft.FontWeight.W_600),
                    content=ft.Text(message),
                    actions=[
                        ft.Button(
                            "Sim",
                            bgcolor=ACCENT,
                            color="#ffffff",
                            height=36,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                            on_click=lambda _: _answer(True),
                        ),
                        ft.OutlinedButton(
                            "Não",
                            height=36,
                            style=ft.ButtonStyle(
                                color=TEXT_LABEL,
                                shape=ft.RoundedRectangleBorder(radius=8),
                                side=ft.BorderSide(1, BORDER),
                            ),
                            on_click=lambda _: _answer(False),
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                self.show_dialog(dlg)

            self.page.run_thread(_show)
            if not event.wait(timeout=120):
                # Timeout: dialog não respondido em 2 minutos — assumir "sim"
                import logging as _logging
                _logging.getLogger(__name__).warning("Timeout aguardando resposta do dialog de confirmacao; assumindo 'sim'.")
            return result[0]

        return confirm

    def _make_ui_warn(self):
        """Cria um callback bloqueante que exibe um aviso na UI Flet.

        Retorna uma função ``warn(title, message)`` que pode ser chamada
        de uma worker thread. A thread fica bloqueada até o usuário fechar.
        """
        import threading as _th

        def warn(title: str, message: str) -> None:
            event = _th.Event()

            def _show() -> None:
                from .theme import BORDER, TEXT_LABEL

                def _close_warn() -> None:
                    self.close_dialog(dlg)
                    event.set()

                dlg = ft.AlertDialog(
                    modal=True,
                    title=ft.Text(title, weight=ft.FontWeight.W_600),
                    content=ft.Text(message),
                    actions=[
                        ft.OutlinedButton(
                            "OK",
                            height=36,
                            style=ft.ButtonStyle(
                                color=TEXT_LABEL,
                                shape=ft.RoundedRectangleBorder(radius=8),
                                side=ft.BorderSide(1, BORDER),
                            ),
                            on_click=lambda _: _close_warn(),
                        ),
                    ],
                )
                self.show_dialog(dlg)

            self.page.run_thread(_show)
            if not event.wait(timeout=120):
                import logging as _logging
                _logging.getLogger(__name__).warning("Timeout aguardando fechamento do dialog de aviso.")

        return warn

    def _clear_scan(self) -> None:
        s = self.state
        s.ocr_results = {}
        s.txt_files = []
        s.vitta_xml_files = []
        s.contract_pdf_path = None
        s.pdf_orders = []
        s.folder_path = None

    def _apply_file_scan(self, result: FolderScanResult) -> None:
        checked_ids = {o["id"] for o in self.state.pdf_orders if o.get("checked")}
        self.state.txt_files = result.txt_files
        self.state.vitta_xml_files = result.vitta_xml_files
        self.state.pdf_orders = result.pdf_orders

        for order in self.state.pdf_orders:
            order["checked"] = order["id"] in checked_ids and order["status"] == "pendente"

        self._auto_detect_fabricante(result)

    def _auto_detect_fabricante(self, result: FolderScanResult) -> None:
        has_txt = bool(result.txt_files)
        has_xml = bool(result.vitta_xml_files)
        if has_txt:
            self.state.fabricante = "Finger"
        elif has_xml:
            self.state.fabricante = "Vitta"

    def _warn(self, msg: str) -> None:
        # Fix 6: AlertDialog com modal=True garante sobreposição
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Aviso"),
            content=ft.Text(msg),
            actions=[ft.TextButton("OK", on_click=lambda _: self.close_dialog(dlg))],
        )
        self.show_dialog(dlg)

    def _alert(self, title: str, msg: str) -> None:
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(msg),
            actions=[ft.TextButton("OK", on_click=lambda _: self.close_dialog(dlg))],
        )
        self.show_dialog(dlg)

    def _is_browser_closed_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        indicators = [
            "browser has been closed", "target closed",
            "target page, context or browser has been closed",
            "connection closed", "browser.close", "protocol error",
            "channel closed", "ns_error_", "session closed",
            "navegador fechado pelo usuario",
        ]
        return any(ind in msg for ind in indicators)

    def _handle_error(self, exc: Exception, on_done: Optional[Callable[[], None]] = None) -> None:
        self.hide_loading()
        self._cancel_event = None
        if on_done:
            on_done()  # Fix 2: sempre re-habilitar o botão mesmo em erros

        if isinstance(exc, ProcessoCancelado):
            self.show_snackbar("Processo cancelado.")
            return

        # Fix 5: verificar CPF ANTES de verificar browser fechado
        msg = str(exc)
        if "cpf" in msg.lower() and "cadastrado" in msg.lower():
            self._alert("CPF já cadastrado",
                        "CPF já cadastrado no portal.\nVerifique os dados e tente novamente.")
            return

        if self._is_browser_closed_error(exc):
            return  # navegador fechado manualmente, não exibir erro

        self._alert("Erro", msg)

    def _finish_success(self, message: str, on_done: Callable[[], None]) -> None:
        self.hide_loading()
        self._cancel_event = None
        on_done()  # Fix 2: re-habilitar botão antes do dialog

        # Fix 6: AlertDialog modal garante sobreposição
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Concluído"),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=lambda _: self._on_success_ok(dlg))],
        )
        self.show_dialog(dlg)

    def _on_success_ok(self, dlg: ft.AlertDialog) -> None:
        """Fecha dialog de sucesso e abre dialog de email se houver PDFs pendentes."""
        self.close_dialog(dlg)
        # Fix 8: exibir tela de email após conclusão dos processos
        self._maybe_show_email_dialog()

    def _maybe_show_email_dialog(self) -> None:
        """Exibe dialog de envio de PDFs se houver pedidos pendentes."""
        from .components.email_dialog import show_email_dialog
        s = self.state
        if not s.folder_path or not s.pdf_orders:
            return
        pendentes = [o for o in s.pdf_orders
                     if o["status"] == "pendente" and o.get("can_send")]
        if pendentes:
            show_email_dialog(self)

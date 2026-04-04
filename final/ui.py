import logging
import os
import subprocess
import sys
import time
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Union

try:
    import sv_ttk
except ImportError:  # pragma: no cover
    sv_ttk = None  # type: ignore[assignment]

try:
    from .cadastro_clientes_finger import (
        STORES,
        OCR_FIELD_KEYS,
        OCR_FIELD_LABELS,
        cadastrar_cliente,
        ensure_config,
        get_contact_settings,
        open_config_file,
    )
except ImportError:  # pragma: no cover
    from cadastro_clientes_finger import (
        STORES,
        OCR_FIELD_KEYS,
        OCR_FIELD_LABELS,
        cadastrar_cliente,
        ensure_config,
        get_contact_settings,
        open_config_file,
    )
try:
    from .cadastro_clientes_vitta import cadastrar_cliente_vitta
except ImportError:  # pragma: no cover
    from cadastro_clientes_vitta import cadastrar_cliente_vitta  # type: ignore
try:
    from .cadastro_pedidos_vitta import cadastrar_pedidos_vitta, _find_xml_and_promob_files
except ImportError:  # pragma: no cover
    from cadastro_pedidos_vitta import cadastrar_pedidos_vitta, _find_xml_and_promob_files  # type: ignore
try:
    from .cadastro_pedidos_finger import cadastrar_pedidos
except ImportError:  # pragma: no cover
    from cadastro_pedidos_finger import cadastrar_pedidos
try:
    from .finger_ocr import extract_contrato_data
except ImportError:  # pragma: no cover
    from finger_ocr import extract_contrato_data
try:
    from .enviar_pedidos_email import (
        scan_pdf_orders,
        extract_client_code,
        build_email_subject,
        build_email_body,
        send_pdf_email,
        mark_email_sent,
        unmark_email_sent,
    )
except ImportError:  # pragma: no cover
    from enviar_pedidos_email import (  # type: ignore
        scan_pdf_orders,
        extract_client_code,
        build_email_subject,
        build_email_body,
        send_pdf_email,
        mark_email_sent,
        unmark_email_sent,
    )

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None  # type: ignore[assignment]
    DND_FILES = None  # type: ignore[assignment]


# ── Paleta de cores ────────────────────────────────────────────────────────────
BG         = "#1e1e2e"
BG_SIDEBAR = "#181825"
BG_CARD    = "#24243e"
BG_ENTRY   = "#2a2a3e"
BG_DROP    = "#1a1a2e"
ACCENT     = "#7c6af7"
ACCENT_HOV = "#6a58e0"
BORDER     = "#383850"
TEXT       = "#cdd6f4"
TEXT_DIM   = "#6c7086"
TEXT_LABEL = "#a6adc8"
SUCCESS    = "#a6e3a1"
WARNING    = "#f9e2af"

WIN_W  = 1080
WIN_H  = 660
SIDE_W = 220


def _clean_drop_value(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("{") and cleaned.endswith("}"):
        cleaned = cleaned[1:-1]
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
    if " " in cleaned and not Path(cleaned).exists():
        cleaned = cleaned.split()[0]
    return cleaned


def run_ui() -> None:
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    root.title("Encomendas Edy")
    root.configure(bg=BG)
    root.resizable(True, True)

    # ── Centrar janela na tela ─────────────────────────────────────────────────
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x  = (sw - WIN_W) // 2
    y  = (sh - WIN_H) // 2
    root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
    root.minsize(860, 540)

    # ── Tema e fontes ──────────────────────────────────────────────────────────
    if sv_ttk is not None:
        sv_ttk.set_theme("dark")

    F_TITLE  = ("Segoe UI", 12, "bold")
    F_LABEL  = ("Segoe UI", 8)
    F_BASE   = ("Segoe UI", 9)
    F_SMALL  = ("Segoe UI", 8)
    F_BADGE  = ("Segoe UI", 7, "bold")

    # ── Estilos customizados ───────────────────────────────────────────────────
    style = ttk.Style()

    style.configure("Sidebar.TFrame",      background=BG_SIDEBAR)
    style.configure("Card.TFrame",         background=BG_CARD)
    style.configure("Main.TFrame",         background=BG)

    style.configure("Sidebar.TLabel",      background=BG_SIDEBAR, foreground=TEXT,      font=F_BASE)
    style.configure("SidebarDim.TLabel",   background=BG_SIDEBAR, foreground=TEXT_LABEL, font=F_SMALL)
    style.configure("SidebarTitle.TLabel", background=BG_SIDEBAR, foreground=TEXT,       font=F_TITLE)
    style.configure("Card.TLabel",         background=BG_CARD,    foreground=TEXT,       font=F_BASE)
    style.configure("CardDim.TLabel",      background=BG_CARD,    foreground=TEXT_DIM,   font=F_SMALL)
    style.configure("CardTitle.TLabel",    background=BG_CARD,    foreground=TEXT,       font=("Segoe UI", 9, "bold"))
    style.configure("Main.TLabel",         background=BG,         foreground=TEXT,       font=F_BASE)

    style.configure("Sidebar.TCheckbutton", background=BG_SIDEBAR, foreground=TEXT_LABEL, font=F_SMALL)
    style.configure("Sidebar.TRadiobutton", background=BG_SIDEBAR, foreground=TEXT_LABEL, font=F_SMALL)

    style.configure("Sidebar.TEntry",  fieldbackground=BG_ENTRY, foreground=TEXT, font=F_BASE)
    style.configure("Card.TEntry",     fieldbackground=BG_ENTRY, foreground=TEXT, font=F_BASE)

    style.configure("Sidebar.TCombobox", fieldbackground=BG_ENTRY, foreground=TEXT, font=F_BASE)

    style.configure("Action.TButton",
                    background=ACCENT, foreground="#ffffff",
                    font=("Segoe UI", 9, "bold"), padding=(8, 5))
    style.map("Action.TButton",
              background=[("active", ACCENT_HOV), ("disabled", "#3a3a52")])

    style.configure("Ghost.TButton",
                    background=BG_SIDEBAR, foreground=TEXT_LABEL,
                    font=F_SMALL, padding=(6, 4))
    style.map("Ghost.TButton",
              background=[("active", BORDER)],
              foreground=[("active", TEXT)])

    # Scrollbar: herda o estilo padrão do tema (vertical prefix é adicionado automaticamente)
    style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=BG_CARD, borderwidth=0)

    # ── Separator horizontal fino ──────────────────────────────────────────────
    style.configure("Sep.TSeparator", background=BORDER)

    # ── Configuração ──────────────────────────────────────────────────────────
    try:
        config_data = ensure_config(include_meta=True)
    except ValueError as exc:
        messagebox.showerror("Erro", str(exc))
        root.destroy()
        return

    credentials      = config_data["stores"]
    ocr_config       = config_data.get("ocr", {})
    vitta_credentials: Dict[str, str] = dict(
        config_data.get("vitta", {"empresa": "", "username": "", "password": ""})
    )
    email_smtp_config: dict = dict(config_data.get("email_smtp", {
        "host": "smtp.exemplo.com.br", "port": 587,
        "use_tls": True, "destino_fixo": "pedidos@exemplo.com.br",
    }))
    usuarios_email: dict = dict(config_data.get("usuarios_email", {}))
    empresa_info: dict = dict(config_data.get("empresa_info", {"codigo": "274", "nome": "EDY SERVICOS EM MOVEIS LTDA"}))
    fornecedores_email_config: dict = dict(config_data.get("fornecedores_email", {}))
    contacts_config: dict = dict(get_contact_settings(config_data))

    browser_settings      = config_data.get("settings", {}) if isinstance(config_data, dict) else {}
    finger_browser_setting = str(browser_settings.get("finger_browser_visible", "Y")).strip().upper()
    vitta_browser_setting  = str(browser_settings.get("vitta_browser_visible",  "Y")).strip().upper()
    os.environ["FINGER_BROWSER_VISIBLE"] = finger_browser_setting
    os.environ["VITTA_BROWSER_VISIBLE"]  = vitta_browser_setting
    os.environ["NAVEGADOR_VISIVEL"]      = finger_browser_setting

    # ── State vars ─────────────────────────────────────────────────────────────
    selected_store   = tk.StringVar(value=STORES[0])
    action_var       = tk.StringVar(value="clientes")
    headless_var     = tk.BooleanVar(value=True)
    comprador_var    = tk.StringVar()
    fabricante_var   = tk.StringVar(value="Finger")
    vitta_action_var = tk.StringVar(value="clientes")
    project_count_var = tk.StringVar(value="Nenhum arquivo identificado")

    ocr_results: Dict[str, str]  = {}
    txt_files:   List[Path]      = []
    vitta_xml_files: List[Path]  = []
    txt_root: Optional[Path]     = None
    contract_pdf_path: Optional[Path] = None
    pdf_orders: List[dict]       = []
    pdf_root: Optional[Path]     = None

    ocr_result_vars: Dict[str, tk.StringVar] = {key: tk.StringVar() for key in OCR_FIELD_KEYS}

    loading_popup: Optional[tk.Toplevel]    = None
    loading_progress: Optional[ttk.Progressbar] = None
    loading_message = tk.StringVar(value="")

    # ── Helper: centrar janela filha ───────────────────────────────────────────
    def _center_on_root(window: Union[tk.Tk, tk.Toplevel],
                        width: Optional[int] = None,
                        height: Optional[int] = None) -> None:
        window.update_idletasks()
        root.update_idletasks()
        w = window.winfo_width()  if width  is None else width
        h = window.winfo_height() if height is None else height
        if w <= 1 or h <= 1:
            w = window.winfo_reqwidth()
            h = window.winfo_reqheight()
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        window.geometry(f"{w}x{h}+{rx + max((rw - w) // 2, 0)}+{ry + max((rh - h) // 2, 0)}")

    # ── Loading popup ──────────────────────────────────────────────────────────
    def show_loading(message: str) -> None:
        nonlocal loading_popup, loading_progress
        loading_message.set(message)
        if loading_popup is not None and loading_popup.winfo_exists():
            try:
                if loading_progress is not None:
                    loading_progress.start(10)
            except tk.TclError:
                pass
            loading_popup.deiconify()
            loading_popup.lift()
            _center_on_root(loading_popup)
            try:
                loading_popup.focus_force()
            except tk.TclError:
                pass
            return
        popup = tk.Toplevel(root)
        loading_popup = popup
        popup.title("Aguarde")
        popup.transient(root)
        popup.resizable(False, False)
        popup.configure(bg=BG_CARD)
        popup.geometry("300x120")
        _center_on_root(popup, 300, 120)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        try:
            popup.attributes("-topmost", True)
            popup.after(200, lambda: popup.attributes("-topmost", False))
        except tk.TclError:
            pass

        pf = ttk.Frame(popup, padding=(20, 16), style="Card.TFrame")
        pf.pack(expand=True, fill="both")
        ttk.Label(pf, textvariable=loading_message, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(pf, text="Por favor, aguarde...", style="CardDim.TLabel").pack(anchor="w", pady=(2, 10))
        progress = ttk.Progressbar(pf, mode="indeterminate", length=240)
        progress.pack(fill="x")
        try:
            progress.start(10)
        except tk.TclError:
            pass
        loading_progress = progress
        popup.update_idletasks()
        try:
            popup.grab_set()
        except tk.TclError:
            pass

    def hide_loading() -> None:
        nonlocal loading_popup, loading_progress
        if loading_progress is not None:
            try:
                loading_progress.stop()
            except tk.TclError:
                pass
            loading_progress = None
        if loading_popup is not None:
            try:
                loading_popup.grab_release()
            except tk.TclError:
                pass
            try:
                loading_popup.destroy()
            except tk.TclError:
                pass
            loading_popup = None

    def update_loading_progress(current: int, total: int) -> None:
        """Atualiza loading popup com progresso determinado (chame via root.after)."""
        nonlocal loading_progress
        if loading_progress is None:
            return
        pct = int(100 * current / total) if total > 0 else 0
        loading_message.set(f"Importando pedidos... {current}/{total} ({pct}%)")
        try:
            loading_progress.configure(mode="determinate", maximum=total, value=current)
        except tk.TclError:
            pass

    def _finish_worker_success(button: ttk.Button, message: str) -> None:
        hide_loading()
        button.config(state="normal")
        messagebox.showinfo("Sucesso", message)
        _maybe_show_pdf_email_dialog()

    def _is_browser_closed_error(exc: Exception) -> bool:
        """Verifica se a excecao indica que o navegador foi fechado manualmente."""
        msg = str(exc).lower()
        indicators = [
            "browser has been closed",
            "target closed",
            "target page, context or browser has been closed",
            "connection closed",
            "browser.close",
            "protocol error",
            "channel closed",
            "ns_error_",
            "session closed",
            "navegador fechado pelo usuario",
        ]
        return any(indicator in msg for indicator in indicators)

    def _handle_worker_exception(button: ttk.Button, exc: Exception) -> None:
        hide_loading()
        button.config(state="normal")
        # Se o navegador foi fechado manualmente, nao mostrar popup de erro
        if _is_browser_closed_error(exc):
            return
        msg = str(exc)
        if "cpf" in msg.lower() and "cadastrado" in msg.lower():
            messagebox.showwarning("CPF existente", "CPF ja cadastrado no portal. Navegador fechado.")
        else:
            messagebox.showerror("Erro", msg)

    # ── Painel de Logs ─────────────────────────────────────────────────────────
    log_visible = tk.BooleanVar(value=False)
    _log_lines: List[str] = []
    _MAX_LOG_LINES = 500

    # ── Layout raiz ────────────────────────────────────────────────────────────
    root.columnconfigure(1, weight=1)
    root.rowconfigure(0, weight=1)

    # ═══════════════════════════════════════════════════════════════════════════
    #  SIDEBAR
    # ═══════════════════════════════════════════════════════════════════════════
    sidebar = ttk.Frame(root, style="Sidebar.TFrame", padding=(16, 18, 16, 14))
    sidebar.grid(row=0, column=0, sticky="ns")
    sidebar.grid_propagate(False)
    sidebar.configure(width=SIDE_W)
    sidebar.columnconfigure(0, weight=1)

    # Título
    ttk.Label(sidebar, text="Encomendas Edy", style="SidebarTitle.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 2))
    ttk.Label(sidebar, text="Protótipo executado por Kevin", style="SidebarDim.TLabel").grid(
        row=1, column=0, sticky="w", pady=(0, 12))

    ttk.Separator(sidebar, orient="horizontal", style="Sep.TSeparator").grid(
        row=2, column=0, sticky="ew", pady=(0, 12))

    # Comprador
    ttk.Label(sidebar, text="COMPRADOR", style="SidebarDim.TLabel").grid(
        row=3, column=0, sticky="w", pady=(0, 3))
    comprador_entry = ttk.Entry(sidebar, textvariable=comprador_var, font=F_BASE)
    comprador_entry.grid(row=4, column=0, sticky="ew", pady=(0, 10))

    # Fabricante
    ttk.Label(sidebar, text="FABRICANTE", style="SidebarDim.TLabel").grid(
        row=5, column=0, sticky="w", pady=(0, 3))
    fabricante_combo = ttk.Combobox(
        sidebar, values=("Finger", "Vitta"),
        textvariable=fabricante_var, state="readonly", font=F_BASE)
    fabricante_combo.grid(row=6, column=0, sticky="ew", pady=(0, 10))

    ttk.Separator(sidebar, orient="horizontal", style="Sep.TSeparator").grid(
        row=7, column=0, sticky="ew", pady=(2, 10))

    # Container de ações
    actions_container = ttk.Frame(sidebar, style="Sidebar.TFrame")
    actions_container.grid(row=8, column=0, sticky="ew")
    actions_container.columnconfigure(0, weight=1)

    # ── Seção Finger ──────────────────────────────────────────────────────────
    finger_section = ttk.Frame(actions_container, style="Sidebar.TFrame")
    finger_section.grid(row=0, column=0, sticky="ew")
    finger_section.columnconfigure(0, weight=1)

    ttk.Label(finger_section, text="LOJA", style="SidebarDim.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 3))
    loja_combo = ttk.Combobox(
        finger_section, values=STORES,
        textvariable=selected_store, state="readonly", font=F_BASE)
    loja_combo.grid(row=1, column=0, sticky="ew", pady=(0, 10))

    ttk.Label(finger_section, text="ACAO", style="SidebarDim.TLabel").grid(
        row=2, column=0, sticky="w", pady=(0, 4))
    finger_actions = ttk.Frame(finger_section, style="Sidebar.TFrame")
    finger_actions.grid(row=3, column=0, sticky="ew")
    ttk.Radiobutton(finger_actions, text="Cadastrar clientes",
                    variable=action_var, value="clientes",
                    style="Sidebar.TRadiobutton").pack(anchor="w", pady=2)
    ttk.Radiobutton(finger_actions, text="Cadastrar pedidos",
                    variable=action_var, value="pedidos",
                    style="Sidebar.TRadiobutton").pack(anchor="w", pady=2)

    # ── Seção Vitta ───────────────────────────────────────────────────────────
    vitta_section = ttk.Frame(actions_container, style="Sidebar.TFrame")
    vitta_section.grid(row=0, column=0, sticky="ew")
    vitta_section.columnconfigure(0, weight=1)

    ttk.Label(vitta_section, text="ACAO", style="SidebarDim.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 4))
    ttk.Radiobutton(vitta_section, text="Cadastrar clientes",
                    variable=vitta_action_var, value="clientes",
                    style="Sidebar.TRadiobutton").grid(row=1, column=0, sticky="w", pady=2)
    ttk.Radiobutton(vitta_section, text="Cadastrar pedidos",
                    variable=vitta_action_var, value="pedidos",
                    style="Sidebar.TRadiobutton").grid(row=2, column=0, sticky="w", pady=2)
    vitta_section.grid_remove()

    # Spacer que empurra os botões para baixo
    sidebar_spacer = ttk.Frame(sidebar, style="Sidebar.TFrame")
    sidebar_spacer.grid(row=9, column=0, sticky="nsew")
    sidebar.rowconfigure(9, weight=1)

    ttk.Separator(sidebar, orient="horizontal", style="Sep.TSeparator").grid(
        row=10, column=0, sticky="ew", pady=(8, 8))

    headless_check = ttk.Checkbutton(
        sidebar, text="Ocultar navegador",
        variable=headless_var, style="Sidebar.TCheckbutton")
    headless_check.grid(row=11, column=0, sticky="w", pady=(0, 8))

    start_button = ttk.Button(sidebar, text="Iniciar processo",
                              style="Action.TButton")
    start_button.grid(row=12, column=0, sticky="ew", pady=(0, 4))

    # Botão de envio de PDFs standalone (independente de Finger/Vitta)
    send_pdf_button = ttk.Button(sidebar, text="Enviar PDFs (0 pendentes)",
                                 style="Ghost.TButton", state="disabled")
    send_pdf_button.grid(row=13, column=0, sticky="ew", pady=(0, 6))

    buttons_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
    buttons_frame.grid(row=14, column=0, sticky="ew")
    buttons_frame.columnconfigure(0, weight=1)
    buttons_frame.columnconfigure(1, weight=1)

    reload_button   = ttk.Button(buttons_frame, text="Carregar .config", style="Ghost.TButton")
    open_config_btn = ttk.Button(buttons_frame, text="Abrir .config",     style="Ghost.TButton")
    reload_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
    open_config_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

    # Toggle + Clear logs
    log_buttons_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
    log_buttons_frame.grid(row=15, column=0, sticky="ew", pady=(4, 0))
    log_buttons_frame.columnconfigure(0, weight=1)
    log_buttons_frame.columnconfigure(1, weight=1)
    log_toggle_btn = ttk.Button(log_buttons_frame, text="Mostrar logs", style="Ghost.TButton")
    log_clear_btn  = ttk.Button(log_buttons_frame, text="Limpar logs",  style="Ghost.TButton")
    log_toggle_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
    log_clear_btn.grid(row=0, column=1,  sticky="ew", padx=(3, 0))

    # ═══════════════════════════════════════════════════════════════════════════
    #  CONTEÚDO PRINCIPAL
    # ═══════════════════════════════════════════════════════════════════════════
    content = ttk.Frame(root, style="Main.TFrame", padding=(14, 14, 14, 14))
    content.grid(row=0, column=1, sticky="nsew")
    content.columnconfigure(0, weight=1)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(1, weight=1)

    # ── Card: Pasta do Projeto ─────────────────────────────────────────────────
    def _make_card(parent, title, row, col, rowspan=1, colspan=1,
                   padx=(0, 0), pady=(0, 8), sticky="nsew") -> ttk.Frame:
        outer = tk.Frame(parent, bg=BG_CARD, bd=0, highlightthickness=1,
                         highlightbackground=BORDER)
        outer.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan,
                   sticky=sticky, padx=padx, pady=pady)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        hdr = tk.Frame(outer, bg=BG_CARD)
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
        tk.Label(hdr, text=title, bg=BG_CARD, fg=TEXT_LABEL,
                 font=F_BADGE).pack(side="left")
        body = tk.Frame(outer, bg=BG_CARD)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 10))
        body.columnconfigure(0, weight=1)
        return body

    folder_body = _make_card(content, "PASTA DO PROJETO", row=0, col=0,
                             padx=(0, 6), pady=(0, 8))
    folder_body.rowconfigure(0, weight=1)

    drop_area = tk.Frame(
        folder_body,
        bg=BG_DROP, height=90,
        highlightbackground=ACCENT, highlightthickness=1,
        bd=0, cursor="hand2",
    )
    drop_area.grid(row=0, column=0, sticky="ew")
    drop_area.grid_propagate(False)

    drop_inner = tk.Frame(drop_area, bg=BG_DROP)
    drop_inner.place(relx=0.5, rely=0.5, anchor="center")
    tk.Label(drop_inner, text="+ Selecionar pasta", bg=BG_DROP,
             fg=ACCENT, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, pady=(0, 2))
    drop_hint_label = tk.Label(
        drop_inner, text="Clique ou arraste a pasta do projeto",
        bg=BG_DROP, fg=TEXT_DIM, font=F_SMALL)
    drop_hint_label.grid(row=1, column=0)

    # Hover highlight
    def _drop_enter(_e=None):
        drop_area.configure(highlightbackground=TEXT, highlightthickness=1)
    def _drop_leave(_e=None):
        drop_area.configure(highlightbackground=ACCENT, highlightthickness=1)
    for w in (drop_area, drop_inner):
        w.bind("<Enter>", _drop_enter)
        w.bind("<Leave>", _drop_leave)

    # ── Card: Projetos Encontrados ─────────────────────────────────────────────
    proj_body = _make_card(content, "PROJETOS ENCONTRADOS", row=0, col=1,
                           padx=(6, 0), pady=(0, 8), sticky="nsew")
    proj_body.rowconfigure(1, weight=1)

    ttk.Label(proj_body, textvariable=project_count_var,
              style="CardDim.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))

    tree_frame = tk.Frame(proj_body, bg=BG_CARD)
    tree_frame.grid(row=1, column=0, sticky="nsew")
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)

    project_tree = ttk.Treeview(tree_frame, columns=("path",), show="tree",
                                height=6)
    project_tree.column("path", width=0, stretch=False)
    project_tree.heading("path", text="")
    project_tree.grid(row=0, column=0, sticky="nsew")

    project_scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=project_tree.yview)
    project_scroll.grid(row=0, column=1, sticky="ns")
    project_tree.configure(yscrollcommand=project_scroll.set)

    remove_project_button = ttk.Button(proj_body, text="Remover selecionado",
                                       style="Ghost.TButton", state="disabled")
    remove_project_button.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    # ── Card: Informações do Cliente (linha 1, col 0+1) ───────────────────────
    client_outer = tk.Frame(content, bg=BG_CARD, bd=0,
                            highlightthickness=1, highlightbackground=BORDER)
    client_outer.grid(row=1, column=0, columnspan=2, sticky="nsew",
                      padx=(0, 0), pady=(0, 0))
    client_outer.columnconfigure(0, weight=1)

    chdr = tk.Frame(client_outer, bg=BG_CARD)
    chdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 0))
    tk.Label(chdr, text="INFORMACOES DO CLIENTE", bg=BG_CARD,
             fg=TEXT_LABEL, font=F_BADGE).pack(side="left")

    client_grid = tk.Frame(client_outer, bg=BG_CARD)
    client_grid.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 10))

    # 4 colunas: label | entry | label | entry  (2 campos por linha)
    for c in range(4):
        client_grid.columnconfigure(c, weight=1 if c % 2 == 1 else 0)

    for idx, key in enumerate(OCR_FIELD_KEYS):
        row_n = idx // 2
        col_n = (idx % 2) * 2

        lbl = tk.Label(client_grid,
                       text=f"{OCR_FIELD_LABELS[key]}",
                       bg=BG_CARD, fg=TEXT_LABEL, font=F_SMALL,
                       anchor="w")
        lbl.grid(row=row_n * 2, column=col_n, columnspan=2,
                 sticky="w", padx=(0 if col_n == 0 else 12, 4), pady=(4, 0))

        ent = tk.Entry(client_grid,
                       textvariable=ocr_result_vars[key],
                       font=F_BASE,
                       bg=BG_ENTRY, fg=TEXT,
                       insertbackground=TEXT,
                       relief="flat", bd=4,
                       highlightthickness=1,
                       highlightbackground=BORDER,
                       highlightcolor=ACCENT)
        ent.grid(row=row_n * 2 + 1, column=col_n, columnspan=2,
                 sticky="ew", padx=(0 if col_n == 0 else 12, 4), pady=(0, 2))

    # ── Painel de Logs (linha 2 do content) ───────────────────────────────────
    content.rowconfigure(2, weight=0)

    log_outer = tk.Frame(content, bg=BG_CARD, bd=0,
                         highlightthickness=1, highlightbackground=BORDER)

    log_hdr = tk.Frame(log_outer, bg=BG_CARD)
    log_hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 0))
    log_outer.columnconfigure(0, weight=1)
    tk.Label(log_hdr, text="LOGS DE EXECUÇÃO", bg=BG_CARD, fg=TEXT_LABEL,
             font=("Segoe UI", 7, "bold")).pack(side="left")

    log_body = tk.Frame(log_outer, bg=BG_CARD)
    log_body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(2, 8))
    log_body.columnconfigure(0, weight=1)
    log_body.rowconfigure(0, weight=1)
    log_outer.rowconfigure(1, weight=1)

    log_text = tk.Text(
        log_body, height=6, bg="#11111b", fg=TEXT_DIM,
        font=("Consolas", 8), relief="flat", bd=0,
        state="disabled", wrap="word", selectbackground=BORDER,
    )
    log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.grid(row=0, column=0, sticky="nsew")
    log_scroll.grid(row=0, column=1, sticky="ns")

    # Tags de cor por nível
    log_text.tag_configure("INFO",    foreground=TEXT_DIM)
    log_text.tag_configure("WARNING", foreground=WARNING)
    log_text.tag_configure("ERROR",   foreground="#f38ba8")
    log_text.tag_configure("DEBUG",   foreground="#585b70")

    def _append_log(level: str, msg: str) -> None:
        _log_lines.append(msg)
        if len(_log_lines) > _MAX_LOG_LINES:
            _log_lines.pop(0)
        try:
            log_text.configure(state="normal")
            log_text.insert("end", msg + "\n", level)
            # Limitar linhas visíveis
            lines = int(log_text.index("end-1c").split(".")[0])
            if lines > _MAX_LOG_LINES:
                log_text.delete("1.0", f"{lines - _MAX_LOG_LINES}.0")
            log_text.see("end")
            log_text.configure(state="disabled")
        except tk.TclError:
            pass

    class _UILogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level = record.levelname
                ts = self.formatter.formatTime(record, "%H:%M:%S") if self.formatter else ""
                msg = f"[{ts}] {level:7s} {record.getMessage()}"
                root.after(0, lambda m=msg, lv=level: _append_log(lv, m))
            except Exception:
                pass

    _ui_handler = _UILogHandler()
    _ui_handler.setFormatter(logging.Formatter())
    _ui_handler.setLevel(logging.DEBUG)

    # Registrar o handler em todos os loggers do projeto
    for _logger_name in (
        "final.cadastro_pedidos_vitta",
        "final.cadastro_pedidos_finger",
        "cadastro_pedidos_vitta",
        "cadastro_pedidos_finger",
        "final.enviar_pedidos_email",
        "enviar_pedidos_email",
    ):
        _lg = logging.getLogger(_logger_name)
        _lg.addHandler(_ui_handler)
        if not _lg.level or _lg.level > logging.DEBUG:
            _lg.setLevel(logging.DEBUG)

    def _log_ui(level: str, msg: str) -> None:
        """Loga uma mensagem diretamente no painel da UI (thread-safe)."""
        import time as _t
        ts = _t.strftime("%H:%M:%S")
        root.after(0, lambda m=f"[{ts}] {level:7s} {msg}", lv=level: _append_log(lv, m))

    def _toggle_logs() -> None:
        if log_visible.get():
            log_outer.grid_remove()
            log_visible.set(False)
            log_toggle_btn.config(text="Mostrar logs")
        else:
            log_outer.grid(row=2, column=0, columnspan=2, sticky="ew",
                           padx=0, pady=(6, 0))
            log_visible.set(True)
            log_toggle_btn.config(text="Ocultar logs")

    def _clear_logs() -> None:
        _log_lines.clear()
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")

    # ═══════════════════════════════════════════════════════════════════════════
    #  LÓGICA / CALLBACKS
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_send_pdf_button() -> None:
        """Atualiza texto e estado do botão 'Enviar PDFs' com base nos pedidos detectados."""
        pendentes = [o for o in pdf_orders if o["status"] == "pendente" and o.get("can_send")]
        n = len(pendentes)
        if n > 0:
            send_pdf_button.config(text=f"Enviar PDFs ({n} pendente{'s' if n != 1 else ''})",
                                   state="normal")
        else:
            total = len(pdf_orders)
            if total > 0:
                send_pdf_button.config(text="Enviar PDFs (0 pendentes)", state="disabled")
            else:
                send_pdf_button.config(text="Enviar PDFs (0 pendentes)", state="disabled")

    def update_project_list() -> None:
        remove_project_button.config(state="disabled")
        project_tree.delete(*project_tree.get_children())
        project_tree.tag_configure("pdf_pendente",  foreground=ACCENT)
        project_tree.tag_configure("pdf_enviado",   foreground=SUCCESS)
        project_tree.tag_configure("pdf_sem_email", foreground=WARNING)

        fabricante = fabricante_var.get().lower()
        if fabricante == "vitta":
            items, suffix, empty_text = vitta_xml_files, ".xml", "Nenhum .xml identificado"
        else:
            items, suffix, empty_text = txt_files, ".txt", "Nenhum .txt identificado"
        has_main_files = False
        if items:
            seen: set = set()
            unique = []
            for p in items:
                if p.name.lower() not in seen:
                    seen.add(p.name.lower())
                    unique.append(p)
            if unique:
                has_main_files = True
                count_label = f"{len(unique)} arquivo(s) {suffix}"
                for p in unique:
                    node = project_tree.insert("", "end", text=p.name)
                    project_tree.set(node, "path", str(p))

        # Mostrar PDFs de pedido imediatamente ao carregar a pasta
        n_pdf_pend = 0
        if pdf_orders:
            for o in pdf_orders:
                tag = f"pdf_{o['status']}"
                prefix = "✉ " if o["status"] == "pendente" and o.get("can_send") else \
                         "✓ " if o["status"] == "enviado" else "⚠ "
                label = f"{prefix}PEDIDO {o['supplier']}"
                project_tree.insert("", "end", text=label, tags=(tag,))
                if o["status"] == "pendente" and o.get("can_send"):
                    n_pdf_pend += 1

        if has_main_files or pdf_orders:
            parts = []
            if has_main_files:
                parts.append(count_label)
            if pdf_orders:
                total_pdf = len(pdf_orders)
                parts.append(f"{total_pdf} PDF(s) de pedido")
            project_count_var.set(" | ".join(parts))
            # Atualizar estado do botão de envio de PDFs
            _update_send_pdf_button()
            return

        project_count_var.set(empty_text)
        node = project_tree.insert("", "end", text=empty_text)
        project_tree.set(node, "path", "")
        _update_send_pdf_button()

    def _update_remove_button_state(*_args: object) -> None:
        selected = project_tree.selection()
        if not selected:
            remove_project_button.config(state="disabled")
            return
        remove_project_button.config(
            state="normal" if project_tree.set(selected[0], "path") else "disabled")

    def remove_selected_project() -> None:
        nonlocal txt_files, vitta_xml_files
        selected = project_tree.selection()
        if not selected:
            messagebox.showwarning("Aviso", "Selecione um arquivo para remover.")
            return
        path_value = project_tree.set(selected[0], "path")
        if not path_value:
            messagebox.showwarning("Aviso", "Este item nao pode ser removido.")
            return
        target = Path(path_value)
        if fabricante_var.get().lower() == "vitta":
            vitta_xml_files = [p for p in vitta_xml_files if p != target]
        else:
            txt_files = [p for p in txt_files if p != target]
        update_project_list()

    remove_project_button.config(command=remove_selected_project)
    project_tree.bind("<<TreeviewSelect>>", _update_remove_button_state)

    def update_finger_display(*_args: object) -> None:
        if selected_store.get() not in credentials and credentials:
            selected_store.set(next(iter(credentials.keys())))

    def _set_ocr_results(results: Dict[str, str]) -> None:
        for key in OCR_FIELD_KEYS:
            ocr_result_vars[key].set(results.get(key, ""))

    def _show_loading(message: str) -> tk.Toplevel:
        win = tk.Toplevel(root)
        win.title("Processando")
        win.transient(root)
        win.resizable(False, False)
        win.grab_set()
        ttk.Label(win, text=message, padding=20).pack(expand=True)
        _center_on_root(win)
        return win

    def clear_ocr_results() -> None:
        nonlocal ocr_results, txt_files, txt_root, vitta_xml_files, contract_pdf_path, pdf_orders, pdf_root
        for var in ocr_result_vars.values():
            var.set("")
        ocr_results = {}
        txt_files = []
        txt_root = None
        vitta_xml_files = []
        contract_pdf_path = None
        pdf_orders = []
        pdf_root = None
        update_project_list()

    def process_folder(folder_path: Path) -> None:
        nonlocal ocr_results, txt_files, txt_root, vitta_xml_files, contract_pdf_path, pdf_orders, pdf_root
        folder_path = folder_path.resolve()
        if not folder_path.is_dir():
            messagebox.showwarning("Aviso", "Selecione uma pasta valida.")
            return
        clear_ocr_results()
        loading = _show_loading("Identificando arquivos...")
        try:
            pdf_path, results  = extract_contrato_data(folder_path, ocr_config)
            txt_files          = sorted(folder_path.rglob("*.txt"))
            vitta_pairs        = _find_xml_and_promob_files(folder_path)
            vitta_xml_files    = [xml for (xml, _) in vitta_pairs]
            # Detectar PDFs de pedido de fornecedores
            _config_snapshot = {
                "fornecedores_email": dict(fornecedores_email_config),
            }
            found_pdfs = scan_pdf_orders(folder_path, _config_snapshot)
        except (FileNotFoundError, NotADirectoryError, ImportError) as exc:
            messagebox.showerror("Erro", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao processar contrato: {exc}")
            return
        finally:
            loading.destroy()
        ocr_results       = {key: results.get(key, "") for key in OCR_FIELD_KEYS}
        _set_ocr_results(ocr_results)
        contract_pdf_path = pdf_path
        txt_root          = folder_path
        pdf_orders        = found_pdfs
        pdf_root          = folder_path
        update_project_list()

    def choose_folder() -> None:
        selected = filedialog.askdirectory()
        if selected:
            process_folder(Path(selected))

    def handle_drop(event: object) -> None:
        path_value = ""
        if isinstance(event, tk.Event) and hasattr(event, "data"):
            path_value = _clean_drop_value(str(event.data))
        if not path_value:
            return
        resolved = Path(path_value)
        if resolved.is_dir():
            process_folder(resolved)
        else:
            messagebox.showwarning("Aviso", "Solte apenas pastas para processar o contrato.")

    def reload_config() -> None:
        nonlocal credentials, ocr_config, vitta_credentials
        nonlocal email_smtp_config, usuarios_email, empresa_info, fornecedores_email_config
        nonlocal contacts_config
        try:
            data = ensure_config(include_meta=True)
        except ValueError as exc:
            messagebox.showerror("Erro", str(exc))
            return
        credentials      = data["stores"]
        ocr_config       = data.get("ocr", {})
        vitta_credentials = dict(data.get("vitta", {"empresa": "", "username": "", "password": ""}))
        email_smtp_config = dict(data.get("email_smtp", email_smtp_config))
        usuarios_email    = dict(data.get("usuarios_email", {}))
        empresa_info      = dict(data.get("empresa_info", empresa_info))
        fornecedores_email_config = dict(data.get("fornecedores_email", {}))
        contacts_config = dict(get_contact_settings(data))
        update_finger_display()
        update_project_list()
        messagebox.showinfo("Configuracao", "Configuracao recarregada com sucesso.")

    def handle_open_config() -> None:
        try:
            open_config_file()
        except Exception as exc:
            messagebox.showerror("Erro", f"Nao foi possivel abrir o arquivo: {exc}")

    def start_finger_process() -> None:
        store        = selected_store.get()
        creds        = credentials.get(store, {"username": "", "password": ""})
        current_action = action_var.get()
        if contract_pdf_path is None:
            messagebox.showwarning("Aviso", "Selecione e processe um contrato antes de continuar.")
            return
        if current_action == "pedidos":
            if not txt_files:
                messagebox.showwarning("Aviso", "Nenhum arquivo .txt identificado na pasta selecionada.")
                return
            if txt_root is None:
                messagebox.showwarning("Aviso", "Selecione novamente a pasta com os arquivos TXT.")
                return
            if not comprador_var.get().strip():
                messagebox.showwarning("Aviso", "Informe o comprador antes de cadastrar pedidos.")
                return
        ocr_snapshot = {key: ocr_result_vars[key].get().strip() for key in OCR_FIELD_KEYS}
        if current_action == "pedidos" and not ocr_snapshot.get("numero_contrato", "").strip():
            messagebox.showwarning("Aviso", "Numero de contrato nao encontrado no OCR.")
            return

        start_button.config(state="disabled")
        os.environ["FINGER_BROWSER_VISIBLE"] = "N" if headless_var.get() else "Y"
        if current_action == "pedidos":
            show_loading("Importando no modo Invisivel..." if headless_var.get() else "Importando pedidos...")
        else:
            show_loading("Cadastro no modo Invisivel..." if headless_var.get() else "Processando cadastro...")

        comprador_snapshot = " ".join(comprador_var.get().strip().upper().split()) if current_action == "pedidos" else ""
        if current_action == "pedidos":
            comprador_var.set(comprador_snapshot)
        txt_snapshot    = list(txt_files)
        txt_root_snap   = txt_root

        total_itens = len(txt_snapshot) if current_action == "pedidos" else 0
        if current_action == "pedidos" and total_itens > 0:
            # Preparar progressbar no modo determinado assim que soubermos o total
            root.after(50, lambda: update_loading_progress(0, total_itens))

        def _finger_progress_cb(current: int, total: int) -> None:
            root.after(0, lambda c=current, t=total: update_loading_progress(c, t))

        def worker() -> None:
            try:
                if current_action == "pedidos":
                    itens = [(Path(p).stem.upper(), str(p)) for p in txt_snapshot]
                    cadastrar_pedidos(store, creds, dados_ocr=ocr_snapshot,
                                      comprador=comprador_snapshot, itens=itens,
                                      registro_dir=str(txt_root_snap),
                                      progress_callback=_finger_progress_cb)
                else:
                    cadastrar_cliente(store, creds, dados_ocr=ocr_snapshot)
            except Exception as exc:
                root.after(0, lambda e=exc: _handle_worker_exception(start_button, e))
            else:
                root.after(0, lambda: _finish_worker_success(
                    start_button,
                    f"Processo de {current_action} finalizado para {store}."))

        threading.Thread(target=worker, daemon=True).start()

    def start_vitta_process() -> None:
        action       = vitta_action_var.get()
        empresa      = vitta_credentials.get("empresa",  "").strip()
        usuario_vitta = vitta_credentials.get("username", "").strip()
        senha_vitta  = vitta_credentials.get("password", "").strip()
        if not (empresa and usuario_vitta and senha_vitta):
            messagebox.showwarning("Aviso", "Preencha as credenciais Vitta no arquivo de configuracao.")
            return
        if contract_pdf_path is None:
            messagebox.showwarning("Aviso", "Selecione a pasta do projeto antes de continuar.")
            return
        if action == "pedidos":
            if txt_root is None:
                messagebox.showwarning("Aviso", "Selecione a pasta do projeto antes de continuar.")
                return
            if not vitta_xml_files:
                messagebox.showwarning("Aviso", "Nenhum .xml localizado em EXECUTIVO/COMPRA/PEDIDOS FABRICAS.")
                return
            comprador_nome = " ".join(comprador_var.get().strip().upper().split())
            if not comprador_nome:
                messagebox.showwarning("Aviso", "Informe o nome do comprador.")
                return
            cliente_nome = " ".join(ocr_result_vars["cliente"].get().strip().split())
            if not cliente_nome:
                messagebox.showwarning("Aviso", "Nome do cliente nao identificado pelo OCR.")
                return
            cred_snap    = dict(vitta_credentials)
            base_snap    = txt_root
            start_button.config(state="disabled")
            os.environ["VITTA_BROWSER_VISIBLE"] = "N" if headless_var.get() else "Y"
            show_loading("Importando Vitta no modo Invisivel..." if headless_var.get() else "Importando pedidos...")

            def pedidos_worker() -> None:
                try:
                    cadastrar_pedidos_vitta(cred_snap, base_snap, comprador_nome, cliente_nome)
                except Exception as exc:
                    root.after(0, lambda e=exc: _handle_worker_exception(start_button, e))
                else:
                    root.after(0, lambda: _finish_worker_success(
                        start_button, "Pedidos Vitta processados com sucesso."))

            threading.Thread(target=pedidos_worker, daemon=True).start()
            return

        nome       = ocr_result_vars["cliente"].get().strip()
        cpf        = ocr_result_vars["cpf_cnpj"].get().strip()
        telefone   = ocr_result_vars["telefone"].get().strip()
        endereco   = ocr_result_vars["endereco_entrega"].get().strip()
        numero     = ocr_result_vars["numero"].get().strip()
        complemento = ocr_result_vars["complemento"].get().strip()
        cep        = ocr_result_vars["cep"].get().strip()
        bairro     = ocr_result_vars["bairro"].get().strip()
        cidade     = ocr_result_vars["cidade"].get().strip()
        estado     = ocr_result_vars["estado"].get().strip()
        contato    = str(contacts_config.get("pedidos_email", "")).strip()
        celular    = ""
        email      = str(contacts_config.get("fiscal_email", "")).strip()

        for field, label in [(nome, "nome do cliente"), (cpf, "CPF"),
                              (telefone or celular, "telefone"), (email, "e-mail fiscal"),
                              (cep, "CEP"), (endereco, "endereco")]:
            if not field:
                messagebox.showwarning("Aviso", f"Informe o {label} para o cadastro Vitta.")
                return

        cred_snap    = dict(vitta_credentials)
        dados_cliente = {
            "nome": nome, "cpf": cpf, "contato": contato, "telefone": telefone,
            "celular": celular, "email": email, "cep": cep, "numero": numero,
            "complemento": complemento, "endereco": endereco, "bairro": bairro,
            "cidade": cidade, "estado": estado,
        }
        start_button.config(state="disabled")
        os.environ["VITTA_BROWSER_VISIBLE"] = "N" if headless_var.get() else "Y"
        show_loading("Cadastro no modo Invisivel..." if headless_var.get() else "Processando cadastro...")

        def worker() -> None:
            try:
                cadastrar_cliente_vitta(cred_snap, dados_cliente)
            except Exception as exc:
                root.after(0, lambda e=exc: _handle_worker_exception(start_button, e))
            else:
                root.after(0, lambda: _finish_worker_success(
                    start_button, "Cadastro de cliente realizado no portal Vitta."))

        threading.Thread(target=worker, daemon=True).start()

    def _maybe_show_pdf_email_dialog() -> None:
        """Exibe dialog de envio de PDFs se houver pedidos pendentes com e-mail."""
        if not pdf_orders or pdf_root is None:
            return
        # Atualizar status com base no registro atual (pode ter enviado em outra sessão)
        _config_snap = {"fornecedores_email": dict(fornecedores_email_config)}
        updated = scan_pdf_orders(pdf_root, _config_snap)
        # Substituir pdf_orders pelo estado atualizado mantendo checked original
        checked_ids = {o["id"] for o in pdf_orders if o.get("checked")}
        for o in updated:
            o["checked"] = o["id"] in checked_ids and o["status"] == "pendente"
        pendentes_com_email = [o for o in updated if o["status"] == "pendente" and o.get("can_send")]
        if not pendentes_com_email:
            return
        _show_pdf_email_dialog(updated)

    def _show_pdf_email_dialog(orders: List[dict]) -> None:
        """Dialog para selecionar e enviar pedidos PDF aos fornecedores."""
        dialog = tk.Toplevel(root)
        dialog.title("Enviar Pedidos PDF")
        dialog.configure(bg=BG_CARD)
        dialog.transient(root)
        dialog.resizable(False, False)
        dialog.grab_set()

        pendentes = [o for o in orders if o["status"] == "pendente" and o.get("can_send")]
        sem_email = [o for o in orders if o["status"] == "sem_email"]
        enviados  = [o for o in orders if o["status"] == "enviado"]

        # Dimensões baseadas na quantidade de itens
        dialog_h = min(420 + len(orders) * 4, 560)
        _center_on_root(dialog, 480, dialog_h)

        pf = ttk.Frame(dialog, padding=(18, 14), style="Card.TFrame")
        pf.pack(expand=True, fill="both")
        pf.columnconfigure(0, weight=1)

        # Título
        tk.Label(pf, text="Enviar Pedidos PDF aos Fornecedores",
                 bg=BG_CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))

        n_pend = len(pendentes)
        n_sem  = len(sem_email)
        resumo = f"{n_pend} pedido(s) pronto(s) para enviar"
        if n_sem:
            resumo += f"  |  {n_sem} sem e-mail cadastrado"
        tk.Label(pf, text=resumo, bg=BG_CARD, fg=TEXT_DIM, font=("Segoe UI", 8)).grid(
            row=1, column=0, sticky="w", pady=(0, 10))

        # Remetente
        tk.Label(pf, text="REMETENTE", bg=BG_CARD, fg=TEXT_LABEL,
                 font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=(0, 3))

        remetente_var_dlg = tk.StringVar()
        user_list = list(usuarios_email.keys())
        if user_list:
            remetente_var_dlg.set(user_list[0])
        remetente_combo_dlg = ttk.Combobox(
            pf, values=user_list, textvariable=remetente_var_dlg,
            state="readonly" if user_list else "normal", font=("Segoe UI", 9))
        remetente_combo_dlg.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        # Treeview de PDFs
        tk.Label(pf, text="PEDIDOS ENCONTRADOS", bg=BG_CARD, fg=TEXT_LABEL,
                 font=("Segoe UI", 8)).grid(row=4, column=0, sticky="w", pady=(0, 3))

        tree_wrap = tk.Frame(pf, bg=BG_CARD)
        tree_wrap.grid(row=5, column=0, sticky="nsew", pady=(0, 4))
        tree_wrap.columnconfigure(0, weight=1)
        pf.rowconfigure(5, weight=1)

        cols = ("selec", "pedido", "status")
        dlg_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=6)
        dlg_tree.heading("selec",  text="")
        dlg_tree.heading("pedido", text="PEDIDO")
        dlg_tree.heading("status", text="STATUS")
        dlg_tree.column("selec",  width=30,  stretch=False, anchor="center")
        dlg_tree.column("pedido", width=240, stretch=True)
        dlg_tree.column("status", width=120, stretch=False, anchor="center")

        dlg_tree.tag_configure("enviado",  foreground=SUCCESS)
        dlg_tree.tag_configure("sem_email", foreground=WARNING)
        dlg_tree.tag_configure("pendente",  foreground=TEXT)

        dlg_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=dlg_tree.yview)
        dlg_tree.configure(yscrollcommand=dlg_scroll.set)
        dlg_tree.grid(row=0, column=0, sticky="nsew")
        dlg_scroll.grid(row=0, column=1, sticky="ns")

        # Mapa de iid → order para controle de checkbox
        iid_to_order: dict = {}

        def _status_label(o: dict) -> str:
            return {"pendente": "PENDENTE", "enviado": "ENVIADO", "sem_email": "SEM E-MAIL"}.get(o["status"], o["status"])

        def _sel_icon(o: dict) -> str:
            if o["status"] not in ("pendente",):
                return " "
            return "[x]" if o.get("checked") else "[ ]"

        def _populate_tree() -> None:
            dlg_tree.delete(*dlg_tree.get_children())
            iid_to_order.clear()
            for o in orders:
                tag = o["status"]
                iid = dlg_tree.insert("", "end",
                    values=(_sel_icon(o), f"PEDIDO {o['supplier']}", _status_label(o)),
                    tags=(tag,))
                iid_to_order[iid] = o

        _populate_tree()

        def _toggle_check(event: object) -> None:
            region = dlg_tree.identify_region(event.x, event.y)  # type: ignore[attr-defined]
            if region not in ("cell", "tree"):
                return
            iid = dlg_tree.identify_row(event.y)  # type: ignore[attr-defined]
            if not iid:
                return
            o = iid_to_order.get(iid)
            if o is None or o["status"] != "pendente" or not o.get("can_send"):
                return
            o["checked"] = not o.get("checked", False)
            dlg_tree.set(iid, "selec", _sel_icon(o))

        dlg_tree.bind("<Button-1>", _toggle_check)

        # Botões marcar/desmarcar
        btn_row = ttk.Frame(pf, style="Card.TFrame")
        btn_row.grid(row=6, column=0, sticky="ew", pady=(2, 8))

        def _mark_all() -> None:
            for o in orders:
                if o["status"] == "pendente" and o.get("can_send"):
                    o["checked"] = True
            _populate_tree()

        def _unmark_all() -> None:
            for o in orders:
                o["checked"] = False
            _populate_tree()

        ttk.Button(btn_row, text="Marcar todos",   style="Ghost.TButton",
                   command=_mark_all).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Desmarcar todos", style="Ghost.TButton",
                   command=_unmark_all).pack(side="left")

        # Barra de progresso e status de envio
        progress_var = tk.StringVar(value="")
        tk.Label(pf, textvariable=progress_var, bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).grid(row=7, column=0, sticky="w", pady=(0, 6))

        # Botões principais
        action_row = ttk.Frame(pf, style="Card.TFrame")
        action_row.grid(row=8, column=0, sticky="ew")
        action_row.columnconfigure(0, weight=1)

        send_btn   = ttk.Button(action_row, text="Enviar marcados", style="Action.TButton")
        cancel_btn = ttk.Button(action_row, text="Cancelar",         style="Ghost.TButton",
                                command=dialog.destroy)
        send_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        cancel_btn.grid(row=0, column=1)

        def _do_send() -> None:
            remetente = remetente_var_dlg.get().strip()
            if not remetente:
                messagebox.showwarning("Aviso", "Selecione o remetente.", parent=dialog)
                return
            senha = usuarios_email.get(remetente, "")
            if not senha:
                messagebox.showerror(
                    "Sem credenciais",
                    f"Usuário '{remetente}' não encontrado em usuarios_email no lojas.config.\n"
                    "Peça ao administrador para adicionar as credenciais.",
                    parent=dialog,
                )
                return
            selecionados = [o for o in orders if o.get("checked") and o["status"] == "pendente" and o.get("can_send")]
            if not selecionados:
                messagebox.showinfo("Aviso", "Nenhum pedido marcado para envio.", parent=dialog)
                return

            send_btn.config(state="disabled")
            cancel_btn.config(state="disabled")
            loja_nome = credentials.get(selected_store.get(), {}).get("loja_email", selected_store.get())
            client_code = extract_client_code(pdf_root) if pdf_root else ""
            ocr_snap = {key: ocr_result_vars[key].get().strip() for key in OCR_FIELD_KEYS}
            smtp_snap = dict(email_smtp_config)
            emp_snap  = dict(empresa_info)
            root_snap = pdf_root

            total = len(selecionados)
            sent  = [0]

            def _email_worker() -> None:
                for o in selecionados:
                    try:
                        subj = build_email_subject(client_code, ocr_snap.get("cliente", ""), ocr_snap.get("numero_contrato", ""))
                        body = build_email_body(o["supplier"], ocr_snap, client_code, emp_snap, loja_nome)
                        send_pdf_email(smtp_snap, remetente, senha, o["emails_cc"], subj, body, o["path"])
                        mark_email_sent(o["path"], root_snap, remetente, o["supplier"])
                        o["status"] = "enviado"
                        o["checked"] = False
                        sent[0] += 1
                        root.after(0, lambda s=sent[0], t=total:
                            progress_var.set(f"Enviando... {s}/{t}"))
                        root.after(0, _populate_tree)
                    except Exception as exc:
                        root.after(0, lambda e=exc:
                            messagebox.showerror("Erro ao enviar", str(e), parent=dialog))

                root.after(0, lambda: _on_worker_done(sent[0], total))

            def _on_worker_done(n_sent: int, n_total: int) -> None:
                _populate_tree()
                progress_var.set("")
                send_btn.config(state="normal")
                cancel_btn.config(state="normal")
                if n_sent == n_total:
                    messagebox.showinfo("Sucesso", f"{n_sent} e-mail(s) enviado(s) com sucesso.", parent=dialog)
                    dialog.destroy()
                else:
                    messagebox.showwarning(
                        "Parcial",
                        f"{n_sent} de {n_total} e-mail(s) enviado(s). Verifique os erros acima.",
                        parent=dialog,
                    )

            threading.Thread(target=_email_worker, daemon=True).start()

        send_btn.config(command=_do_send)

        try:
            dialog.focus_force()
        except tk.TclError:
            pass

    def handle_start_click() -> None:
        if fabricante_var.get().lower() == "finger":
            start_finger_process()
        else:
            start_vitta_process()

    def update_fabricante_display(*_args: object) -> None:
        is_finger = fabricante_var.get().lower() == "finger"
        if is_finger:
            vitta_section.grid_remove()
            finger_section.grid()
            start_button.config(text="Iniciar processo")
        else:
            finger_section.grid_remove()
            vitta_section.grid()
            start_button.config(text="Iniciar processo")
        loja_combo.config(state="readonly" if is_finger else "disabled")
        update_project_list()

    # ── Bindings ───────────────────────────────────────────────────────────────
    for widget in (drop_area, drop_inner):
        widget.bind("<Button-1>", lambda _event: choose_folder())
    drop_hint_label.bind("<Button-1>", lambda _event: choose_folder())

    if TkinterDnD and DND_FILES:
        drop_area.drop_target_register(DND_FILES)
        drop_area.dnd_bind("<<Drop>>", handle_drop)
    else:
        drop_hint_label.config(text="Clique para selecionar a pasta do projeto")

    start_button.config(command=handle_start_click)
    send_pdf_button.config(command=_maybe_show_pdf_email_dialog)
    log_toggle_btn.config(command=_toggle_logs)
    log_clear_btn.config(command=_clear_logs)
    reload_button.config(command=reload_config)
    open_config_btn.config(command=handle_open_config)
    fabricante_var.trace_add("write", lambda *_: update_fabricante_display())
    selected_store.trace_add("write", lambda *_: update_finger_display())
    loja_combo.bind("<<ComboboxSelected>>", lambda _event: update_finger_display())

    update_finger_display()
    update_project_list()
    update_fabricante_display()

    root.mainloop()


if __name__ == "__main__":
    run_ui()

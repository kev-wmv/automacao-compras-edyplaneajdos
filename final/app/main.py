"""Entry point da aplicação Flet — Encomendas Edy v6.0."""
from __future__ import annotations

import threading
import flet as ft

from .theme import BG, BORDER, THEME, DARK_THEME, C_SURFACE, ACCENT, ACCENT_SOFT, TEXT, TEXT_DIM, TEXT_SEC
from .state import AppController
from .components.sidebar import build_sidebar
from .components.folder_card import build_folder_card
from .components.project_card import build_project_card
from .components.client_card import build_client_card
from .components.log_panel import build_log_panel
from .components.email_dialog import show_email_dialog
from .components.loading import setup_loading


def _check_update_bg(page: ft.Page) -> None:
    """
    Roda em thread daemon. Verifica se há atualização disponível no GitHub.
    Se houver, agenda a exibição do diálogo na thread de UI.
    Qualquer exceção é silenciada — falha no update nunca deve travar o app.
    """
    try:
        from .updater import check_for_update
        result = check_for_update()
        if result is None:
            return
        latest_version, download_url = result
        # Chama diretamente — Flet sincroniza threads internamente
        _show_update_prompt(page, latest_version, download_url)
    except Exception:
        pass


def _show_update_prompt(page: ft.Page, latest_version: str, download_url: str) -> None:
    """Exibe diálogo de atualização com barra de progresso."""
    from .updater import get_current_version, download_update, apply_update

    progress_bar = ft.ProgressBar(
        color=ACCENT,
        bgcolor=BORDER,
        value=0,
        visible=False,
    )
    progress_text = ft.Text("", size=11, color=TEXT_DIM)

    update_btn = ft.ElevatedButton(
        "Atualizar agora",
        bgcolor=ACCENT,
        color=ft.colors.WHITE,
        height=38,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
    )
    later_btn = ft.OutlinedButton(
        "Mais tarde",
        height=38,
        style=ft.ButtonStyle(
            color=TEXT_DIM,
            shape=ft.RoundedRectangleBorder(radius=8),
            side=ft.BorderSide(1, BORDER),
        ),
    )

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Atualização disponível", weight=ft.FontWeight.W_600),
        content=ft.Container(
            width=360,
            content=ft.Column([
                ft.Text(
                    f"Uma nova versão está disponível: v{latest_version}\n"
                    f"Versão atual: v{get_current_version()}",
                    size=13,
                    color=TEXT,
                ),
                progress_text,
                progress_bar,
                ft.Row([update_btn, later_btn], spacing=10),
            ], spacing=12, tight=True),
            padding=ft.padding.only(top=4),
        ),
    )

    def _close(_=None) -> None:
        dlg.open = False
        try:
            page.update()
        except Exception:
            pass

    later_btn.on_click = _close

    def _do_update(_=None) -> None:
        update_btn.disabled = True
        later_btn.disabled = True
        progress_bar.visible = True
        progress_text.value = "Preparando download..."
        try:
            page.update()
        except Exception:
            pass

        def _download_thread() -> None:
            def _progress(done: int, total: int) -> None:
                progress_bar.value = done / total
                progress_text.value = f"Baixando... {int(done / total * 100)}%"
                try:
                    page.update()
                except Exception:
                    pass

            new_exe = download_update(download_url, _progress)

            if new_exe is None:
                def _fail() -> None:
                    progress_text.value = "Falha no download. Tente mais tarde."
                    update_btn.disabled = False
                    later_btn.disabled = False
                    progress_bar.visible = False
                    try:
                        page.update()
                    except Exception:
                        pass
                _fail()
                return

            progress_text.value = "Concluído. Aplicando atualização..."
            try:
                page.update()
            except Exception:
                pass

            apply_update(new_exe)  # lança o .bat e chama sys.exit(0)

        threading.Thread(target=_download_thread, daemon=True).start()

    update_btn.on_click = _do_update

    # Compatível com Flet 0.21+
    try:
        page.open(dlg)
    except AttributeError:
        page.dialog = dlg
        dlg.open = True
    page.update()


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

    # ── Verificação de atualização (em background, não bloqueia o startup) ────
    threading.Thread(target=_check_update_bg, args=(page,), daemon=True).start()

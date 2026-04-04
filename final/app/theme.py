"""Design system â€” paleta editorial, light-first com suporte completo a dark."""
import flet as ft

# â”€â”€ Paleta light (usada por constantes legadas e como referÃªncia) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BG           = "#f2f4f3"
BG_SIDEBAR   = "#ffffff"
BG_CARD      = "#ffffff"
BG_ENTRY     = "#f5f7f6"
BG_DROP      = "#f0f8f3"
ACCENT       = "#1b6b3a"
ACCENT_HOV   = "#155a30"
ACCENT_SOFT  = "#e4f0e8"
ACCENT_MUTED = "#a3c9b0"
BORDER       = "#dce3de"
BORDER_FOCUS = "#b8cfbe"
TEXT         = "#1a2620"
TEXT_SEC     = "#4a5e52"
TEXT_DIM     = "#8a9b91"
TEXT_LABEL   = "#5a6e63"
SUCCESS      = "#1e8a48"
WARNING      = "#b07d0a"
ERROR        = "#c03030"
LOG_BG       = "#1a2620"
LOG_TEXT     = "#a8c4b0"

# â”€â”€ DimensÃµes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SIDE_W = 264

# â”€â”€ Sombras â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CARD_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=12,
    color="#0000000d",
    offset=ft.Offset(0, 2),
)

SIDEBAR_SHADOW = ft.BoxShadow(
    spread_radius=0,
    blur_radius=20,
    color="#00000018",
    offset=ft.Offset(2, 0),
)

# â”€â”€ Tema claro â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
THEME = ft.Theme(
    color_scheme_seed=ACCENT,
    color_scheme=ft.ColorScheme(
        primary=ACCENT,
        on_primary="#ffffff",
        surface=BG,
        on_surface=TEXT,
        on_surface_variant=TEXT_LABEL,
        surface_container=BG_CARD,
        outline=BORDER,
    ),
)

# â”€â”€ Tema escuro â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# primary mais claro para que on_primary escuro tenha contraste suficiente (WCAG AA)
DARK_THEME = ft.Theme(
    color_scheme_seed=ACCENT,
    color_scheme=ft.ColorScheme(
        primary="#4caf75",
        on_primary="#003a1a",
        surface="#0d1210",
        on_surface="#e8ede9",
        on_surface_variant="#8fa898",
        surface_container="#161f1a",
        outline="#2a3a2e",
    ),
)

FONT_FAMILY = "Segoe UI"

# ── Tokens semânticos — strings resolvidas pelo tema ativo ────────────────────
# Evita usar ft.Colors.X (enum incompleto em algumas versões do Flet).
# Flet resolve esses camelCase strings direto do ColorScheme do tema.
C_SURFACE            = "surface"
C_SURFACE_VARIANT    = "surfaceVariant"
C_SURFACE_CONTAINER  = "surfaceContainer"
C_ON_SURFACE         = "onSurface"
C_ON_SURFACE_VARIANT = "onSurfaceVariant"
C_PRIMARY            = "primary"
C_ON_PRIMARY         = "onPrimary"
C_OUTLINE            = "outline"
C_OUTLINE_VARIANT    = "outlineVariant"



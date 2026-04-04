import logging
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .cadastro_clientes_finger import OCR_FIELD_KEYS, OCR_FIELDS
except ImportError:  # pragma: no cover
    from cadastro_clientes_finger import OCR_FIELD_KEYS, OCR_FIELDS

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


OCR_FIELDS_ORDER: Tuple[str, ...] = tuple(OCR_FIELD_KEYS)


# Funções legadas de verificação de caminho do Tesseract/Poppler foram removidas para ganho de performance e limpeza de código.


def _require_pdfplumber() -> None:
    if pdfplumber is None:
        raise ImportError(
            "Dependencia 'pdfplumber' ausente. Instale com 'pip install pdfplumber'."
        )


def _normalize_path_sequence(raw: str) -> Iterable[str]:
    cleaned = raw.strip()
    if not cleaned:
        return ()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        cleaned = cleaned[1:-1]
    parts = re.split(r"[{}\s]+", cleaned)
    return tuple(filter(None, parts))


def _split_endereco_parts(value: str) -> tuple[str, str, str]:
    text = value.strip()
    complemento = ""

    if "-" in text:
        before_dash, after_dash = text.split("-", 1)
        complemento = " ".join(after_dash.strip().upper().split())
        text = before_dash.strip()

    if "," in text:
        before_comma, after_comma = text.split(",", 1)
        numero_part = after_comma.split(",", 1)[0]
        logradouro = " ".join(before_comma.split())
        numero_raw = numero_part.strip().split("-", 1)[0].strip()
    else:
        logradouro = " ".join(text.split())
        numero_raw = ""

    numero = "".join(ch for ch in numero_raw if ch.isdigit())

    return logradouro, numero, complemento


def find_latest_contrato_pdf(base_directory: Path, search_pattern: str) -> Path:
    pattern_normalized = search_pattern.lower()
    latest_path: Optional[Path] = None
    latest_mtime: float = -1.0

    for pdf_path in base_directory.rglob("*.pdf"):
        try:
            stem = pdf_path.stem.lower()
        except Exception:
            continue
        if pattern_normalized not in stem:
            continue
        try:
            mtime = pdf_path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_path = pdf_path

    if latest_path is None:
        logger.error(f"Nenhum PDF contendo '{search_pattern}' encontrado em {base_directory}.")
        raise FileNotFoundError(
            f"Nenhum PDF contendo '{search_pattern}' encontrado em {base_directory}."
        )

    logger.info(f"PDF encontrado: {latest_path.name}")
    return latest_path


def _parse_box(raw_box: Any) -> tuple[int, float, float, float, float] | None:
    """Analisa a caixa de coordenadas e retorna (page_index, x1, y1, x2, y2) em pixels."""
    if raw_box is None:
        return None

    page_index = 0

    if isinstance(raw_box, dict):
        if "page" in raw_box:
            try:
                page_index = int(float(raw_box.get("page", 0)))
            except (TypeError, ValueError):
                page_index = 0
        if {"x", "y", "width", "height"} <= raw_box.keys():
            try:
                x = float(raw_box["x"])
                y = float(raw_box["y"])
                width = float(raw_box["width"])
                height = float(raw_box["height"])
            except (TypeError, ValueError):
                return None
            if width <= 0 or height <= 0:
                return None
            return page_index, x, y, x + width, y + height
        if {"x1", "y1", "x2", "y2"} <= raw_box.keys():
            try:
                x1 = float(raw_box["x1"])
                y1 = float(raw_box["y1"])
                x2 = float(raw_box["x2"])
                y2 = float(raw_box["y2"])
            except (TypeError, ValueError):
                return None
            return page_index, x1, y1, x2, y2
        return None

    if isinstance(raw_box, (list, tuple)):
        values = list(raw_box)
        if len(values) == 5:
            try:
                page_index = int(float(values[0]))
            except (TypeError, ValueError):
                page_index = 0
            values = values[1:]
        if len(values) < 4:
            return None
        try:
            x1, y1, x2, y2 = (float(values[i]) for i in range(4))
        except (TypeError, ValueError):
            return None
        return page_index, x1, y1, x2, y2

    return None


def _extract_field_text_plumber(
    pdf: Any,
    raw_box: Any,
) -> str:
    """Extrai texto de uma região do PDF usando pdfplumber.

    As coordenadas em ``raw_box`` são usadas diretamente como pontos PDF
    no sistema de coordenadas nativo do pdfplumber (top-down, origem no canto superior esquerdo).
    """
    parsed = _parse_box(raw_box)
    if not parsed:
        return ""
    page_index, x0, top, x1, bottom = parsed

    if x1 <= x0 or bottom <= top:
        return ""

    pages = pdf.pages
    if page_index < 0 or page_index >= len(pages):
        return ""

    cropped = pages[page_index].crop((x0, top, x1, bottom))
    text = cropped.extract_text() or ""
    text = " ".join(text.split()).upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


def extract_contrato_data(base_directory: Path, ocr_config: Mapping[str, Any]) -> Tuple[Path, Dict[str, str]]:
    logger.info("Iniciando extração de dados do contrato pelo pdfplumber...")
    if not base_directory.is_dir():
        logger.error(f"{base_directory} nao e uma pasta valida.")
        raise NotADirectoryError(f"{base_directory} nao e uma pasta valida.")

    _require_pdfplumber()

    contrato_conf = ocr_config.get("contrato", {}) if isinstance(ocr_config, Mapping) else {}
    search_pattern = contrato_conf.get("search_pattern") if isinstance(contrato_conf, Mapping) else None
    if not isinstance(search_pattern, str) or not search_pattern.strip():
        search_pattern = "CONTRATO"

    pdf_path = find_latest_contrato_pdf(base_directory, search_pattern)

    fields_conf = contrato_conf.get("fields", {}) if isinstance(contrato_conf, Mapping) else {}

    results: Dict[str, str] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        logger.debug(f"Processando {len(OCR_FIELDS)} campos configurados.")
        for field in OCR_FIELDS:
            config_key = field["config_key"]
            key = field["key"]
            raw_box = fields_conf.get(config_key) if isinstance(fields_conf, Mapping) else None
            value = _extract_field_text_plumber(pdf, raw_box).strip()
            value = value.encode("ascii", "ignore").decode("ascii")
            value = " ".join(value.split())
            if key == "cliente":
                value = re.sub(r"[\d-]+", " ", value)
                value = " ".join(value.split())
            elif key == "telefone":
                value = value.split("/")[0]
                value = "".join(ch for ch in value if ch.isdigit())
            results[key] = value

    logger.debug("Processando lógicas de pós-extração (endereços e formatações).")
    endereco_base = results.get("endereco_entrega", "")
    if endereco_base:
        logradouro, numero_calc, complemento_calc = _split_endereco_parts(endereco_base)
        results["endereco_entrega"] = logradouro
    else:
        _, numero_calc, complemento_calc = _split_endereco_parts("")

    numero_value = results.get("numero", "")
    if numero_value == endereco_base:
        numero_value = numero_calc
    else:
        numero_value = numero_value.split("-", 1)[0]
        numero_value = "".join(ch for ch in numero_value if ch.isdigit())
        
    if not numero_value:
        numero_value = numero_calc
    results["numero"] = numero_value

    complemento_value = results.get("complemento", "").strip()
    if complemento_value == endereco_base:
        complemento_value = complemento_calc
    elif not complemento_value:
        complemento_value = complemento_calc
        
    complemento_value = " ".join(complemento_value.upper().split())
    results["complemento"] = complemento_value

    logger.info("Extração finalizada com sucesso.")
    return pdf_path, results


__all__ = [
    "OCR_FIELDS_ORDER",
    "extract_contrato_data",
    "find_latest_contrato_pdf",
    "_normalize_path_sequence",
]

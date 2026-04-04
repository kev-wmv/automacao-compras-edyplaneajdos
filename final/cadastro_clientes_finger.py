import json
import os
import re
import subprocess
import sys
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

BLOCKING_MESSAGES = [
    "CPF j\u00e1 cadastrado na Empresa!",
    "CPF Inv\u00e1lido!",
]
CONFIG_FILENAME = "lojas.config"
STORES = [
    "Tatuap\u00e9",
    "Rep\u00fablica",
    "Santo Andr\u00e9",
    "Campanella",
    "Lar center",
    "Aricanduva",
    "Pacaembu",
]
OCR_FIELDS: List[Dict[str, Any]] = [
    {"key": "cliente", "label": "NOME CLIENTE", "config_key": "NOME CLIENTE", "required": True},
    {"key": "cpf_cnpj", "label": "CPF/CNPJ", "config_key": "CPF/CNPJ", "required": True},
    {"key": "telefone", "label": "TELEFONE", "config_key": "TELEFONE", "required": True},
    {
        "key": "endereco_entrega",
        "label": "ENDERECO DE ENTREGA",
        "config_key": "ENDERECO DE ENTREGA",
        "required": True,
    },
    {"key": "numero", "label": "NUMERO", "config_key": "NUMERO", "required": False},
    {"key": "complemento", "label": "COMPLEMENTO", "config_key": "COMPLEMENTO", "required": False},
    {"key": "bairro", "label": "BAIRRO", "config_key": "BAIRRO", "required": True},
    {"key": "cidade", "label": "CIDADE", "config_key": "CIDADE", "required": True},
    {"key": "estado", "label": "UF", "config_key": "UF", "required": True},
    {"key": "cep", "label": "CEP", "config_key": "CEP", "required": True},
    {"key": "numero_contrato", "label": "NUMERO CONTRATO", "config_key": "NUMERO CONTRATO", "required": False},
]
OCR_FIELD_KEYS: List[str] = [field["key"] for field in OCR_FIELDS]
OCR_FIELD_LABELS: Dict[str, str] = {field["key"]: field["label"] for field in OCR_FIELDS}
OCR_CONFIG_KEY_BY_KEY: Dict[str, str] = {field["key"]: field["config_key"] for field in OCR_FIELDS}
OCR_KEY_BY_CONFIG_KEY: Dict[str, str] = {field["config_key"]: field["key"] for field in OCR_FIELDS}
DEFAULT_CONTRATO_BOXES: Dict[str, List[int]] = {
    "NOME CLIENTE":         [28, 175, 430, 188],
    "CPF/CNPJ":            [28, 201, 200, 213],
    "TELEFONE":            [28, 279, 370, 292],
    "ENDERECO DE ENTREGA": [28, 305, 370, 318],
    "NUMERO":              [28, 305, 370, 318],
    "COMPLEMENTO":         [28, 305, 370, 318],
    "BAIRRO":              [28, 331, 200, 344],
    "CIDADE":             [202, 331, 370, 344],
    "UF":                 [370, 331, 435, 344],
    "CEP":                [432, 331, 560, 344],
    "NUMERO CONTRATO":    [458, 108, 560, 123],
}

LEGACY_FIELD_KEYS: Dict[str, List[str]] = {
    "NOME CLIENTE": ["cliente", "NOME"],
    "CPF/CNPJ": ["cpf_cnpj", "CPF", "CPF/CNPJ"],
    "TELEFONE": ["telefone", "TELEFONE 01", "telefone_01", "TELEFONE1", "TELEFONE 02", "TELEFONE02", "telefone_02"],
    "ENDERECO DE ENTREGA": ["endereco_entrega", "ENDERECO", "ENDEREÇO DE ENTREGA"],
    "NUMERO": ["numero", "NRO", "NUMERO"],
    "COMPLEMENTO": ["complemento", "COMPLEMENTO", "complemento endereco", "complemento end", "comp"],
    "BAIRRO": ["bairro"],
    "CIDADE": ["cidade"],
    "UF": ["estado", "UF"],
    "CEP": ["cep"],
    "NUMERO CONTRATO": ["numero_contrato", "CONTRATO"],
}


def _default_vitta_credentials() -> Dict[str, str]:
    return {"empresa": "", "username": "", "password": ""}


def _default_contacts_block() -> Dict[str, str]:
    return {
        "pedidos_email": "pedidos@exemplo.com.br",
        "fiscal_email": "fiscal@exemplo.com.br",
    }


def _default_settings_block() -> Dict[str, str]:
    return {
        "finger_browser_visible": "Y",
        "vitta_browser_visible": "Y",
    }


def _default_email_smtp_block() -> Dict[str, Any]:
    return {
        "host": "smtp.exemplo.com.br",
        "port": 587,
        "use_tls": True,
        "destino_fixo": "pedidos@exemplo.com.br",
    }


def _default_empresa_info_block() -> Dict[str, str]:
    return {
        "codigo": "000",
        "nome": "EMPRESA EXEMPLO LTDA",
    }


def _default_config_data() -> Dict[str, Any]:
    return {
        "stores": _default_store_block(),
        "ocr": _default_ocr_block(),
        "vitta": _default_vitta_credentials(),
        "email_smtp": _default_email_smtp_block(),
        "usuarios_email": {},
        "empresa_info": _default_empresa_info_block(),
        "fornecedores_email": {},
        "settings": _default_settings_block(),
        "contatos": _default_contacts_block(),
    }




_FINGER_BROWSER_VISIBLE: Optional[bool] = None


def _finger_browser_visible() -> bool:
    import os
    env_val = os.environ.get("FINGER_BROWSER_VISIBLE")
    if env_val:
        return env_val != "N"
    global _FINGER_BROWSER_VISIBLE
    if _FINGER_BROWSER_VISIBLE is None:
        try:
            config_data = ensure_config(include_meta=True)  # type: ignore[arg-type]
        except Exception:
            _FINGER_BROWSER_VISIBLE = True
        else:
            settings = config_data.get("settings", {}) if isinstance(config_data, dict) else {}
            value = str(settings.get("finger_browser_visible", "Y")).strip().upper()
            _FINGER_BROWSER_VISIBLE = value != "N"
    return _FINGER_BROWSER_VISIBLE


def _app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _config_path() -> Path:
    return _app_base_dir() / CONFIG_FILENAME


def _default_store_block() -> Dict[str, Dict[str, str]]:
    return {
        store: {
            "username": "",
            "password": "",
            "loja_email": store,
        }
        for store in STORES
    }


def _to_number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_number(number: float) -> float | int:
    if float(number).is_integer():
        return int(number)
    return number


def _copy_box_list(values: Sequence[Any]) -> List[float | int]:
    coords = list(values)[:4]
    normalized: List[float | int] = []
    for raw in coords:
        number = _to_number(raw)
        if number is None:
            return []
        normalized.append(_normalize_number(number))
    if len(normalized) != 4:
        return []
    return normalized


def _default_box_for(config_key: str) -> List[float | int]:
    base = DEFAULT_CONTRATO_BOXES.get(config_key)
    if base is None:
        return [0, 0, 0, 0]
    normalized = _copy_box_list(base)
    return normalized if normalized else [0, 0, 0, 0]


def _copy_default_boxes() -> Dict[str, List[float | int]]:
    return {key: _default_box_for(key) for key in DEFAULT_CONTRATO_BOXES}


def _normalize_box(raw: Any) -> Optional[List[float | int]]:
    if raw is None:
        return None

    if isinstance(raw, (list, tuple)):
        coords = list(raw)
        if len(coords) == 5:
            coords = coords[1:]
        if len(coords) < 4:
            return None
        normalized: List[float | int] = []
        for value in coords[:4]:
            number = _to_number(value)
            if number is None:
                return None
            normalized.append(_normalize_number(number))
        return normalized

    if isinstance(raw, dict):
        if {"x", "y", "width", "height"} <= raw.keys():
            x = _to_number(raw.get("x"))
            y = _to_number(raw.get("y"))
            width = _to_number(raw.get("width"))
            height = _to_number(raw.get("height"))
            if None in (x, y, width, height) or width <= 0 or height <= 0:
                return None
            coords = (x, y, x + width, y + height)
        elif {"x1", "y1", "x2", "y2"} <= raw.keys():
            x1 = _to_number(raw.get("x1"))
            y1 = _to_number(raw.get("y1"))
            x2 = _to_number(raw.get("x2"))
            y2 = _to_number(raw.get("y2"))
            if None in (x1, y1, x2, y2):
                return None
            coords = (x1, y1, x2, y2)
        else:
            return None
        return [_normalize_number(value) for value in coords]

    return None


def _only_digits(value: Optional[str]) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _get_required_text(dados: Mapping[str, str], key: str) -> str:
    label = OCR_FIELD_LABELS.get(key, key)
    raw = dados.get(key)
    text = str(raw).strip() if raw is not None else ""
    if not text:
        raise ValueError(
            f"Campo '{label}' n\u00e3o foi preenchido pelo OCR. Execute a leitura do contrato novamente."
        )
    return text


def _get_required_digits(dados: Mapping[str, str], key: str, min_length: int) -> str:
    label = OCR_FIELD_LABELS.get(key, key)
    digits = _only_digits(dados.get(key))
    if len(digits) < min_length:
        raise ValueError(
            f"Campo '{label}' precisa conter ao menos {min_length} d\u00edgitos ap\u00f3s o OCR."
        )
    return digits


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _clean_nome_cliente(value: str) -> str:
    cleaned = re.sub(r"[\d-]+", " ", value)
    return " ".join(cleaned.split())


def _split_endereco(value: str) -> tuple[str, str, str]:
    text = value.strip()
    complemento = ""

    if "-" in text:
        before_dash, after_dash = text.split("-", 1)
        complemento = " ".join(after_dash.strip().upper().split())
        text = before_dash.strip()

    if "," in text:
        before_comma, after_comma = text.split(",", 1)
        logradouro = " ".join(before_comma.split())
        numero_raw = after_comma.strip().split("-", 1)[0].strip()
    else:
        logradouro = " ".join(text.split())
        numero_raw = ""

    numero = _only_digits(numero_raw)

    return logradouro, numero, complemento


STATE_ABBR_BY_NAME = {
    "ACRE": "AC",
    "ALAGOAS": "AL",
    "AMAPA": "AP",
    "AMAZONAS": "AM",
    "BAHIA": "BA",
    "CEARA": "CE",
    "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES",
    "GOIAS": "GO",
    "MARANHAO": "MA",
    "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS",
    "MINAS GERAIS": "MG",
    "PARA": "PA",
    "PARAIBA": "PB",
    "PARANA": "PR",
    "PERNAMBUCO": "PE",
    "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO",
    "RORAIMA": "RR",
    "SANTA CATARINA": "SC",
    "SAO PAULO": "SP",
    "SERGIPE": "SE",
    "TOCANTINS": "TO",
}

STATE_NAME_BY_ABBR = {abbr: name for name, abbr in STATE_ABBR_BY_NAME.items()}


def _normalize_uf(cidade: str, estado: str) -> str:
    for candidate in (estado, cidade):
        if not candidate:
            continue
        normalized = _strip_accents(candidate).upper().strip()
        if not normalized:
            continue
        if len(normalized) == 2 and normalized.isalpha():
            return normalized
        if normalized in STATE_ABBR_BY_NAME:
            return STATE_ABBR_BY_NAME[normalized]
    return ""


def _default_ocr_block() -> Dict[str, Any]:
    return {
        "contrato": {
            "search_pattern": "CONTRATO",
            "fields": _copy_default_boxes(),
        }
    }

def _clone_value(value: Any) -> Any:
    return deepcopy(value)


def _deep_merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = {str(key): _clone_value(value) for key, value in base.items()}
    for key, value in override.items():
        key_str = str(key)
        if isinstance(result.get(key_str), dict) and isinstance(value, Mapping):
            result[key_str] = _deep_merge_dicts(result[key_str], value)
        else:
            result[key_str] = _clone_value(value)
    return result


def _load_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Erro ao ler {label}: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Nao foi possivel ler {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Formato invalido em {label}.")
    return data


def _bootstrap_user_config(template_data: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(template_data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


def _normalize_stores_section(data: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    stores_source = data.get("stores")
    if not isinstance(stores_source, Mapping):
        stores_source = {}
        for store in STORES:
            legacy_creds = data.get(store)
            if isinstance(legacy_creds, Mapping):
                stores_source[store] = dict(legacy_creds)

    stores_section: Dict[str, Dict[str, str]] = {}
    for store in STORES:
        creds = stores_source.get(store)
        if not isinstance(creds, Mapping):
            stores_section[store] = {
                "username": "",
                "password": "",
                "loja_email": store,
            }
            continue
        username = creds.get("username", "")
        password = creds.get("password", "")
        loja_email = creds.get("loja_email", store)
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError(f"Credenciais invalidas para {store} em {CONFIG_FILENAME}.")
        if not isinstance(loja_email, str):
            loja_email = store
        stores_section[store] = {
            "username": username,
            "password": password,
            "loja_email": loja_email,
        }
    return stores_section


def _normalize_ocr_section(data: Mapping[str, Any]) -> Dict[str, Any]:
    raw_ocr = data.get("ocr")
    ocr_section = dict(raw_ocr) if isinstance(raw_ocr, Mapping) else _default_ocr_block()

    raw_contrato = ocr_section.get("contrato")
    contrato_section = dict(raw_contrato) if isinstance(raw_contrato, Mapping) else {}
    search_pattern = contrato_section.get("search_pattern")
    if not isinstance(search_pattern, str) or not search_pattern.strip():
        search_pattern = "CONTRATO"
    contrato_section["search_pattern"] = search_pattern

    raw_fields = contrato_section.get("fields")
    if not isinstance(raw_fields, Mapping):
        raw_fields = {}

    normalized_fields: Dict[str, List[float | int]] = {}
    legacy_ignore = set()
    for key_list in LEGACY_FIELD_KEYS.values():
        for legacy_key in key_list:
            legacy_ignore.add(legacy_key)
            legacy_ignore.add(legacy_key.lower())
    for extra in {"complemento", "complemento endereco", "complemento end"}:
        legacy_ignore.add(extra)
        legacy_ignore.add(extra.lower())

    for field in OCR_FIELDS:
        config_key = field["config_key"]
        existing = None
        if config_key in raw_fields:
            existing = raw_fields[config_key]
        else:
            for legacy_key in LEGACY_FIELD_KEYS.get(config_key, []):
                if legacy_key in raw_fields:
                    existing = raw_fields[legacy_key]
                    break
                legacy_lower = legacy_key.lower()
                for candidate_key in raw_fields.keys():
                    if str(candidate_key).lower() == legacy_lower:
                        existing = raw_fields[candidate_key]
                        break
                if existing is not None:
                    break
        normalized_box = _normalize_box(existing) or _default_box_for(config_key)
        normalized_fields[config_key] = normalized_box

    for key, value in list(raw_fields.items()):
        key_text = str(key)
        if (
            key_text in normalized_fields
            or key_text.lower() in normalized_fields
            or key_text in legacy_ignore
            or key_text.lower() in legacy_ignore
        ):
            continue
        normalized_box = _normalize_box(value)
        if not normalized_box:
            continue
        normalized_fields[key_text] = normalized_box

    contrato_section["fields"] = normalized_fields
    ocr_section["contrato"] = contrato_section
    return ocr_section


def _normalize_vitta_section(data: Mapping[str, Any]) -> Dict[str, str]:
    raw_vitta = data.get("vitta")
    if not isinstance(raw_vitta, Mapping):
        return _default_vitta_credentials()
    vitta_section: Dict[str, str] = {}
    for key in ("empresa", "username", "password"):
        value = raw_vitta.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"Campo '{key}' de Vitta deve ser texto em {CONFIG_FILENAME}.")
        vitta_section[key] = value
    return vitta_section


def _normalize_email_smtp_section(data: Mapping[str, Any]) -> Dict[str, Any]:
    raw_smtp = data.get("email_smtp")
    if not isinstance(raw_smtp, Mapping):
        return _default_email_smtp_block()
    try:
        port = int(raw_smtp.get("port", _default_email_smtp_block()["port"]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Campo 'port' de email_smtp invalido em {CONFIG_FILENAME}.") from exc
    return {
        "host": str(raw_smtp.get("host", _default_email_smtp_block()["host"])),
        "port": port,
        "use_tls": bool(raw_smtp.get("use_tls", _default_email_smtp_block()["use_tls"])),
        "destino_fixo": str(
            raw_smtp.get("destino_fixo", _default_email_smtp_block()["destino_fixo"])
        ),
    }


def _normalize_usuarios_email_section(data: Mapping[str, Any]) -> Dict[str, str]:
    raw_usuarios = data.get("usuarios_email")
    if not isinstance(raw_usuarios, Mapping):
        return {}
    return {str(k): str(v) for k, v in raw_usuarios.items() if isinstance(k, str)}


def _normalize_empresa_info_section(data: Mapping[str, Any]) -> Dict[str, str]:
    raw_empresa = data.get("empresa_info")
    if not isinstance(raw_empresa, Mapping):
        return _default_empresa_info_block()
    return {
        "codigo": str(raw_empresa.get("codigo", _default_empresa_info_block()["codigo"])),
        "nome": str(raw_empresa.get("nome", _default_empresa_info_block()["nome"])),
    }


def _normalize_fornecedores_email_section(data: Mapping[str, Any]) -> Dict[str, List[str]]:
    raw_forn = data.get("fornecedores_email")
    if not isinstance(raw_forn, Mapping):
        return {}
    fornecedores_section: Dict[str, List[str]] = {}
    for key, value in raw_forn.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            normalized_items = [str(item).strip() for item in value]
            if normalized_items and all(item == "" for item in normalized_items):
                fornecedores_section[key] = [""]
            else:
                fornecedores_section[key] = [item for item in normalized_items if item]
        else:
            fornecedores_section[key] = []
    return fornecedores_section


def _normalize_settings_section(data: Mapping[str, Any]) -> Dict[str, Any]:
    raw_settings = data.get("settings")
    defaults = _default_settings_block()
    if not isinstance(raw_settings, Mapping):
        return defaults
    settings_section: Dict[str, Any] = {str(k): _clone_value(v) for k, v in raw_settings.items()}
    for key, default_value in defaults.items():
        raw_value = raw_settings.get(key, default_value)
        settings_section[key] = "N" if str(raw_value).strip().upper() == "N" else "Y"
    return settings_section


def _normalize_contacts_section(data: Mapping[str, Any]) -> Dict[str, Any]:
    raw_contacts = data.get("contatos")
    defaults = _default_contacts_block()
    if not isinstance(raw_contacts, Mapping):
        return defaults
    contatos_section: Dict[str, Any] = {str(k): _clone_value(v) for k, v in raw_contacts.items()}
    for key, default_value in defaults.items():
        raw_value = raw_contacts.get(key, default_value)
        if not isinstance(raw_value, str):
            raise ValueError(f"Campo '{key}' de contatos deve ser texto em {CONFIG_FILENAME}.")
        contatos_section[key] = raw_value.strip()
    return contatos_section


def _validate_and_normalize_config(data: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError(f"Formato invalido em {CONFIG_FILENAME}.")

    normalized_data: Dict[str, Any] = {str(k): _clone_value(v) for k, v in data.items()}
    normalized_data["stores"] = _normalize_stores_section(data)
    normalized_data["ocr"] = _normalize_ocr_section(data)
    normalized_data["vitta"] = _normalize_vitta_section(data)
    normalized_data["email_smtp"] = _normalize_email_smtp_section(data)
    normalized_data["usuarios_email"] = _normalize_usuarios_email_section(data)
    normalized_data["empresa_info"] = _normalize_empresa_info_section(data)
    normalized_data["fornecedores_email"] = _normalize_fornecedores_email_section(data)
    normalized_data["settings"] = _normalize_settings_section(data)
    normalized_data["contatos"] = _normalize_contacts_section(data)
    return normalized_data


def get_contact_settings(config_data: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    source = config_data if isinstance(config_data, Mapping) else ensure_config(include_meta=True)
    contatos = source.get("contatos", {}) if isinstance(source, Mapping) else {}
    defaults = _default_contacts_block()
    resolved = dict(defaults)
    if isinstance(contatos, Mapping):
        for key in defaults:
            value = contatos.get(key)
            if isinstance(value, str) and value.strip():
                resolved[key] = value.strip()
    return resolved


def ensure_config(include_meta: bool = False) -> Dict[str, Any]:
    config_path = _config_path()
    if not config_path.exists():
        _bootstrap_user_config(_default_config_data(), config_path)

    raw_data = _load_json_object(config_path, config_path.name)
    normalized_data = _validate_and_normalize_config(raw_data)
    return normalized_data if include_meta else normalized_data["stores"]





def open_config_file() -> None:
    ensure_config()
    path = _config_path()
    if sys.platform.startswith("win"):
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def cadastrar_cliente(
    loja: str,
    credenciais: Mapping[str, str],
    dados_ocr: Optional[Mapping[str, str]] = None,
) -> None:
    usuario = credenciais.get("username", "").strip()
    senha = credenciais.get("password", "").strip()

    if not usuario or not senha:
        raise ValueError(f"Credenciais de {loja} n\u00e3o preenchidas em {CONFIG_FILENAME}.")

    if dados_ocr is None:
        raise ValueError(
            "Dados do contrato n\u00e3o informados. Execute o OCR antes de cadastrar o cliente."
        )

    nome_cliente = _clean_nome_cliente(_get_required_text(dados_ocr, "cliente"))
    nome_fantasia = nome_cliente

    documento_digits = _get_required_digits(dados_ocr, "cpf_cnpj", min_length=11)
    if len(documento_digits) not in (11, 14):
        raise ValueError("CPF/CNPJ extra\u00eddo do contrato possui quantidade inv\u00e1lida de d\u00edgitos.")
    documento = documento_digits

    telefone_digits = _get_required_digits(dados_ocr, "telefone", min_length=10)[:11]
    telefone1 = telefone_digits
    telefone2 = ""

    endereco_texto = _get_required_text(dados_ocr, "endereco_entrega")
    logradouro, numero_extraido, complemento_extraido = _split_endereco(endereco_texto)
    logradouro = " ".join(logradouro.split())
    cidade = _get_required_text(dados_ocr, "cidade")
    estado_original = _strip_accents(_get_required_text(dados_ocr, "estado"))
    estado = _normalize_uf(cidade, estado_original) or _strip_accents(estado_original).upper().strip()[:2]
    estado_nome = STATE_NAME_BY_ABBR.get(estado, estado_original.upper())
    bairro = _get_required_text(dados_ocr, "bairro")

    numero_campo = _only_digits(str(dados_ocr.get("numero", "")))
    numero_final = numero_campo or numero_extraido or "S/N"

    complemento_campo = str(dados_ocr.get("complemento", "")).strip()
    if complemento_campo:
        complemento = " ".join(complemento_campo.upper().split())
    else:
        complemento = complemento_extraido

    cep_digits = _get_required_digits(dados_ocr, "cep", min_length=8)[:8]
    if len(cep_digits) != 8:
        raise ValueError("CEP extra\u00eddo do contrato precisa possuir 8 d\u00edgitos.")
    cep = cep_digits
    contact_settings = get_contact_settings()
    pedidos_email = contact_settings["pedidos_email"].upper()
    fiscal_email = contact_settings["fiscal_email"].upper()

    browser_visible = _finger_browser_visible()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=not browser_visible)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("http://187.45.123.235:18914/pedidos3/login.asp")
            page.get_by_role("textbox", name="Usu\u00e1rio:").fill(usuario)
            page.get_by_role("textbox", name="Senha:").fill(senha)
            page.get_by_role("link", name="logar no sistema").click()
            try:
                menu = page.get_by_text("Cadastros Clientes Pedidos")
                menu.wait_for(timeout=5000)
                menu.click()
            except Exception:
                context.close()
                browser.close()
                raise RuntimeError("Timeout ao acessar menu Cadastros Clientes Pedidos. Reabra a aplicação e tente novamente.")
            page.get_by_role("link", name="Clientes").click()
            page.get_by_label("Tipo de Cliente :").select_option("F")
            page.get_by_role("textbox", name="Inscri\u00e7\u00e3o Estadual :").click()
            page.get_by_role("textbox", name="Inscri\u00e7\u00e3o Estadual :").fill("ISENTO")
            page.get_by_role("textbox", name="Raz\u00e3o Social/Nome :").click()
            page.get_by_role("textbox", name="Raz\u00e3o Social/Nome :").fill(nome_cliente)
            page.get_by_role("textbox", name="Nome Fantasia :").click()
            page.get_by_role("textbox", name="Nome Fantasia :").fill(nome_fantasia)
            page.get_by_role("textbox", name="CNPJ/CPF :").click()
            page.get_by_role("textbox", name="CNPJ/CPF :").fill(documento)
            page.locator("#Cliente__Telefone_1").click()

            # Checa imediatamente por mensagens bloqueantes sem aguardar timeout longo.
            for mensagem in BLOCKING_MESSAGES:
                # query_selector retorna None imediatamente se o texto não existir
                alerta_handle = page.query_selector(f'text="{mensagem}"')
                if alerta_handle:
                    try:
                        alerta_handle.click()
                    except Exception:
                        pass
                    context.close()
                    browser.close()
                    raise RuntimeError(f"{mensagem} detectado - navegador fechado.")

            page.locator("#Cliente__Telefone_1").click()
            page.locator("#Cliente__Telefone_1").fill(telefone1)
            page.locator("#Cliente__Telefone_2").click()
            page.locator("#Cliente__Telefone_2").fill(telefone1)
            page.locator("#Cliente__E_Mail").click()
            page.locator("#Cliente__E_Mail").fill(pedidos_email)
            page.get_by_role("textbox", name="e-Mail NF-e :").click()
            page.get_by_role("textbox", name="e-Mail NF-e :").fill(fiscal_email)
            page.get_by_role("link", name="Endere\u00e7os").click()
            page.locator("#Cliente__End").click()
            page.locator("#Cliente__End").fill(logradouro)
            page.get_by_role("textbox", name="Pa\u00eds :").click()
            page.get_by_role("textbox", name="Pa\u00eds :").fill("BRASIL")
            page.get_by_role("textbox", name="Estado :").click()
            page.get_by_role("textbox", name="Estado :").fill(estado_nome)
            page.get_by_role("textbox", name="Cidade :").click()
            page.get_by_role("textbox", name="Cidade :").fill(cidade)
            page.get_by_role("textbox", name="N\u00ba :").click()
            page.get_by_role("textbox", name="N\u00ba :").fill(numero_final)
            page.get_by_role("textbox", name="Compl. :").click()
            page.get_by_role("textbox", name="Compl. :").fill(complemento)
            page.get_by_role("textbox", name="Bairro :").click()
            page.get_by_role("textbox", name="Bairro :").fill(bairro)
            page.get_by_role("textbox", name="Cep :").click()
            page.get_by_role("textbox", name="Cep :").fill(cep)

            page.get_by_role("img", name="salvar").click()
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
        except Exception:
            context.close()
            browser.close()
            raise


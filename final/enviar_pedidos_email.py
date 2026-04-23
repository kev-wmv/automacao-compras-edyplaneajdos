import hashlib
import json
import re
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

PDF_PATTERN = re.compile(r"^PEDIDO\s+(.+?)\.pdf$", re.IGNORECASE)
CLIENT_CODE_PATTERN = re.compile(r"^0*(\d+)[A-Z]{2}", re.IGNORECASE)
REGISTRY_FILENAME = "pedidos_email_enviados.json"

ESPECIAL_TOKEN = "ESPECIAL"
ESPECIAL_SUPPLIER_KEY = "ESPECIAL"
# Cobre variacoes: "PEDIDOS FABRICAS", "Pedidos Fabricas", "pedidos fabrica", etc.
PEDIDOS_FABRICAS_PATTERN = re.compile(r"pedidos\s+f[aá]bricas?", re.IGNORECASE)

_registry_lock = threading.Lock()


def extract_client_code(folder_path: Path) -> str:
    """Extrai código do cliente dos nomes de arquivos TXT/XML na pasta do projeto.
    Ex: '06467AA - LIVING.txt' → '6467'
    """
    for f in sorted(folder_path.rglob("*")):
        if f.suffix.lower() in (".txt", ".xml") and f.is_file():
            m = CLIENT_CODE_PATTERN.match(f.stem)
            if m:
                return m.group(1)
    return ""


def _compute_file_key(pdf_path: Path) -> str:
    h = hashlib.sha256()
    try:
        h.update(pdf_path.read_bytes())
    except OSError:
        h.update(str(pdf_path).encode())
    return h.hexdigest()


def _load_registry(folder_path: Path) -> Dict[str, Any]:
    reg_path = folder_path / REGISTRY_FILENAME
    if not reg_path.exists():
        return {}
    try:
        return json.loads(reg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registry(folder_path: Path, data: Dict[str, Any]) -> None:
    reg_path = folder_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def is_already_sent(pdf_path: Path, folder_path: Path) -> bool:
    with _registry_lock:
        registry = _load_registry(folder_path)
        key = _compute_file_key(pdf_path)
        return registry.get(key, {}).get("status") == "enviado"


def mark_email_sent(pdf_path: Path, folder_path: Path, sent_by: str, supplier: str) -> None:
    with _registry_lock:
        registry = _load_registry(folder_path)
        key = _compute_file_key(pdf_path)
        registry[key] = {
            "status": "enviado",
            "path": str(pdf_path),
            "supplier": supplier,
            "sent_by": sent_by,
            "timestamp": datetime.now().timestamp(),
        }
        _save_registry(folder_path, registry)


def unmark_email_sent(pdf_path: Path, folder_path: Path) -> None:
    with _registry_lock:
        registry = _load_registry(folder_path)
        key = _compute_file_key(pdf_path)
        if key in registry:
            del registry[key]
            _save_registry(folder_path, registry)


def _is_under_pedidos_fabricas(pdf_path: Path) -> bool:
    """True se algum ancestral do PDF casa com a pasta 'PEDIDOS FABRICAS' (com variacoes)."""
    for parent in pdf_path.parents:
        if PEDIDOS_FABRICAS_PATTERN.search(parent.name):
            return True
    return False


def _has_especial_sibling(pdf_path: Path) -> bool:
    """True se existe .pdf ou .dxf com 'ESPECIAL' no nome em qualquer descendente
    do parent imediato do PDF. Inclui o proprio PDF na varredura (simplifica o check
    do filename do pedido).
    """
    parent = pdf_path.parent
    token = ESPECIAL_TOKEN.lower()
    for f in parent.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".pdf", ".dxf"):
            continue
        if token in f.name.lower():
            return True
    return False


def _detect_especial(pdf_path: Path) -> bool:
    """ESPECIAL = PDF esta em PEDIDOS FABRICAS E (nome do PDF ou vizinho .pdf/.dxf tem ESPECIAL)."""
    if not _is_under_pedidos_fabricas(pdf_path):
        return False
    return _has_especial_sibling(pdf_path)


def _collect_especial_dxfs(pdf_path: Path) -> List[Path]:
    """Retorna lista ordenada de .dxf com 'ESPECIAL' no nome na arvore do parent do PDF.

    Ex: PDF em FINGER/PEDIDO FINGER.pdf, DXFs em FINGER/DXFs/peca1_ESPECIAL.dxf -> [peca1_ESPECIAL.dxf].
    """
    parent = pdf_path.parent
    token = ESPECIAL_TOKEN.lower()
    found: List[Path] = []
    for f in parent.rglob("*.dxf"):
        if f.is_file() and token in f.name.lower():
            found.append(f)
    return sorted(found)


def scan_pdf_orders(folder_path: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Varre folder_path recursivamente em busca de 'PEDIDO *.pdf'.

    Retorna lista de dicts:
        {id, supplier, path, emails_cc, send_without_cc, can_send, status, checked}
    status: 'pendente' | 'enviado' | 'sem_email'

    Roteamento ESPECIAL: se o PDF esta sob pasta 'PEDIDOS FABRICAS' e o proprio
    filename ou algum .pdf/.dxf vizinho contem 'ESPECIAL', os emails de CC sao
    substituidos por fornecedores_email['ESPECIAL'] (TO continua destino_fixo).
    """
    fornecedores_email: Dict[str, List[str]] = config.get("fornecedores_email", {})
    orders: List[Dict[str, Any]] = []
    seen_names: set = set()

    for pdf in sorted(folder_path.rglob("*.pdf")):
        if not pdf.is_file():
            continue
        m = PDF_PATTERN.match(pdf.name)
        if not m:
            continue
        name_lower = pdf.name.lower()
        if name_lower in seen_names:
            continue
        seen_names.add(name_lower)

        supplier = m.group(1).strip().upper()

        # Roteamento ESPECIAL tem prioridade: se o PDF esta em PEDIDOS FABRICAS
        # e o filename (ou algum .pdf/.dxf vizinho) contem ESPECIAL, usa os emails
        # do entry "ESPECIAL" em vez do fornecedor detectado pelo nome do arquivo.
        # Quando NAO eh especial, a chave ESPECIAL eh excluida do lookup por nome
        # (senao suppliers tipo "VITTA ESPECIAL" casariam via substring match).
        is_especial = _detect_especial(pdf)
        extra_attachments: List[Path] = _collect_especial_dxfs(pdf) if is_especial else []
        if is_especial:
            raw_emails_cc: Optional[List[str]] = fornecedores_email.get(ESPECIAL_SUPPLIER_KEY, [])
        else:
            # Lookup de e-mails: tentativa exata, depois parcial.
            # Exclui ESPECIAL do dicionario de busca pra evitar falso-positivo.
            lookup = {k: v for k, v in fornecedores_email.items()
                      if k.upper() != ESPECIAL_SUPPLIER_KEY}
            raw_emails_cc = lookup.get(supplier)
            if raw_emails_cc is None:
                for key in lookup:
                    if key.upper() in supplier or supplier in key.upper():
                        raw_emails_cc = lookup[key]
                        break
            if raw_emails_cc is None:
                raw_emails_cc = []

        send_without_cc = bool(raw_emails_cc) and all(
            not str(email).strip() for email in raw_emails_cc
        )
        emails_cc = [] if send_without_cc else [
            str(email).strip() for email in raw_emails_cc if str(email).strip()
        ]
        can_send = bool(emails_cc) or send_without_cc

        if is_already_sent(pdf, folder_path):
            status = "enviado"
        elif not can_send:
            status = "sem_email"
        else:
            status = "pendente"

        orders.append({
            "id": str(pdf),
            "supplier": supplier,
            "path": pdf,
            "emails_cc": emails_cc,
            "send_without_cc": send_without_cc,
            "can_send": can_send,
            "status": status,
            "checked": status == "pendente",
            "is_especial": is_especial,
            "extra_attachments": extra_attachments,
        })

    return orders


def build_email_subject(client_code: str, client_name: str, contract: str) -> str:
    client_part = f"{client_code} - {client_name}" if client_code else client_name
    parts = [f"Cliente : {client_part}"]
    if contract:
        parts.append(f"Contrato : {contract}")
    return " / ".join(parts)


def build_email_body(
    supplier: str,
    ocr_data: Dict[str, str],
    client_code: str,
    empresa_info: Dict[str, str],
    loja_nome: str,
    is_especial: bool = False,
) -> str:
    hora = datetime.now().hour
    saudacao = "Bom dia!" if hora < 12 else "Boa tarde!"

    empresa_codigo = empresa_info.get("codigo", "274")
    empresa_nome = empresa_info.get("nome", "EDY SERVICOS EM MOVEIS LTDA")

    client_name = ocr_data.get("cliente", "").strip()
    contract = ocr_data.get("numero_contrato", "").strip()
    cpf = ocr_data.get("cpf_cnpj", "").strip()
    endereco = ocr_data.get("endereco_entrega", "").strip()
    numero = ocr_data.get("numero", "").strip()
    complemento = ocr_data.get("complemento", "").strip()
    bairro = ocr_data.get("bairro", "").strip()
    cidade = ocr_data.get("cidade", "").strip()
    estado = ocr_data.get("estado", "").strip()
    cep = ocr_data.get("cep", "").strip()
    telefone = ocr_data.get("telefone", "").strip()

    # Endereço completo (o campo OCR já costuma conter número; complemento é adicionado se ausente)
    end_line = endereco
    if complemento and complemento.upper() not in end_line.upper():
        end_line += f" - {complemento}"

    # Cidade / Estado
    cidade_estado = cidade
    if estado:
        cidade_estado += f" / {estado}"

    # CEP formatado
    if len(cep) == 8 and cep.isdigit():
        cep_fmt = f"{cep[:5]}-{cep[5:]}"
    else:
        cep_fmt = cep

    # Linha do cliente
    client_line = f"{client_code} - {client_name}" if client_code else client_name

    sep = "-" * 45

    action_line = (
        "Analisar viabilidade de peças e aprovar pra produção."
        if is_especial
        else f"Segue em anexo o pedido referente a {supplier}."
    )

    lines = [
        saudacao,
        "",
        action_line,
        "",
        sep,
        f"Empresa  : {empresa_codigo} - {empresa_nome}",
        f"Loja     : {loja_nome}",
        f"Cliente  : {client_line}",
    ]
    if contract:
        lines.append(f"Contrato : {contract}")
    if cpf:
        lines.append(f"CPF/CNPJ : {cpf}")
    if end_line:
        lines.append(f"Endereco : {end_line}")
    if bairro:
        lines.append(f"Bairro   : {bairro}")
    if cidade_estado:
        lines.append(f"Cidade   : {cidade_estado}")
    if cep_fmt:
        lines.append(f"CEP      : {cep_fmt}")
    if telefone:
        lines.append(f"Telefone : {telefone}")
    lines += [sep, "", "Atenciosamente,", "Edy Planejados"]

    return "\n".join(lines)


def send_pdf_email(
    smtp_cfg: Dict[str, Any],
    sender_email: str,
    sender_password: str,
    cc_emails: List[str],
    subject: str,
    body: str,
    pdf_path: Path,
    extra_attachments: Optional[List[Path]] = None,
) -> None:
    """Envia e-mail com PDF anexado via SMTP (STARTTLS ou SSL).

    BCC para o remetente garante que uma cópia fique na caixa de entrada
    do usuário para consulta futura, pois o KingHost SMTP não salva
    automaticamente os enviados.

    extra_attachments: lista de paths adicionais (ex: .dxf do ESPECIAL) anexados
    junto do PDF com MIME type generico (application/octet-stream).
    """
    msg = EmailMessage()
    msg["From"] = sender_email
    msg["To"] = smtp_cfg["destino_fixo"]
    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)
    # BCC oculto para o próprio remetente — documentação do envio
    msg["Bcc"] = sender_email
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")
    msg.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )
    for attachment in (extra_attachments or []):
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.name,
        )

    host = smtp_cfg["host"]
    port = int(smtp_cfg["port"])
    use_tls = bool(smtp_cfg.get("use_tls", True))

    if use_tls:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)

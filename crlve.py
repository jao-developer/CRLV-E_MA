"""Consulta e tratamento do documento do veículo (CRLV/e-CRLV).

O endpoint pode responder JSON, PDF binário, HTML ou uma string base64. Quando o
conteúdo estiver criptografado, o módulo preserva o retorno para tratamento com
a chave/protocolo oficial; ele não tenta quebrar criptografia.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import requests

from detran_client import BASE_URL, REFERER, VeiculoIdentificacao, proxy_url, decode_base64_pdf

CRLVE_URL = f"{BASE_URL}/Veiculo/DocumentoVeiculo.cshtml"


def _headers() -> dict[str, str]:
    return {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "pt-BR,pt;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": BASE_URL,
        "referer": REFERER,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
    }


def consultar_crlve(
    identificacao: VeiculoIdentificacao,
    *,
    cpf: str,
    codigo_seguranca: str = "",
    proxy: str | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """Consulta o documento usando placa, RENAVAM e CPF fornecidos pelo chamador."""
    data = {
        "placa": identificacao.placa,
        "renavam": identificacao.renavam,
        "documentoproprietario": cpf,
        "codigoseguranca": codigo_seguranca,
    }
    session = requests.Session()
    p = proxy_url(proxy)
    if p:
        session.proxies.update({"http": p, "https": p})
    response = session.post(CRLVE_URL, headers=_headers(), data=data, timeout=timeout)
    response.raise_for_status()
    return interpretar_resposta(response)


def interpretar_resposta(response: requests.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    body = response.content
    if body.startswith(b"%PDF") or "application/pdf" in content_type:
        return {"kind": "pdf", "status_code": response.status_code, "content_type": content_type, "bytes": body, "size": len(body)}

    text = response.text.strip()
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            # O portal pode devolver o PDF dentro de MensagemErro, apesar do
            # nome do campo. Quando Erro=false, esse campo é o documento.
            mensagem = next(
                (value for key, value in parsed.items() if str(key).lower() == "mensagemerro"),
                None,
            )
            erro = next(
                (value for key, value in parsed.items() if str(key).lower() == "erro"),
                None,
            )
            if isinstance(mensagem, str) and mensagem.strip():
                try:
                    pdf = decode_base64_pdf(mensagem)
                    return {
                        "kind": "pdf_base64",
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "bytes": pdf,
                        "size": len(pdf),
                        "source_field": "MensagemErro",
                        "erro": erro,
                    }
                except ValueError:
                    # MensagemErro realmente pode ser uma mensagem textual.
                    pass
        return {"kind": "json", "status_code": response.status_code, "content_type": content_type, "data": parsed}
    except ValueError:
        pass

    # Alguns retornos vêm como JSON entre aspas ou como base64 puro.
    candidate = text
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError:
            pass
    if isinstance(candidate, str):
        try:
            pdf = decode_base64_pdf(candidate)
            return {"kind": "pdf_base64", "status_code": response.status_code, "content_type": content_type, "bytes": pdf, "size": len(pdf)}
        except ValueError:
            pass

    return {"kind": "text_or_encrypted", "status_code": response.status_code, "content_type": content_type, "text": text, "size": len(body)}


def salvar_documento(resultado: dict[str, Any], caminho: str | os.PathLike[str]) -> str:
    """Salva PDF direto/base64. Para retorno criptografado, salva texto bruto .bin."""
    path = Path(caminho)
    kind = resultado.get("kind")
    if kind in {"pdf", "pdf_base64"} and isinstance(resultado.get("bytes"), (bytes, bytearray)):
        path.write_bytes(bytes(resultado["bytes"]))
    else:
        path.write_text(resultado.get("text", ""), encoding="utf-8")
    return str(path)

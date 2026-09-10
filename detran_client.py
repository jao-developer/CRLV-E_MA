"""Cliente reutilizável para endpoints autorizados do Detran-MA.

Não inclui credenciais, placas, RENAVAM, chassi ou CPF reais. Use somente com
permissão e com dados cujo tratamento seja autorizado.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any, Callable, Mapping
from urllib.parse import unquote_plus

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://portal.detrannet.detran.ma.gov.br"
REFERER = f"{BASE_URL}/Veiculo/ExtratoVeiculo.cshtml"

ENDPOINTS: dict[str, tuple[str, int, str]] = {
    "dados_veiculo": ("/Veiculo/Extrato/DadosVeiculo.cshtml", 1503, "DadosVeiculo"),
    "debitos": ("/Veiculo/Extrato/DebitosVeiculo.cshtml", 1630, "DebitosVeiculo"),
    "debitos_autuacao": ("/Veiculo/Extrato/DebitosVeiculoAutuacao.cshtml", 4554, "DebitosVeiculoAutuacao"),
    "ipva": ("/Veiculo/Extrato/ConsultaIpva.cshtml", 2049, "ConsultaIpva"),
    "autuacoes": ("/Veiculo/Extrato/AutuacoesVeiculo.cshtml", 1642, "AutuacoesVeiculo"),
    "multas": ("/Veiculo/Extrato/MultasVeiculo.cshtml", 1643, "MultasVeiculo"),
    "recursos_infracao": ("/Veiculo/Extrato/RecursosInfracao.cshtml", 1648, "RecursosInfracao"),
}


@dataclass(frozen=True)
class VeiculoIdentificacao:
    placa: str
    renavam: str
    chassi: str
    id_veiculo: str
    id_acesso: str

    def as_form(self, id_acao: int, acao: str) -> dict[str, str]:
        return {
            "idAcesso": self.id_acesso,
            "idAcao": str(id_acao),
            "acao": acao,
            "placa": self.placa,
            "renavam": self.renavam,
            "chassi": self.chassi,
            "idVeiculo": self.id_veiculo,
            "flagConsultaSEFAZ": "",
        }


def proxy_url(proxy: str | None = None) -> str | None:
    """Converte host:porta:usuario:senha ou URL em URL de proxy.

    A senha nunca é exibida por esta biblioteca. Prefira DETRAN_PROXY no ambiente.
    """
    value = proxy or os.getenv("DETRAN_PROXY")
    if not value:
        return None
    if "://" in value:
        return value
    parts = value.split(":", 3)
    if len(parts) != 4:
        raise ValueError("DETRAN_PROXY deve estar em host:porta:usuario:senha")
    host, port, user, password = parts
    from urllib.parse import quote
    return f"http://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"


def _headers(accept: str = "text/html, */*; q=0.01") -> dict[str, str]:
    return {
        "accept": accept,
        "accept-language": "pt-BR,pt;q=0.9",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": BASE_URL,
        "referer": REFERER,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
    }


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _scalar(value: str) -> str | int | float | bool | None:
    value = _clean_text(value)
    if not value:
        return None
    if value.lower() in {"sim", "true", "verdadeiro"}:
        return True
    if value.lower() in {"não", "nao", "false", "falso"}:
        return False
    return value


def html_to_json(html: str) -> dict[str, Any]:
    """Extrai tabelas, pares label/valor, inputs e JSON embutido de HTML."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {"tables": [], "fields": {}, "inputs": {}, "embedded_json": []}

    for table in soup.find_all("table"):
        rows: list[list[Any]] = []
        headers: list[str] = []
        for tr in table.find_all("tr"):
            cells = [_scalar(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            if tr.find("th") and not headers:
                headers = [str(c) if c is not None else "" for c in cells]
            else:
                rows.append(cells)
        if headers and rows:
            records = [dict(zip(headers, row + [None] * (len(headers) - len(row)))) for row in rows]
            result["tables"].append({"headers": headers, "rows": records})
        elif rows:
            result["tables"].append({"rows": rows})

    for tag in soup.find_all(["input", "textarea", "select"]):
        name = tag.get("name") or tag.get("id")
        if not name:
            continue
        value = tag.get("value") if tag.name != "select" else (tag.find("option", selected=True) or tag.find("option"))
        if hasattr(value, "get"):
            value = value.get("value")
        result["inputs"][name] = _scalar(value or tag.get_text(" ", strip=True))

    labels = soup.find_all(["label", "dt", "th"])
    for label in labels:
        key = _clean_text(label.get_text(" ", strip=True)).rstrip(":")
        sibling = label.find_next_sibling(["span", "dd", "td", "div"])
        if key and sibling:
            result["fields"][key] = _scalar(sibling.get_text(" ", strip=True))

    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        for match in re.finditer(r"\{(?:[^{}]|\{[^{}]*\})*\}", text):
            candidate = match.group(0)
            try:
                result["embedded_json"].append(json.loads(candidate))
            except json.JSONDecodeError:
                pass

    result["title"] = _clean_text(soup.title.get_text()) if soup.title else None
    result["text"] = _clean_text(soup.get_text(" ", strip=True))
    return result


def response_to_json(response: requests.Response) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            payload = response.json()
            return {"kind": "json", "status_code": response.status_code, "data": payload}
        except ValueError:
            pass
    body = response.content
    if body.startswith(b"%PDF") or "pdf" in content_type:
        return {"kind": "pdf", "status_code": response.status_code, "content_type": content_type, "size": len(body), "bytes": body}
    text = response.text
    return {"kind": "html", "status_code": response.status_code, "content_type": content_type, "data": html_to_json(text)}


class DetranClient:
    def __init__(self, *, proxy: str | None = None, timeout: float = 30, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.timeout = timeout
        p = proxy_url(proxy)
        if p:
            self.session.proxies.update({"http": p, "https": p})

    def consultar(self, identificacao: VeiculoIdentificacao, nome: str) -> dict[str, Any]:
        if nome not in ENDPOINTS:
            raise KeyError(f"Endpoint desconhecido: {nome}")
        path, id_acao, acao = ENDPOINTS[nome]
        response = self.session.post(
            BASE_URL + path,
            headers=_headers(),
            data=identificacao.as_form(id_acao, acao),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return {"endpoint": nome, "url": BASE_URL + path, "result": response_to_json(response)}

    def consultar_tudo(self, identificacao: VeiculoIdentificacao) -> dict[str, Any]:
        saida: dict[str, Any] = {"identificacao": asdict(identificacao), "consultas": {}}
        for nome in ENDPOINTS:
            try:
                saida["consultas"][nome] = self.consultar(identificacao, nome)
            except requests.RequestException as exc:
                saida["consultas"][nome] = {"error": type(exc).__name__, "message": str(exc)}
        return saida


def decode_base64_pdf(value: str | bytes) -> bytes:
    """Decodifica base64 de PDF; não tenta quebrar criptografia desconhecida."""
    raw = value.encode() if isinstance(value, str) else value
    raw = raw.strip()
    if raw.startswith(b"data:"):
        raw = raw.split(b",", 1)[1]
    try:
        decoded = base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("O retorno não é base64 válido") from exc
    if not decoded.startswith(b"%PDF"):
        raise ValueError("Base64 decodificado não começa com assinatura PDF; pode estar criptografado ou ser outro formato")
    return decoded


def salvar_json(payload: Mapping[str, Any], caminho: str) -> None:
    with open(caminho, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2, default=str)

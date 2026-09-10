"""Consulta completa do veículo e gera uma resposta JSON simples e legível.

Preencha as variáveis abaixo antes de executar. A proxy é lida de DETRAN_PROXY
para não deixar a senha gravada no arquivo.
"""
from __future__ import annotations

import base64
import json
import os

from crlve import consultar_crlve, salvar_documento
from detran_client import DetranClient, VeiculoIdentificacao

# ===================== DADOS DA CONSULTA =====================
# SUBSTITUA pelos seus dados autorizados. NÃO commite valores reais.
placa = "ABC1D23"
renavam = "00000000000"
cpf = "00000000000"
chassi = "9C2XXXXXXXXXXXXX"
id_veiculo = "0000000"
id_acesso = "00000000"

codigo_seguranca = ""
proxy = os.getenv("DETRAN_PROXY", "")

arquivo_json = "resultado_detran.json"
arquivo_crlve = "crlve.pdf"
# ============================================================

NOMES_LEGIVEIS = {
    "dados_veiculo": "dados do veículo",
    "debitos": "débitos",
    "debitos_autuacao": "débitos em autuação",
    "ipva": "IPVA",
    "autuacoes": "autuações",
    "multas": "multas",
    "recursos_infracao": "recursos de infração",
}


def texto_da_consulta(retorno: dict) -> str | list[str]:
    """Obtém somente os dados úteis, descartando URL e metadados técnicos."""
    result = retorno.get("result", {})
    if result.get("kind") == "html":
        data = result.get("data", {})
        tabelas = data.get("tables", [])
        campos: list[str] = []
        for tabela in tabelas:
            linhas = tabela.get("rows", []) if isinstance(tabela, dict) else []
            for linha in linhas:
                if isinstance(linha, list):
                    campos.extend(str(item) for item in linha if item)
                elif isinstance(linha, dict):
                    campos.extend(f"{chave}: {valor}" for chave, valor in linha.items() if valor not in (None, ""))
        if campos:
            return campos
        return data.get("text") or "Nenhuma informação encontrada."
    if result.get("kind") == "json":
        data = result.get("data", {})
        if isinstance(data, dict):
            mensagem = next(
                (v for k, v in data.items() if str(k).lower() in {"mensagem", "mensagemerro"} and isinstance(v, str)),
                None,
            )
            if mensagem:
                return mensagem
        return "Resposta recebida."
    return "Resposta recebida."


def montar_resposta_legivel(resultado_bruto: dict, crlve: dict | None, arquivo_pdf: str | None) -> dict:
    """Monta uma resposta voltada somente ao usuário final e ao veículo."""
    consultas = resultado_bruto.get("consultas", {})
    informacoes = {}
    for chave, nome in NOMES_LEGIVEIS.items():
        if chave in consultas:
            informacoes[nome] = texto_da_consulta(consultas[chave])

    resposta = {
        "veiculo": {
            "placa": placa,
            "renavam": renavam,
            "chassi": chassi,
            "informacoes": informacoes,
        }
    }
    if crlve is not None:
        pdf_bytes = crlve.get("bytes")
        disponivel = (
            crlve.get("kind") in {"pdf", "pdf_base64"}
            and isinstance(pdf_bytes, (bytes, bytearray))
            and bytes(pdf_bytes).startswith(b"%PDF")
        )
        resposta["veiculo"]["crlve"] = {
            "disponivel": disponivel,
            "base64": base64.b64encode(bytes(pdf_bytes)).decode("ascii") if disponivel else None,
            "arquivo": arquivo_pdf if arquivo_pdf else None,
        }
    return resposta


def main() -> int:
    veiculo = VeiculoIdentificacao(
        placa=placa,
        renavam=renavam,
        chassi=chassi,
        id_veiculo=id_veiculo,
        id_acesso=id_acesso,
    )
    client = DetranClient(proxy=proxy or None)
    resultado_bruto = client.consultar_tudo(veiculo)

    retorno_crlve = None
    caminho_pdf = None
    try:
        retorno_crlve = consultar_crlve(
            veiculo,
            cpf=cpf,
            codigo_seguranca=codigo_seguranca,
            proxy=proxy or None,
        )
        if "bytes" in retorno_crlve:
            salvar_documento(retorno_crlve, arquivo_crlve)
            caminho_pdf = arquivo_crlve
    except Exception:
        # A resposta JSON continua sendo gerada mesmo se o CRLV falhar.
        retorno_crlve = {"kind": "indisponivel"}

    resposta = montar_resposta_legivel(resultado_bruto, retorno_crlve, caminho_pdf)
    with open(arquivo_json, "w", encoding="utf-8") as arquivo:
        json.dump(resposta, arquivo, ensure_ascii=False, indent=2)
    print(json.dumps(resposta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

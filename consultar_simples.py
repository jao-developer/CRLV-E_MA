"""Consulta simples: basta preencher PLACA, RENAVAM e CPF.

Gera o CRLV/e-CRLV (quando disponível) e um JSON mínimo.
Não grava senha nem dados reais no código — use só com autorização.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from crlve import consultar_crlve, salvar_documento
from detran_client import VeiculoIdentificacao

# ===================== PREENCHA SÓ O QUE É OBRIGATÓRIO =====================
placa = "ABC1D23"          # obrigatório
renavam = "00000000000"    # obrigatório
cpf = "00000000000"        # obrigatório (documento do proprietário)

# Opcional
codigo_seguranca = ""      # se o portal pedir
proxy = os.getenv("DETRAN_PROXY", "")

arquivo_pdf = "crlve.pdf"
arquivo_json = "resultado_simples.json"
# ===========================================================================


@dataclass(frozen=True)
class _IdsVazios:
    """IDs de sessão do extrato — não são necessários para o CRLV."""
    chassi: str = ""
    id_veiculo: str = ""
    id_acesso: str = ""


def main() -> int:
    ids = _IdsVazios()
    veiculo = VeiculoIdentificacao(
        placa=placa.strip().upper(),
        renavam=renavam.strip(),
        chassi=ids.chassi,
        id_veiculo=ids.id_veiculo,
        id_acesso=ids.id_acesso,
    )

    print(f"Consultando CRLV — placa {veiculo.placa} …")
    try:
        retorno = consultar_crlve(
            veiculo,
            cpf=cpf.strip(),
            codigo_seguranca=codigo_seguranca,
            proxy=proxy or None,
        )
    except Exception as exc:
        print(f"Erro na consulta: {type(exc).__name__}: {exc}")
        return 1

    disponivel = (
        retorno.get("kind") in {"pdf", "pdf_base64"}
        and isinstance(retorno.get("bytes"), (bytes, bytearray))
        and bytes(retorno["bytes"]).startswith(b"%PDF")
    )

    caminho = None
    if disponivel:
        caminho = salvar_documento(retorno, arquivo_pdf)
        print(f"PDF salvo em: {caminho} ({retorno.get('size', 0)} bytes)")
    else:
        print("CRLV não disponível neste retorno.")
        print(f"  kind={retorno.get('kind')!r} status={retorno.get('status_code')}")
        if retorno.get("kind") == "json":
            print(f"  data={retorno.get('data')}")
        elif retorno.get("text"):
            trecho = str(retorno["text"])[:300]
            print(f"  texto={trecho!r}")

    resposta = {
        "placa": veiculo.placa,
        "renavam": veiculo.renavam,
        "crlve": {
            "disponivel": disponivel,
            "arquivo": caminho,
            "tamanho_bytes": retorno.get("size") if disponivel else None,
            # base64 só se quiser embutir; costuma ser grande — deixe None se preferir
            "base64": (
                base64.b64encode(bytes(retorno["bytes"])).decode("ascii")
                if disponivel
                else None
            ),
        },
    }

    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(resposta, f, ensure_ascii=False, indent=2)
    print(f"JSON salvo em: {arquivo_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

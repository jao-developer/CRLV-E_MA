# Cliente de consulta Detran-MA (uso autorizado)

Scripts em Python para consultar extrato de veículo e documento (CRLV/e-CRLV) no portal do Detran-MA, **somente com dados e autorização legítimos**.

## Aviso importante

- Use **apenas** com permissão e com dados cujo tratamento seja autorizado.
- **Nunca** versionar placa, RENAVAM, CPF, chassi, IDs reais, PDFs ou JSON de resultados reais.
- Proxy e senhas devem ir só em variável de ambiente (`DETRAN_PROXY`), nunca no código.

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

### Opção 1 — Só o obrigatório (placa + RENAVAM + CPF)

Para baixar o CRLV/e-CRLV, abra `consultar_simples.py`, preencha só estes três campos e rode:

```python
placa = "ABC1D23"
renavam = "00000000000"
cpf = "00000000000"
```

```bash
python consultar_simples.py
```

Saídas: `crlve.pdf` (se disponível) e `resultado_simples.json`.

### Opção 2 — Extrato completo

Precisa também de `chassi`, `id_veiculo` e `id_acesso` (vindos da sessão no portal). Preencha em `dadoscompletos.py` e rode:

```bash
python dadoscompletos.py
```

Saídas: `resultado_detran.json` e `crlve.pdf`.

### Proxy (opcional)

```bash
export DETRAN_PROXY="host:porta:usuario:senha"
```

Ou copie `.env.example` → `.env` e preencha.

## Estrutura

| Arquivo | Função |
|---------|--------|
| `consultar_simples.py` | **Só placa + RENAVAM + CPF** → CRLV |
| `detran_client.py` | Cliente HTTP e parsing HTML/JSON |
| `crlve.py` | Consulta e salvamento do CRLV/e-CRLV |
| `dadoscompletos.py` | Extrato completo + CRLV (precisa de IDs extras) |

## Segurança no GitHub

Antes de qualquer `git push`:

- [ ] Placeholders nos scripts (sem CPF/placa reais)
- [ ] Nenhum JSON de resultado ou PDF no commit
- [ ] `.gitignore` presente
- [ ] Sem senha de proxy no código

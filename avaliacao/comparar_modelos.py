# avaliacao/comparar_modelos.py
#
# Compara as narrativas geradas pelo Gemini Flash e pelo Gemini Pro para o mesmo
# documento, usando o pipeline RAG já existente (Prompt 1 + Prompt 2).
#
# - Roda Prompt 1 (extração) + Prompt 2 (narrativa) para WEGE3, LWSA3 e LAVV3,
#   uma vez com Flash e uma vez com Pro (6 execuções no total).
# - NÃO reindexa nada: usa os chunks já presentes no ChromaDB via recuperar_contexto.
# - Salva progressivamente em avaliacao/comparacao_modelos.json; se travar ou a
#   quota esgotar, retoma de onde parou na próxima execução.
#
# Uso: python avaliacao/comparar_modelos.py

import os
import sys
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import modulos.prompt1 as prompt1
import modulos.prompt2 as prompt2
from modulos.ticker      import validar_ticker, buscar_nome_empresa
from modulos.recuperacao import recuperar_contexto
from config              import MODELO_LLM, MODELO_LLM_PRO

# ── Configuração da avaliação ───────────────────────────────────────────────────

TICKERS = ["WEGE3", "LWSA3", "LAVV3"]

# rótulo legível -> id do modelo no config.py
MODELOS = {
    "flash": MODELO_LLM,
    "pro":   MODELO_LLM_PRO,
}

# Documento avaliado — deve corresponder às collections já indexadas no ChromaDB
TIPO_DOC = "ITR"
PERIODO  = "2026-03-31"

PASTA_SAIDA  = os.path.dirname(__file__)
ARQUIVO_JSON = os.path.join(PASTA_SAIDA, "comparacao_modelos.json")


# ── Persistência (save progressivo + retomada) ──────────────────────────────────

def carregar_resultados() -> dict:
    """Carrega o JSON acumulado ou devolve a estrutura vazia."""
    if os.path.exists(ARQUIVO_JSON):
        with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_resultados(resultados: dict) -> None:
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


def ja_concluido(resultados: dict, ticker: str, rotulo: str) -> bool:
    """True se essa combinação (ticker, modelo) já foi gerada com sucesso."""
    return bool(resultados.get(ticker, {}).get(rotulo, {}).get("sucesso"))


# ── Execução de uma combinação (ticker, modelo) ─────────────────────────────────

def usar_modelo(modelo_id: str) -> None:
    """
    Sobrescreve, em runtime, a constante MODELO_LLM que prompt1/prompt2 importaram
    no momento do import. Como ambos fazem `from config import MODELO_LLM`, o nome
    fica ligado ao namespace de cada módulo — então reatribuímos lá diretamente.
    """
    prompt1.MODELO_LLM = modelo_id
    prompt2.MODELO_LLM = modelo_id


def gerar(ticker: str, rotulo: str, modelo_id: str) -> dict:
    """Roda Prompt 1 + Prompt 2 para um ticker com o modelo escolhido."""
    registro = {
        "modelo":           modelo_id,
        "rotulo":           rotulo,
        "periodo":          PERIODO,
        "gerado_em":        datetime.now(timezone.utc).isoformat(),
        "sucesso":          False,
        "erro":             None,
        "dados_extraidos":  None,
        "narrativa_completa": None,
        "secoes":           None,
    }

    # 1. Resolve nome da empresa
    val = validar_ticker(ticker)
    if not val["valido"]:
        registro["erro"] = val["motivo"]
        return registro
    nome_empresa = buscar_nome_empresa(val["codigo_cvm"])

    # 2. Recupera contexto dos chunks já indexados (sem reindexar)
    print(f"  > recuperando contexto RAG ({ticker})...")
    ctx_num, ctx_nar = recuperar_contexto(ticker, TIPO_DOC, PERIODO)

    # 3. Aponta prompt1/prompt2 para o modelo desta rodada
    usar_modelo(modelo_id)

    # 4. Prompt 1 — extração estruturada
    print(f"  > Prompt 1 (extração) com {modelo_id}...")
    dados = prompt1.executar_prompt_extracao(ctx_num)
    if not dados["sucesso"]:
        registro["erro"] = f"Prompt 1 falhou: {dados['erro']}"
        return registro
    registro["dados_extraidos"] = dados["dados"]

    # 5. Prompt 2 — narrativa
    time.sleep(1)
    print(f"  > Prompt 2 (narrativa) com {modelo_id}...")
    narrativa = prompt2.executar_prompt_narrativa(
        dados, ctx_nar, ticker.upper(), nome_empresa, periodo=PERIODO
    )
    if not narrativa["sucesso"]:
        registro["erro"] = f"Prompt 2 falhou: {narrativa['erro']}"
        registro["narrativa_completa"] = narrativa.get("narrativa_completa")
        registro["secoes"] = narrativa.get("secoes")
        return registro

    registro["narrativa_completa"] = narrativa["narrativa_completa"]
    registro["secoes"]             = narrativa["secoes"]
    registro["sucesso"]            = True
    return registro


# ── Pipeline principal ──────────────────────────────────────────────────────────

def _quota_esgotada(texto: str) -> bool:
    return "429" in texto or "RESOURCE_EXHAUSTED" in texto.upper() or "quota" in texto.lower()


def comparar() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        sys.exit("Erro: defina a variável de ambiente GEMINI_API_KEY antes de rodar.")

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    resultados = carregar_resultados()

    combinacoes = [(t, r, m) for t in TICKERS for r, m in MODELOS.items()]
    total = len(combinacoes)
    feitas = sum(
        1 for t, r, _ in combinacoes if ja_concluido(resultados, t, r)
    )
    if feitas:
        print(f"Retomando: {feitas}/{total} combinação(ões) já concluída(s) no JSON.")

    for i, (ticker, rotulo, modelo_id) in enumerate(combinacoes, 1):
        cabecalho = f"[{i}/{total}] {ticker} — {rotulo} ({modelo_id})"

        if ja_concluido(resultados, ticker, rotulo):
            print(f"{cabecalho}: PULADO (já gerado).")
            continue

        print(cabecalho)
        try:
            registro = gerar(ticker, rotulo, modelo_id)
        except Exception as e:
            if _quota_esgotada(str(e)):
                print(f"  ! Quota esgotada em {ticker}/{rotulo}. Salvando o parcial e encerrando...")
                break
            # Salva o erro para inspeção e segue para a próxima combinação
            registro = {
                "modelo":  modelo_id,
                "rotulo":  rotulo,
                "periodo": PERIODO,
                "gerado_em": datetime.now(timezone.utc).isoformat(),
                "sucesso": False,
                "erro":    f"Exceção: {e}",
            }

        resultados.setdefault(ticker, {})[rotulo] = registro
        salvar_resultados(resultados)

        if registro.get("sucesso"):
            chars = len(registro.get("narrativa_completa") or "")
            print(f"  OK: narrativa com {chars:,} caracteres salva.")
        else:
            print(f"  FALHA: {registro.get('erro')}")
            if _quota_esgotada(str(registro.get("erro", ""))):
                print("  ! Quota esgotada — encerrando para retomar depois.")
                break

    # Resumo final
    concluidas = sum(
        1 for t, r, _ in combinacoes if ja_concluido(resultados, t, r)
    )
    status = "COMPLETO" if concluidas == total else f"PARCIAL ({concluidas}/{total})"
    print(f"\nOK [{status}]: resultados em {ARQUIVO_JSON}")


if __name__ == "__main__":
    comparar()

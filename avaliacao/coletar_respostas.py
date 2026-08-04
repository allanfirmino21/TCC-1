# avaliacao/coletar_respostas.py
#
# Coleta respostas do pipeline RAG + Gemini para uma lista de (ticker, question).
#
# NOTA sobre executar_prompt_extracao:
#   A função original tem prompt fixo (sem slot para question). Por isso este
#   script chama o Gemini diretamente, usando ctx_num como contexto e a
#   question como pergunta livre — mesma chave de API e modelo do config.py.
#
# Saída: avaliacao/respostas_coletadas.json

import os
import sys
import json
import re
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google import genai
from google.genai import types as genai_types
from modulos.recuperacao import recuperar_contexto
from config import MODELO_LLM

# ── Lista de avaliação ─────────────────────────────────────────────────────────

PARES = [
    # WEGE3
    ("WEGE3", "Qual foi a receita líquida da WEG no último trimestre reportado?"),
    ("WEGE3", "Qual foi o lucro líquido consolidado da WEG?"),
    ("WEGE3", "Qual é a margem líquida da WEG?"),
    ("WEGE3", "A WEG tem mais caixa ou mais dívidas?"),
    ("WEGE3", "Qual é o patrimônio líquido consolidado da WEG?"),
    # LWSA3
    ("LWSA3", "Qual foi a receita líquida da Locaweb no último trimestre?"),
    ("LWSA3", "Qual foi o lucro líquido da Locaweb?"),
    ("LWSA3", "Qual é a margem líquida da Locaweb?"),
    ("LWSA3", "Como está a posição de caixa e dívida da Locaweb?"),
    ("LWSA3", "O resultado operacional da Locaweb melhorou ou piorou?"),
    # LAVV3
    ("LAVV3", "Qual foi a receita da Lavvi no último trimestre?"),
    ("LAVV3", "Qual foi o lucro líquido da Lavvi?"),
    ("LAVV3", "Por que o lucro da Lavvi caiu mesmo com a receita crescendo?"),
    ("LAVV3", "Qual é a situação de endividamento da Lavvi?"),
    ("LAVV3", "Qual é a margem líquida da Lavvi?"),
]

# ── Configurações ──────────────────────────────────────────────────────────────

PASTA_SAIDA  = os.path.join(os.path.dirname(__file__))
ARQUIVO_JSON = os.path.join(PASTA_SAIDA, "respostas_coletadas.json")
MAX_TOKENS   = 1024

# Documento avaliado — deve corresponder à collection indexada no ChromaDB
# (collections agora são nomeadas fundia_{ticker}_{tipo}_{periodo})
TIPO_DOC = "ITR"
PERIODO  = "2026-03-31"


# ── Helpers ────────────────────────────────────────────────────────────────────

def extrair_chunks(ctx_num: str) -> list[str]:
    """
    Parseia o ctx_num formatado por recuperacao.py e devolve
    a lista de chunks brutos (texto de cada [Trecho N]).
    """
    partes = re.split(r"\[Trecho \d+\]\n", ctx_num)
    # partes[0] é o cabeçalho "=== CONTEXTO ... ===" — descartamos
    chunks = []
    sep = "-" * 40
    for bloco in partes[1:]:
        texto = bloco.replace(sep, "").strip()
        if texto:
            chunks.append(texto)
    return chunks


def perguntar(ctx_num: str, question: str, cliente: genai.Client,
              tentativas: int = 4, espera_base: int = 15) -> str:
    """
    Envia ctx_num + question ao Gemini e retorna a resposta em texto livre.
    Retentas automaticamente em caso de 503 com backoff exponencial.
    """
    prompt = (
        "Você é um analista financeiro. Com base EXCLUSIVAMENTE nos trechos abaixo, "
        "responda à pergunta de forma objetiva e em português.\n\n"
        "Nota: \"Receita de Venda de Bens e/ou Serviços\" equivale à \"Receita Líquida\" "
        "para fins de análise.\n\n"
        f"## TRECHOS DO DOCUMENTO\n{ctx_num}\n\n"
        f"## PERGUNTA\n{question}"
    )
    ultimo_erro = None
    for t in range(1, tentativas + 1):
        try:
            resp = cliente.models.generate_content(
                model    = MODELO_LLM,
                contents = prompt,
                config   = genai_types.GenerateContentConfig(
                    temperature       = 0.1,
                    max_output_tokens = MAX_TOKENS,
                ),
            )
            return resp.text.strip()
        except Exception as e:
            ultimo_erro = e
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                espera = espera_base * t
                print(f"  ! 503 na tentativa {t}/{tentativas} — aguardando {espera}s...")
                time.sleep(espera)
            else:
                raise
    raise RuntimeError(f"Falha apos {tentativas} tentativas: {ultimo_erro}")


# ── Pipeline principal ─────────────────────────────────────────────────────────

def coletar():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Erro: defina a variável de ambiente GEMINI_API_KEY antes de rodar.")

    os.makedirs(PASTA_SAIDA, exist_ok=True)
    cliente = genai.Client(api_key=api_key)

    # Carrega respostas já coletadas (retomada de execução anterior)
    if os.path.exists(ARQUIVO_JSON):
        with open(ARQUIVO_JSON, "r", encoding="utf-8") as f:
            resultados = json.load(f)
        ja_coletados = {(r["ticker"], r["question"]) for r in resultados}
        print(f"Retomando: {len(resultados)} resposta(s) ja coletada(s) encontrada(s) no JSON.")
    else:
        resultados   = []
        ja_coletados = set()

    quota_esgotada = False

    for i, (ticker, question) in enumerate(PARES, 1):
        # Pula pares já processados
        if (ticker, question) in ja_coletados:
            print(f"[{i}/{len(PARES)}] PULADO (ja coletado): {ticker} - {question}")
            continue

        print(f"[{i}/{len(PARES)}] {ticker} - {question}")

        # 1. Recupera contexto RAG
        print(f"  > recuperando contexto...")
        ctx_num, _ = recuperar_contexto(ticker, TIPO_DOC, PERIODO)
        chunks     = extrair_chunks(ctx_num)
        print(f"  > {len(chunks)} chunks extraidos")

        # 2. Chama o LLM com a question
        print(f"  > chamando Gemini...")
        try:
            answer = perguntar(ctx_num, question, cliente)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"  ! Quota diaria esgotada no par {i}. Salvando o que foi coletado...")
                quota_esgotada = True
                break
            raise

        print(f"  > resposta: {answer[:80]}{'...' if len(answer) > 80 else ''}")

        resultados.append({
            "ticker":   ticker,
            "question": question,
            "answer":   answer,
            "contexts": chunks,
        })
        ja_coletados.add((ticker, question))

        # Salva progressivamente apos cada resposta
        with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)

    # 3. Resumo final
    status = "PARCIAL (quota esgotada)" if quota_esgotada else "COMPLETO"
    print(f"\nOK [{status}]: {len(resultados)}/{len(PARES)} respostas salvas em: {ARQUIVO_JSON}")


if __name__ == "__main__":
    coletar()

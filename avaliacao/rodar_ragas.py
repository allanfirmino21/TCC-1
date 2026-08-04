# avaliacao/rodar_ragas.py
#
# Avalia as respostas coletadas usando RAGAS 0.4.x + Gemini como LLM judge.
#
# Metricas rodadas:
#   - faithfulness      : a resposta e fiel ao contexto recuperado?
#   - answer_relevancy  : a resposta e relevante para a pergunta?
#
# Estrategia anti-timeout:
#   - Processa UMA amostra por vez (EvaluationDataset de 1 elemento)
#   - RunConfig(timeout=120, max_workers=1) — sem paralelismo, 120s por chamada
#   - Pausa de 10s entre amostras para nao sobrecarregar a API
#   - Save progressivo: cada amostra e gravada no JSON imediatamente apos o calculo
#   - Retomada: amostras ja avaliadas (por question) sao puladas
#
# NOTAS de compatibilidade (ragas 0.4.3 + langchain-community 0.4.x):
#   1. langchain_community.chat_models.vertexai removido no langchain-community >= 0.3
#      → stub aplicado antes de qualquer import do ragas
#   2. ragas.metrics.collections usa BaseMetric (incompativel com evaluate())
#      → usamos ragas.metrics._faithfulness / _answer_relevance (herdam de Metric)
#
# Entrada : avaliacao/respostas_coletadas.json
# Saida   : avaliacao/resultados_ragas.json

import sys
import os
import json
import time
import math
import warnings
from types import ModuleType

# ── Stub do modulo removido — DEVE VIR ANTES de qualquer import do ragas ───────
_stub = ModuleType("langchain_community.chat_models.vertexai")
_stub.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules["langchain_community.chat_models.vertexai"] = _stub

# ── Imports ────────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from ragas import EvaluationDataset, evaluate
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics._faithfulness import Faithfulness
from ragas.metrics._answer_relevance import AnswerRelevancy
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ── Caminhos ───────────────────────────────────────────────────────────────────
PASTA        = os.path.dirname(__file__)
ENTRADA_JSON = os.path.join(PASTA, "respostas_coletadas.json")
SAIDA_JSON   = os.path.join(PASTA, "resultados_ragas.json")

# ── Configuracoes de execucao ──────────────────────────────────────────────────
PAUSA_ENTRE_AMOSTRAS = 10   # segundos entre cada amostra
RUN_CFG = RunConfig(
    timeout     = 120,   # segundos por chamada LLM
    max_retries = 3,
    max_workers = 1,     # sem paralelismo
)


def _salvar(resultados: list, saida_json: str) -> None:
    """Persiste o estado atual em disco."""
    nan_safe = []
    for r in resultados:
        nan_safe.append({
            k: (None if isinstance(v, float) and math.isnan(v) else v)
            for k, v in r.items()
        })
    scores_coletados = [r for r in nan_safe
                        if r["faithfulness"] is not None
                        and r["answer_relevancy"] is not None]
    scores_medios = {}
    if scores_coletados:
        scores_medios["faithfulness"]     = round(
            sum(r["faithfulness"]     for r in scores_coletados) / len(scores_coletados), 4)
        scores_medios["answer_relevancy"] = round(
            sum(r["answer_relevancy"] for r in scores_coletados) / len(scores_coletados), 4)
    with open(saida_json, "w", encoding="utf-8") as f:
        json.dump({"scores_medios": scores_medios, "resultados": nan_safe},
                  f, ensure_ascii=False, indent=2)


def rodar():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit("Erro: defina GEMINI_API_KEY antes de rodar.")
    if not os.path.exists(ENTRADA_JSON):
        sys.exit(f"Erro: arquivo nao encontrado: {ENTRADA_JSON}")

    # ── Carrega respostas coletadas ────────────────────────────────────────────
    with open(ENTRADA_JSON, "r", encoding="utf-8") as f:
        entradas = json.load(f)

    # ── Retomada: carrega resultados ja calculados ─────────────────────────────
    if os.path.exists(SAIDA_JSON):
        with open(SAIDA_JSON, "r", encoding="utf-8") as f:
            existente = json.load(f)
        resultados = existente.get("resultados", [])
        ja_avaliados = {r["question"] for r in resultados}
        print(f"Retomando: {len(resultados)} resultado(s) ja calculado(s).")
    else:
        resultados   = []
        ja_avaliados = set()

    # ── LLM judge ─────────────────────────────────────────────────────────────
    print("Configurando LLM judge (Gemini via LangchainLLMWrapper)...")
    evaluator_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(
            model          = "gemini-2.5-flash",
            google_api_key = api_key,
            temperature    = 0.0,
        )
    )

    # ── Embeddings (modelo ja presente no projeto) ────────────────────────────
    print("Carregando embeddings (paraphrase-multilingual-mpnet-base-v2)...")
    evaluator_emb = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )
    )

    # ── Metricas ───────────────────────────────────────────────────────────────
    metricas = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_emb),
    ]

    total   = len(entradas)
    pendentes = [e for e in entradas if e["question"] not in ja_avaliados]
    print(f"\nAmostras: {total} total | {len(resultados)} prontas | {len(pendentes)} pendentes")
    print(f"Config: timeout={RUN_CFG.timeout}s | max_workers={RUN_CFG.max_workers} | "
          f"pausa={PAUSA_ENTRE_AMOSTRAS}s entre amostras\n")

    for idx, entrada in enumerate(pendentes, 1):
        ticker   = entrada["ticker"]
        question = entrada["question"]
        print(f"[{idx}/{len(pendentes)}] {ticker} — {question[:70]}")

        # Dataset de 1 amostra
        sample  = SingleTurnSample(
            user_input         = question,
            response           = entrada["answer"],
            retrieved_contexts = entrada["contexts"],
            reference          = entrada.get("ground_truth", ""),
        )
        dataset = EvaluationDataset(samples=[sample])

        try:
            resultado = evaluate(
                dataset    = dataset,
                metrics    = metricas,
                run_config = RUN_CFG,
            )
            df  = resultado.to_pandas()
            row = df.iloc[0]
            faith = float(row["faithfulness"])
            relev = float(row["answer_relevancy"])
            print(f"  faithfulness={faith:.4f}  answer_relevancy={relev:.4f}")
        except Exception as e:
            print(f"  ERRO: {e}")
            faith = float("nan")
            relev = float("nan")

        resultados.append({
            "ticker":           ticker,
            "question":         question,
            "answer":           entrada["answer"],
            "ground_truth":     entrada.get("ground_truth", ""),
            "faithfulness":     faith,
            "answer_relevancy": relev,
        })

        # Save progressivo
        _salvar(resultados, SAIDA_JSON)
        print(f"  salvo. ({len(resultados)}/{total} no JSON)")

        # Pausa entre amostras (exceto na ultima)
        if idx < len(pendentes):
            print(f"  aguardando {PAUSA_ENTRE_AMOSTRAS}s...")
            time.sleep(PAUSA_ENTRE_AMOSTRAS)

    # ── Resumo final ───────────────────────────────────────────────────────────
    completos = [r for r in resultados
                 if r["faithfulness"] is not None
                 and r["answer_relevancy"] is not None]
    print(f"\n=== RESUMO FINAL ===")
    print(f"Avaliados: {len(resultados)}/{total} | "
          f"Scores completos (sem NaN): {len(completos)}/{total}")

    if completos:
        print(f"\n=== SCORES POR AMOSTRA ===")
        for r in resultados:
            f_str = f"{r['faithfulness']:.4f}"     if r["faithfulness"]     is not None else "NaN"
            r_str = f"{r['answer_relevancy']:.4f}" if r["answer_relevancy"] is not None else "NaN"
            print(f"  [{r['ticker']}] faithfulness={f_str}  answer_relevancy={r_str}")
            print(f"         {r['question'][:80]}")

        media_f = sum(r["faithfulness"]     for r in completos) / len(completos)
        media_r = sum(r["answer_relevancy"] for r in completos) / len(completos)
        print(f"\n=== SCORES MEDIOS (n={len(completos)}) ===")
        print(f"  faithfulness:     {media_f:.4f}")
        print(f"  answer_relevancy: {media_r:.4f}")

    print(f"\nOK: resultados em {SAIDA_JSON}")


if __name__ == "__main__":
    rodar()

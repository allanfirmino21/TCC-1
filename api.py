# api.py — Backend FastAPI do fundIA
#
# Expõe o pipeline de análise (modulos/) como API REST:
#
#   GET  /api/status          — verifica se a GEMINI_API_KEY está configurada
#   GET  /api/analisar        — roda o pipeline com progresso em tempo real (SSE)
#   GET  /api/fonte           — baixa o documento CVM analisado (cache da empresa)
#   POST /api/pdf             — gera o PDF da análise a partir das seções
#
# Como rodar:  uvicorn api:app --port 8000
# O frontend React (frontend/) consome esta API via proxy do Vite.

import os
import re
import json
import queue
import threading

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from config import CAMINHO_CACHE

from modulos.orquestrador import analisar
from modulos.relatorio_pdf import gerar_pdf

# ── Chave da API Gemini: variável de ambiente ou api_key.txt na raiz ──────────
if not os.getenv("GEMINI_API_KEY"):
    _caminho_chave = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.txt")
    if os.path.exists(_caminho_chave):
        with open(_caminho_chave, "r", encoding="utf-8") as f:
            os.environ["GEMINI_API_KEY"] = f.read().strip()

app = FastAPI(title="fundIA API", version="1.0")

# CORS liberado para o dev server do Vite (localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def status():
    return {
        "api_key_configurada": bool(os.getenv("GEMINI_API_KEY")),
        "versao": "1.0",
    }


@app.get("/api/analisar")
def analisar_sse(ticker: str, tipo: str = "ITR", forcar: bool = False):
    """
    Roda o pipeline em uma thread e transmite o progresso via Server-Sent Events.

    Eventos emitidos:
      event: progresso  → {"etapa": "3/7", "msg": "Baixando..."}
      event: resultado  → dict completo do orquestrador (sucesso)
      event: erro       → {"erro": "mensagem"}
    """
    fila: queue.Queue = queue.Queue()
    FIM = object()

    def _progresso(etapa: str, msg: str) -> None:
        fila.put(("progresso", {"etapa": etapa, "msg": msg}))

    def _rodar() -> None:
        try:
            resultado = analisar(ticker, tipo_doc=tipo, forcar=forcar,
                                 on_progress=_progresso)
            if resultado.get("erro"):
                fila.put(("erro", {"erro": resultado["erro"]}))
            else:
                fila.put(("resultado", resultado))
        except Exception as e:
            fila.put(("erro", {"erro": f"Falha inesperada no pipeline: {e}"}))
        finally:
            fila.put(FIM)

    threading.Thread(target=_rodar, daemon=True).start()

    def _eventos():
        while True:
            item = fila.get()
            if item is FIM:
                break
            evento, dados = item
            yield f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _eventos(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/fonte")
def baixar_fonte(ticker: str, tipo: str = "ITR", periodo: str = ""):
    """
    Devolve o documento estruturado da CVM usado na análise e na auditoria —
    o extrato específico da empresa, salvo em cache pelo pipeline. É a fonte
    exata contra a qual os números da narrativa foram conferidos.
    """
    # Sanitização: só caracteres esperados, sem separadores de caminho
    ticker  = re.sub(r"[^A-Z0-9]", "", ticker.upper())[:6]
    tipo    = "DFP" if tipo.upper() == "DFP" else "ITR"
    periodo = re.sub(r"[^0-9-]", "", periodo)[:10]
    if not ticker or not periodo:
        raise HTTPException(400, "Parâmetros ticker e periodo são obrigatórios.")

    caminho = os.path.join(CAMINHO_CACHE, f"{ticker}_{tipo}_{periodo}.txt")
    if not os.path.exists(caminho):
        raise HTTPException(
            404, "Documento não encontrado no cache. Rode a análise primeiro."
        )
    return FileResponse(
        caminho,
        media_type="text/plain; charset=utf-8",
        filename=f"CVM_{ticker}_{tipo}_{periodo}.txt",
    )


class PedidoPDF(BaseModel):
    empresa: str
    ticker: str
    periodo: str
    tipo_doc: str
    secoes: dict


@app.post("/api/pdf")
def baixar_pdf(pedido: PedidoPDF):
    pdf = gerar_pdf(pedido.empresa, pedido.ticker, pedido.periodo,
                    pedido.tipo_doc, pedido.secoes)
    nome = f"fundia_{pedido.ticker}_{pedido.periodo}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )

# modulos/recuperacao.py
import logging
import os
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List, Tuple
from modulos.chunking import nome_collection
from config import MODELO_EMBEDDINGS, MAX_CHUNKS_NUMERICO, MAX_CHUNKS_NARRATIVO, CAMINHO_CHROMA

# Silencia avisos de carregamento do modelo (mesmo tratamento de chunking.py)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

QUERY_NUMERICO = "receita líquida lucro bruto EBITDA margem operacional lucro líquido endividamento dívida caixa resultado financeiro variação percentual"
QUERY_NARRATIVO = "desempenho operacional comentários da administração perspectivas principais eventos mercado estratégia riscos destaques do período"

def recuperar_contexto(ticker: str, tipo_doc: str, periodo: str) -> Tuple[str, str]:
    modelo     = SentenceTransformer(MODELO_EMBEDDINGS)
    cliente    = chromadb.PersistentClient(path=CAMINHO_CHROMA)
    collection = cliente.get_collection(nome_collection(ticker, tipo_doc, periodo))
    ctx_num = _recuperar_canal(collection, modelo, QUERY_NUMERICO,  "tabela",    MAX_CHUNKS_NUMERICO)
    ctx_nar = _recuperar_canal(collection, modelo, QUERY_NARRATIVO, "narrativo", MAX_CHUNKS_NARRATIVO)
    return ctx_num, ctx_nar

def _recuperar_canal(collection, modelo, query, tipo_prio, n) -> str:
    emb = modelo.encode(query).tolist()
    try:
        if tipo_prio == "tabela":
            where_cons = {"$and": [{"tipo": {"$eq": "tabela"}}, {"base": {"$eq": "Consolidado"}}]}
            res    = collection.query(query_embeddings=[emb], n_results=n, where=where_cons)
            chunks = res["documents"][0]
            if not chunks:
                print("[recuperacao] aviso: nenhum chunk Consolidado encontrado — fallback sem filtro de base")
                res    = collection.query(query_embeddings=[emb], n_results=n, where={"tipo": tipo_prio})
                chunks = res["documents"][0]
        else:
            res    = collection.query(query_embeddings=[emb], n_results=n, where={"tipo": tipo_prio})
            chunks = res["documents"][0]
        ids = set(res["ids"][0])
    except Exception:
        chunks, ids = [], set()
    if len(chunks) < n:
        tipo_sec = "narrativo" if tipo_prio == "tabela" else "tabela"
        try:
            res2 = collection.query(query_embeddings=[emb], n_results=n - len(chunks), where={"tipo": tipo_sec})
            for doc, id_ in zip(res2["documents"][0], res2["ids"][0]):
                if id_ not in ids:
                    chunks.append(doc)
        except Exception:
            pass
    return _formatar_contexto(chunks, tipo_prio)

def _formatar_contexto(chunks: List[str], rotulo: str) -> str:
    sep = "-" * 40
    blocos = [f"[Trecho {i+1}]\n{c}" for i, c in enumerate(chunks)]
    return f"=== CONTEXTO {rotulo.upper()} ===\n{sep}\n{(chr(10)+sep+chr(10)).join(blocos)}\n{sep}"
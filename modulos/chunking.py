# modulos/chunking.py
import logging
import os
import re
import chromadb
from sentence_transformers import SentenceTransformer
from typing import List
from modulos.extracao import SecaoDocumento
from config import MODELO_EMBEDDINGS, MAX_PALAVRAS_CHUNK, OVERLAP_PALAVRAS, CAMINHO_CHROMA

# Silencia o LOAD REPORT e os avisos de HF Hub no console.
# O modelo carrega normalmente — são apenas mensagens informativas de bibliotecas.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

def criar_chunks(secoes: List[SecaoDocumento]) -> List[dict]:
    chunks = []
    for secao in secoes:
        if secao.tipo == "tabela":
            chunks.append({
                "id":       f"p{secao.pagina}_tab_{len(chunks)}",
                "texto":    f"[TABELA | {secao.titulo}]\n{_limpar_tabela(secao.conteudo)}",
                "metadata": {"tipo": "tabela", "secao": secao.titulo, "pagina": secao.pagina, "base": secao.base}
            })
            continue
        palavras = secao.conteudo.split()
        if len(palavras) <= MAX_PALAVRAS_CHUNK:
            chunks.append({
                "id":       f"p{secao.pagina}_nar_{len(chunks)}",
                "texto":    f"[SEÇÃO: {secao.titulo}]\n{secao.conteudo}",
                "metadata": {"tipo": "narrativo", "secao": secao.titulo, "pagina": secao.pagina}
            })
        else:
            subs = _dividir_com_overlap(palavras, MAX_PALAVRAS_CHUNK, OVERLAP_PALAVRAS)
            for i, sub in enumerate(subs):
                chunks.append({
                    "id":       f"p{secao.pagina}_nar_{len(chunks)}_pt{i+1}",
                    "texto":    f"[SEÇÃO: {secao.titulo} — parte {i+1}/{len(subs)}]\n{' '.join(sub)}",
                    "metadata": {"tipo": "narrativo", "secao": secao.titulo, "pagina": secao.pagina, "parte": i + 1}
                })
    return chunks

# Linha de tabela da CVM: "Nome da Conta    VALOR  (anterior: VALOR)" — anterior opcional
_RE_LINHA_TABELA = re.compile(
    r"^(?P<conta>.*?)\s{2,}(?P<atual>-?\d+(?:\.\d+)?)"
    r"(?:\s+\(anterior:\s*(?P<anterior>-?\d+(?:\.\d+)?)\))?\s*$"
)

def _formatar_valor(bruto: str) -> str:
    """9468313.0000000000 → 9.468.313 | 0.3472900000 → 0,3473 (até 4 decimais)."""
    texto = f"{float(bruto):,.4f}"
    texto = texto.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return texto.rstrip("0").rstrip(",")

def _limpar_tabela(conteudo: str) -> str:
    """
    Limpa o texto tabular antes da indexação:
    - remove linhas sem informação (valor atual E anterior iguais a zero);
    - normaliza os números (sem decimais excedentes, milhar com ponto).
    Linhas fora do padrão CVM passam inalteradas.
    """
    linhas = []
    for linha in conteudo.split("\n"):
        m = _RE_LINHA_TABELA.match(linha)
        if not m:
            linhas.append(linha)
            continue
        atual    = float(m.group("atual"))
        anterior = float(m.group("anterior")) if m.group("anterior") else 0.0
        if atual == 0 and anterior == 0:
            continue
        conta     = m.group("conta").strip()
        valor_fmt = _formatar_valor(m.group("atual"))
        if m.group("anterior"):
            linhas.append(f"{conta:<55} {valor_fmt:>15}  (anterior: {_formatar_valor(m.group('anterior'))})")
        else:
            linhas.append(f"{conta:<55} {valor_fmt:>15}")
    return "\n".join(linhas)

def nome_collection(ticker: str, tipo_doc: str, periodo: str) -> str:
    """Nome único por documento: evita misturar chunks de períodos/tipos diferentes."""
    return f"fundia_{ticker.lower()}_{tipo_doc.lower()}_{periodo.replace('/', '-')}"

def indexar_documento(ticker: str, chunks: List[dict], tipo_doc: str, periodo: str,
                      forcar: bool = False) -> object:
    modelo  = SentenceTransformer(MODELO_EMBEDDINGS)
    cliente = chromadb.PersistentClient(path=CAMINHO_CHROMA)
    nome    = nome_collection(ticker, tipo_doc, periodo)
    if forcar:
        try: cliente.delete_collection(nome)
        except: pass
    collection = cliente.get_or_create_collection(
        nome, metadata={"ticker": ticker, "tipo_doc": tipo_doc, "periodo": periodo})
    textos = [c["texto"]    for c in chunks]
    ids    = [c["id"]       for c in chunks]
    metas  = [c["metadata"] for c in chunks]
    embeddings = modelo.encode(textos, show_progress_bar=False).tolist()
    collection.add(documents=textos, embeddings=embeddings, metadatas=metas, ids=ids)
    return collection

def _dividir_com_overlap(palavras, tamanho, overlap):
    subs, inicio = [], 0
    while inicio < len(palavras):
        subs.append(palavras[inicio:inicio + tamanho])
        inicio += tamanho - overlap
    return subs
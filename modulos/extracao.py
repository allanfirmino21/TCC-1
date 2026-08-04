# modulos/extracao.py
import re, os
import pdfplumber
from dataclasses import dataclass
from typing import List

@dataclass
class SecaoDocumento:
    titulo:   str
    tipo:     str
    conteudo: str
    pagina:   int
    base:     str = "desconhecido"

def extrair_documento(caminho: str) -> List[SecaoDocumento]:
    """
    Detecta automaticamente o formato do arquivo e extrai o conteúdo.
    Suporta PDF (pdfplumber) e TXT (dados estruturados da CVM).
    Lança ValueError com mensagem clara em caso de falha.
    """
    if not os.path.exists(caminho):
        raise ValueError(
            f"Arquivo não encontrado: '{os.path.basename(caminho)}'. "
            "O download pode ter falhado. Tente novamente com 'Forçar novo download'."
        )
    if os.path.getsize(caminho) == 0:
        raise ValueError(
            f"O arquivo '{os.path.basename(caminho)}' está vazio. "
            "O download pode ter sido interrompido. Tente novamente."
        )
    ext = os.path.splitext(caminho)[1].lower()
    if ext == ".txt":
        return _extrair_txt(caminho)
    return _extrair_pdf(caminho)

# ── Extração de TXT estruturado (CSVs formatados) ────────────────────────────

def _extrair_txt(caminho: str) -> List[SecaoDocumento]:
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
    except OSError as e:
        raise ValueError(
            f"Não foi possível ler o arquivo '{os.path.basename(caminho)}': {e}"
        ) from e

    if not conteudo.strip():
        raise ValueError(
            f"O arquivo '{os.path.basename(caminho)}' está vazio ou sem conteúdo legível. "
            "Tente novamente com 'Forçar novo download'."
        )

    secoes = []
    blocos = re.split(r'\n={50}\n', conteudo)

    # Primeiro bloco: cabeçalho do documento
    if blocos:
        secoes.append(SecaoDocumento(
            titulo="Cabeçalho",
            tipo="narrativo",
            conteudo=blocos[0].strip(),
            pagina=1
        ))

    # Demais blocos: seções financeiras (título + dados)
    for i in range(1, len(blocos), 2):
        titulo  = blocos[i].strip() if i < len(blocos) else "Seção"
        conteudo_bloco = blocos[i+1].strip() if i+1 < len(blocos) else ""
        if not conteudo_bloco:
            continue
        if "(Consolidado)" in titulo:
            base = "Consolidado"
        elif "(Individual)" in titulo:
            base = "Individual"
        else:
            base = "desconhecido"
        secoes.append(SecaoDocumento(
            titulo=titulo,
            tipo="tabela",
            conteudo=conteudo_bloco,
            pagina=i // 2 + 1,
            base=base,
        ))

    return secoes

# ── Extração de PDF ──────────────────────────────────────────────────────────

def _extrair_pdf(caminho: str) -> List[SecaoDocumento]:
    nome_base = os.path.basename(caminho)

    # Tenta abrir o PDF antes de entrar no loop de páginas
    try:
        pdf_handle = pdfplumber.open(caminho)
    except Exception as e:
        raise ValueError(
            f"Não foi possível abrir o PDF '{nome_base}'. "
            "O arquivo pode estar corrompido, protegido por senha ou em formato não suportado. "
            f"Detalhe: {e}"
        ) from e

    secoes = []
    secao_atual_titulo   = "Introdução"
    secao_atual_conteudo = []
    pagina_inicio        = 1
    paginas_com_texto    = 0

    try:
        with pdf_handle as pdf:
            for num_pagina, pagina in enumerate(pdf.pages, start=1):
                # Tabelas
                try:
                    tabelas = pagina.extract_tables() or []
                except Exception:
                    tabelas = []
                for tabela in tabelas:
                    if tabela and len(tabela) > 1:
                        secoes.append(SecaoDocumento(
                            titulo=f"{secao_atual_titulo} — tabela",
                            tipo="tabela",
                            conteudo=_formatar_tabela(tabela),
                            pagina=num_pagina
                        ))

                # Texto corrido
                try:
                    texto = pagina.extract_text(layout=True)
                except Exception:
                    texto = None

                if not texto:
                    continue
                paginas_com_texto += 1
                for linha in texto.split("\n"):
                    linha = linha.strip()
                    if not linha:
                        continue
                    if _eh_cabecalho(linha):
                        if secao_atual_conteudo:
                            secoes.append(SecaoDocumento(
                                titulo=secao_atual_titulo,
                                tipo="narrativo",
                                conteudo="\n".join(secao_atual_conteudo),
                                pagina=pagina_inicio
                            ))
                        secao_atual_titulo   = linha
                        secao_atual_conteudo = []
                        pagina_inicio        = num_pagina
                    else:
                        secao_atual_conteudo.append(linha)
    except ValueError:
        raise   # re-propaga os nossos próprios erros descritivos
    except Exception as e:
        raise ValueError(
            f"Erro ao processar o PDF '{nome_base}': {e}. "
            "O arquivo pode estar corrompido ou com páginas danificadas."
        ) from e

    if secao_atual_conteudo:
        secoes.append(SecaoDocumento(
            titulo=secao_atual_titulo,
            tipo="narrativo",
            conteudo="\n".join(secao_atual_conteudo),
            pagina=pagina_inicio
        ))

    # PDF sem texto extraível (provavelmente escaneado sem OCR)
    if paginas_com_texto == 0 and not any(s.tipo == "tabela" for s in secoes):
        raise ValueError(
            f"Nenhum texto extraível encontrado em '{nome_base}'. "
            "O PDF parece conter apenas imagens (documento escaneado sem OCR). "
            "Este sistema suporta apenas documentos com texto selecionável."
        )

    return secoes

def verificar_qualidade_extracao(secoes: List[SecaoDocumento]) -> dict:
    total_chars  = sum(len(s.conteudo) for s in secoes)
    total_secoes = len(secoes)
    extraivel    = total_chars > 100

    if not extraivel:
        if total_chars == 0:
            aviso = (
                "O documento não contém texto extraível. "
                "Verifique se é um PDF escaneado sem OCR ou um arquivo corrompido."
            )
        else:
            aviso = (
                f"Conteúdo insuficiente ({total_chars} caracteres extraídos). "
                "O documento pode estar incompleto ou em formato não suportado."
            )
    else:
        aviso = None

    return {
        "extraivel":            extraivel,
        "chars_totais":         total_chars,
        "secoes_identificadas": total_secoes,
        "aviso":                aviso,
    }

def _eh_cabecalho(linha: str) -> bool:
    padroes = [
        r'^\d+\.\s+[A-ZÁÉÍÓÚÂÊÎÔÛÃÕ]',
        r'^[A-ZÁÉÍÓÚÂÊÎÔÛÃÕ\s]{10,50}$',
        r'^[A-ZÁÉÍÓÚÂÊÎÔÛÃÕ][a-záéíóúâêîôûãõ\s]+:$',
    ]
    return any(re.match(p, linha) for p in padroes)

def _formatar_tabela(tabela: list) -> str:
    linhas = []
    for linha in tabela:
        celulas = [str(c).strip() if c else "" for c in linha]
        celulas = [c for c in celulas if c]
        if celulas:
            linhas.append(" | ".join(celulas))
    return "\n".join(linhas)

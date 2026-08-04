# modulos/relatorio_pdf.py
#
# Geração do PDF da análise — usado pela API FastAPI (e reutilizável por
# qualquer outra interface). Recebe os metadados e as 7 seções da narrativa
# e devolve os bytes do PDF, sem tocar em disco.

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

# Ordem e títulos amigáveis das seções no PDF
SECOES_PDF = {
    "RESUMO":                   "Resumo Executivo",
    "O QUE A EMPRESA FATURA":   "O Que a Empresa Fatura",
    "LUCRO":                    "Lucro do Período",
    "SAUDE DO CAIXA E DIVIDAS": "Caixa e Dívidas",
    "O QUE FOI POSITIVO":       "O Que Foi Positivo",
    "O QUE MERECE ATENCAO":     "O Que Merece Atenção",
    "LIMITACOES DESTA ANALISE": "Limitações desta Análise",
}


def _escape_xml(texto: str) -> str:
    """Prepara texto para os Paragraph do reportlab: escapa XML e quebras de linha."""
    txt = (texto.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    return txt.replace("\n", "<br/>")


def gerar_pdf(empresa: str, ticker: str, periodo: str,
              tipo_doc: str, secoes: dict) -> bytes:
    """
    Gera o PDF da análise em memória e retorna os bytes.

    Estrutura:
      • Título: nome da empresa + ticker
      • Subtítulo: tipo de relatório + período
      • As 7 seções da narrativa; seções sem conteúdo são puladas.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"fundIA — {ticker}",
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "TituloEmpresa", parent=estilos["Title"],
        fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=4,
    )
    estilo_subtitulo = ParagraphStyle(
        "Subtitulo", parent=estilos["Normal"],
        fontSize=10, leading=13, alignment=TA_CENTER,
        textColor="#666666", spaceAfter=18,
    )
    estilo_secao = ParagraphStyle(
        "TituloSecao", parent=estilos["Heading2"],
        fontSize=13, leading=16, spaceBefore=12, spaceAfter=6,
    )
    estilo_corpo = ParagraphStyle(
        "Corpo", parent=estilos["Normal"],
        fontSize=10.5, leading=15, spaceAfter=6,
    )

    elementos = [
        Paragraph(f"{_escape_xml(empresa)} ({_escape_xml(ticker)})", estilo_titulo),
        Paragraph(f"Relatório {_escape_xml(tipo_doc)} · Período {_escape_xml(periodo)}",
                  estilo_subtitulo),
    ]

    for chave, titulo in SECOES_PDF.items():
        texto = (secoes.get(chave) or "").strip()
        if not texto:
            continue
        elementos.append(Paragraph(_escape_xml(titulo), estilo_secao))
        elementos.append(Paragraph(_escape_xml(texto), estilo_corpo))
        elementos.append(Spacer(1, 4))

    doc.build(elementos)
    return buffer.getvalue()

import os
import sys
import io
import contextlib

import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

sys.path.insert(0, ".")

from modulos.orquestrador import analisar

# ── Configuração global da página ─────────────────────────────────────────────
st.set_page_config(
    page_title = "fundIA — Análise Fundamentalista",
    page_icon  = "📊",  
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

# ── Mapa de seções: chave normalizada → (ícone, título amigável) ──────────────
SECOES = {
    "RESUMO":                   ("📋", "Resumo Executivo"),
    "O QUE A EMPRESA FATURA":   ("💰", "O Que a Empresa Fatura"),
    "LUCRO":                    ("📈", "Lucro do Período"),
    "SAUDE DO CAIXA E DIVIDAS": ("🏦", "Caixa e Dívidas"),
    "O QUE FOI POSITIVO":       ("✅", "O Que Foi Positivo"),
    "O QUE MERECE ATENCAO":     ("⚠️",  "O Que Merece Atenção"),
    "LIMITACOES DESTA ANALISE": ("ℹ️",  "Limitações desta Análise"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _silente(fn, *args, **kwargs):
    """Executa fn suprimindo stdout (logs de terminal) para não poluir o UI."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _delta(variacao: str) -> str | None:
    """Converte '+6,1%' em string compatível com st.metric(delta=...)."""
    if not variacao or variacao in ("nao_disponivel", "—"):
        return None
    return variacao.replace(",", ".")


def _secao(chave: str, secoes: dict) -> str:
    """Retorna o texto da seção ou string vazia."""
    return secoes.get(chave, "").strip()


def _md(texto: str) -> str:
    """
    Escapa cifrões para evitar que o Streamlit interprete 'R$ X' como LaTeX.
    Streamlit usa $...$ como delimitador de fórmulas matemáticas; sem o escape
    o texto fica colado e ilegível (ex: 'R32,76bilhõesneste...').
    """
    return texto.replace("$", r"\$")


def _escape_pdf(texto: str) -> str:
    """
    Prepara texto para os Paragraph do reportlab: escapa caracteres XML
    e converte quebras de linha em <br/>.
    """
    txt = (texto.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    return txt.replace("\n", "<br/>")


def _gerar_pdf(empresa: str, ticker: str, periodo: str,
               tipo_doc: str, secoes: dict) -> bytes:
    """
    Gera o PDF da análise em memória (sem salvar em disco) e retorna os bytes.

    Estrutura:
      • Título: nome da empresa + ticker
      • Subtítulo: tipo de relatório + período
      • As 7 seções da narrativa, cada uma com o título em negrito.
        Seções sem conteúdo são puladas.

    Os emojis dos títulos são omitidos — as fontes padrão do reportlab
    não os renderizam; usa-se apenas o texto amigável de SECOES.
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
        Paragraph(f"{_escape_pdf(empresa)} ({_escape_pdf(ticker)})", estilo_titulo),
        Paragraph(f"Relatório {_escape_pdf(tipo_doc)} · Período {_escape_pdf(periodo)}",
                  estilo_subtitulo),
    ]

    # Itera na ordem definida em SECOES, pulando seções vazias.
    for chave, (_icone, titulo) in SECOES.items():
        texto = (secoes.get(chave) or "").strip()
        if not texto:
            continue
        elementos.append(Paragraph(_escape_pdf(titulo), estilo_secao))
        elementos.append(Paragraph(_escape_pdf(texto), estilo_corpo))
        elementos.append(Spacer(1, 4))

    doc.build(elementos)
    return buffer.getvalue()


# ── Pipeline com progresso visual ─────────────────────────────────────────────

def rodar_pipeline(ticker: str, tipo: str, forcar: bool) -> dict:
    """
    Delega ao orquestrador.analisar() e espelha o progresso no st.status.
    Retorna o dict do orquestrador: ticker, tipo_documento, nome_empresa,
    etapas, analise, erro.
    """
    with st.status("Iniciando análise...", expanded=True) as status:

        def _progresso(etapa: str, msg: str) -> None:
            if etapa == "ERRO":
                status.update(label=msg, state="error")
            else:
                status.write(f"**[{etapa}]** {msg}")

        resultado = _silente(
            analisar, ticker, tipo_doc=tipo, forcar=forcar, on_progress=_progresso
        )

        if not resultado["erro"]:
            status.update(
                label    = f"Análise de {resultado['nome_empresa']} concluída!",
                state    = "complete",
                expanded = False,
            )

    return resultado


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📊 fundIA")
    st.caption("Análise fundamentalista automatizada via RAG + IA")
    st.divider()

    ticker_input = st.text_input(
        "Ticker da empresa",
        value       = st.session_state.get("ultimo_ticker", "WEGE3"),
        max_chars   = 6,
        placeholder = "Ex: WEGE3",
        help        = "Código da ação na B3 (ex.: WEGE3, B3SA3)",
    ).strip().upper()

    tipo_doc = st.radio(
        "Tipo de relatório",
        options  = ["ITR", "DFP"],
        index    = 0,
        help     = "**ITR** = trimestral | **DFP** = anual",
        horizontal = True,
    )

    forcar = st.checkbox(
        "Forçar novo download",
        value = False,
        help  = "Ignorar cache local e baixar novamente da CVM",
    )

    st.divider()

    # API Key — lê da variável de ambiente ou permite digitar na UI
    api_env = os.getenv("GEMINI_API_KEY", "")
    if not api_env:
        api_input = st.text_input(
            "Gemini API Key",
            type  = "password",
            help  = "Obtenha em aistudio.google.com · Opcional se GEMINI_API_KEY estiver definida",
        ).strip()
        if api_input:
            os.environ["GEMINI_API_KEY"] = api_input
    else:
        st.success("GEMINI_API_KEY configurada.", icon="🔑")

    api_ok = bool(os.getenv("GEMINI_API_KEY"))

    if not api_ok:
        st.warning("Informe a Gemini API Key para habilitar a análise.")

    st.divider()

    btn_analisar = st.button(
        "🔍  Analisar",
        use_container_width = True,
        disabled            = not (api_ok and ticker_input),
        type                = "primary",
    )

    st.divider()
    st.caption(
        "**Dados:** CVM Open Data  \n"
        "**LLM:** Gemini 2.5 Flash  \n"
        "**Embeddings:** paraphrase-multilingual-mpnet-base-v2  \n"
        "**Vetores:** ChromaDB (persistente em disco)"
    )


# ── Lógica de execução ────────────────────────────────────────────────────────

cache_key = f"{ticker_input}_{tipo_doc}"

if btn_analisar:
    st.session_state["ultimo_ticker"] = ticker_input
    # Remove resultado anterior de outra empresa se existir
    if st.session_state.get("cache_key") != cache_key:
        st.session_state.pop("resultado", None)

    with st.spinner(""):       # spinner global como fallback visual
        resultado = rodar_pipeline(ticker_input, tipo_doc, forcar)

    st.session_state["resultado"] = resultado
    st.session_state["cache_key"] = cache_key


# ── Exibição dos resultados ───────────────────────────────────────────────────

if "resultado" in st.session_state:
    r = st.session_state["resultado"]

    # Erro
    if r.get("erro"):
        st.error(f"**Erro na análise:** {r['erro']}", icon="❌")
        st.stop()

    analise  = r["analise"]
    dados    = analise["dados_extraidos"]
    secoes   = analise["secoes"]
    periodo  = analise["periodo"]
    empresa  = r["nome_empresa"]
    ticker   = r["ticker"]

    # ── Cabeçalho da empresa ──────────────────────────────────────────────────
    st.markdown(f"# {empresa}")
    col_h1, col_h2, col_h3, col_h4 = st.columns(4)
    col_h1.markdown(f"**Ticker:** `{ticker}`")
    col_h2.markdown(f"**Período:** `{periodo}`")
    col_h3.markdown(f"**Relatório:** `{r['tipo_documento']}`")
    col_h4.markdown(f"**Base:** `{dados.get('base_dados', '—')}`")

    st.divider()

    # ── Métricas em destaque ──────────────────────────────────────────────────
    rec   = dados.get("receita_principal", {})
    lucro = dados.get("lucro_liquido", {})
    divid = dados.get("endividamento", {})
    ebit  = dados.get("ebitda", {})

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)

    def _val(v: str) -> str:
        """Remove cifrão dos valores do JSON (st.metric não renderiza markdown)."""
        return (v or "—").replace("nao_disponivel", "—").replace("R$", "R$")

    with col_m1:
        label_rec = (rec.get("descricao") or "Receita Principal")[:40]
        st.metric(
            label = label_rec,
            value = _val(rec.get("valor_atual", "—")),
            delta = _delta(rec.get("variacao_pct")),
            help  = "Primeiro nível de receita no demonstrativo de resultado",
        )
    with col_m2:
        st.metric(
            label = "Lucro Líquido",
            value = _val(lucro.get("valor_atual", "—")),
            delta = _delta(lucro.get("variacao_pct")),
            help  = "Lucro líquido do período versus período anterior",
        )
    with col_m3:
        st.metric(
            label = "Dívida Líquida",
            value = _val(divid.get("divida_liquida", "—")),
            help  = "Dívida bruta menos caixa e equivalentes de caixa",
        )
    with col_m4:
        st.metric(
            label = "EBITDA",
            value = _val(ebit.get("valor_atual", "—")),
            help  = "Lucro antes de juros, impostos, depreciação e amortização",
        )

    st.divider()

    # ── Resumo executivo (seção de destaque) ──────────────────────────────────
    resumo = _secao("RESUMO", secoes)
    if resumo:
        icone, titulo = SECOES["RESUMO"]
        with st.container(border=True):
            st.subheader(f"{icone} {titulo}")
            st.markdown(_md(resumo))
        st.markdown("")

    # ── Faturamento | Lucro | Caixa (3 colunas) ──────────────────────────────
    col_s1, col_s2, col_s3 = st.columns(3)
    for col, chave in zip(
        [col_s1, col_s2, col_s3],
        ["O QUE A EMPRESA FATURA", "LUCRO", "SAUDE DO CAIXA E DIVIDAS"],
    ):
        icone, titulo = SECOES[chave]
        txt = _secao(chave, secoes)
        with col:
            with st.container(border=True, height=320):
                st.markdown(f"**{icone} {titulo}**")
                st.markdown(_md(txt) if txt else "_Informação não disponível neste relatório._")

    st.markdown("")

    # ── Positivos | Atenção (2 colunas) ──────────────────────────────────────
    col_p, col_a = st.columns(2)

    with col_p:
        icone, titulo = SECOES["O QUE FOI POSITIVO"]
        txt = _secao("O QUE FOI POSITIVO", secoes)
        with st.container(border=True):
            st.markdown(f"**{icone} {titulo}**")
            st.markdown(_md(txt) if txt else "_Não identificados com os dados disponíveis._")

    with col_a:
        icone, titulo = SECOES["O QUE MERECE ATENCAO"]
        txt = _secao("O QUE MERECE ATENCAO", secoes)
        with st.container(border=True):
            st.markdown(f"**{icone} {titulo}**")
            st.markdown(_md(txt) if txt else "_Não identificados com os dados disponíveis._")

    st.markdown("")

    # ── Limitações (expander) ─────────────────────────────────────────────────
    icone, titulo = SECOES["LIMITACOES DESTA ANALISE"]
    txt = _secao("LIMITACOES DESTA ANALISE", secoes)
    with st.expander(f"{icone} {titulo}", expanded=False):
        st.markdown(_md(txt) if txt else "Nenhuma limitação identificada.")

    st.divider()

    # ── Download ──────────────────────────────────────────────────────────────
    pdf_bytes = _gerar_pdf(empresa, ticker, periodo, r["tipo_documento"], secoes)
    nome_arquivo = f"fundia_{ticker}_{periodo}.pdf"
    st.download_button(
        label     = "⬇️  Baixar análise completa (.pdf)",
        data      = pdf_bytes,
        file_name = nome_arquivo,
        mime      = "application/pdf",
        help      = "Exporta a análise gerada pela IA em PDF formatado",
    )

else:
    # ── Tela de boas-vindas ───────────────────────────────────────────────────
    st.markdown("# 📊 fundIA")
    st.markdown("### Análise fundamentalista automatizada via RAG + Inteligência Artificial")
    st.markdown("---")

    col_i1, col_i2 = st.columns([1, 1])

    with col_i1:
        st.markdown("""
**Como funciona:**

1. 📥 **Busca** o relatório ITR/DFP mais recente da empresa na CVM
2. 📄 **Extrai** as demonstrações financeiras (DRE, Balanço, DFC)
3. 🔍 **Indexa** os dados com embeddings multilíngues
4. 🤖 **Recupera** os trechos mais relevantes via RAG
5. 💡 **Gera** uma análise estruturada com Gemini 2.5 Flash

**Digite o ticker e clique em Analisar →**
        """)

    with col_i2:
        st.markdown("""
**Empresas suportadas (amostra):**

| Ticker | Empresa             |
|--------|---------------------|
| WEGE3  | WEG S.A.            |
| ITUB4  | Itaú Unibanco       |
| BBAS3  | Banco do Brasil     |
| PETR4  | Petrobras           |
| VALE3  | Vale S.A.           |
| EMBR3  | Embraer             |

Qualquer empresa listada na B3 com código CVM pode ser analisada.
        """)

    st.markdown("---")
    st.caption(
        "Fonte dos dados: CVM Open Data · "
        "Este sistema não constitui recomendação de investimento."
    )

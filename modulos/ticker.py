# modulos/ticker.py
import io
import os
import re
import time
import zipfile

import pandas as pd
import requests

from config import BASE_URL_CVM

TICKER_MAP_PATH = "dados/ticker_map.csv"

# Todos os códigos CVM verificados contra o índice real de dados abertos da CVM
# (DFP/2025 e ITR/2026). Códigos com discrepância foram corrigidos.
# Tickers não encontrados no índice foram removidos — a busca automática
# (_buscar_no_fca) os resolve pelo cadastro oficial FCA da CVM.
TICKER_MAP_EMBUTIDO = {
    # ── Bancos & Financeiro ───────────────────────────────────────────────────
    "ITUB3": ("19348", "Itaú Unibanco Holding S.A."),
    "ITUB4": ("19348", "Itaú Unibanco Holding S.A."),
    "BBDC3": ("906",   "Banco Bradesco S.A."),
    "BBDC4": ("906",   "Banco Bradesco S.A."),
    "BBAS3": ("1023",  "Banco do Brasil S.A."),
    "SANB3": ("20532", "Banco Santander (Brasil) S.A."),
    "SANB4": ("20532", "Banco Santander (Brasil) S.A."),
    "SANB11":("20532", "Banco Santander (Brasil) S.A."),
    "IRBR3": ("24180", "IRB - Brasil Resseguros S.A."),

    # ── Petróleo & Gás ────────────────────────────────────────────────────────
    "PETR3": ("9512",  "Petróleo Brasileiro S.A. - Petrobras"),
    "PETR4": ("9512",  "Petróleo Brasileiro S.A. - Petrobras"),
    "PRIO3": ("22187", "PRIO S.A."),
    "ENEV3": ("21237", "Eneva S.A."),

    # ── Mineração & Siderurgia ────────────────────────────────────────────────
    "VALE3": ("4170",  "Vale S.A."),
    "GGBR3": ("3980",  "Gerdau S.A."),
    "GGBR4": ("3980",  "Gerdau S.A."),
    "CSNA3": ("4030",  "Companhia Siderúrgica Nacional"),

    # ── Papel & Celulose ──────────────────────────────────────────────────────
    "KLBN3": ("12653", "Klabin S.A."),
    "KLBN4": ("12653", "Klabin S.A."),
    "KLBN11":("12653", "Klabin S.A."),
    "SUZB3": ("13986", "Suzano S.A."),

    # ── Energia Elétrica ──────────────────────────────────────────────────────
    "CMIG3": ("2453",  "Companhia Energética de Minas Gerais - Cemig"),
    "CMIG4": ("2453",  "Companhia Energética de Minas Gerais - Cemig"),
    "CPLE3": ("14311", "Companhia Paranaense de Energia - Copel"),
    "CPLE6": ("14311", "Companhia Paranaense de Energia - Copel"),
    "ENGI3": ("15253", "Energisa S.A."),
    "ENGI4": ("15253", "Energisa S.A."),
    "ENGI11":("15253", "Energisa S.A."),
    "CPFE3": ("18660", "CPFL Energia S.A."),
    "EQTL3": ("20010", "Equatorial Energia S.A."),
    "TAEE3": ("20257", "Transmissora Aliança de Energia Elétrica S.A."),
    "TAEE4": ("20257", "Transmissora Aliança de Energia Elétrica S.A."),
    "TAEE11":("20257", "Transmissora Aliança de Energia Elétrica S.A."),

    # ── Saneamento ────────────────────────────────────────────────────────────
    "SBSP3": ("14443", "Companhia de Saneamento Básico do Estado de São Paulo - Sabesp"),

    # ── Indústria ─────────────────────────────────────────────────────────────
    "WEGE3": ("5410",  "WEG S.A."),
    "WEGE4": ("5410",  "WEG S.A."),
    "EMBR3": ("20087", "Embraer S.A."),
    "POSI3": ("20362", "Positivo Tecnologia S.A."),

    # ── Alimentos & Bebidas ───────────────────────────────────────────────────
    "ABEV3": ("23264", "Ambev S.A."),
    "JBSS3": ("20575", "JBS S.A."),
    "MRFG3": ("20788", "Marfrig Global Foods S.A."),
    "BEEF3": ("20931", "Minerva Foods S.A."),
    "BRFS3": ("16292", "BRF S.A."),

    # ── Saúde ─────────────────────────────────────────────────────────────────
    "HAPV3": ("24392", "Hapvida Participações e Investimentos S.A."),
    "RDOR3": ("24821", "Rede D'Or São Luiz S.A."),
    "RADL3": ("5258",  "Raia Drogasil S.A."),

    # ── Varejo ────────────────────────────────────────────────────────────────
    "MGLU3": ("22470", "Magazine Luiza S.A."),
    "LREN3": ("8133",  "Lojas Renner S.A."),

    # ── Logística & Infraestrutura ────────────────────────────────────────────
    "RENT3": ("19739", "Localiza Rent a Car S.A."),
    "RAIL3": ("17450", "Rumo S.A."),
    "ECOR3": ("19453", "EcoRodovias Infraestrutura e Logística S.A."),

    # ── Telecom ───────────────────────────────────────────────────────────────
    "VIVT3": ("17671", "Telefônica Brasil S.A."),
    "TOTVS3":("19992", "TOTVS S.A."),

    # ── Conglomerados & Outros ────────────────────────────────────────────────
    "CSAN3": ("19836", "Cosan S.A."),
    "UGPA3": ("18465", "Ultrapar Participações S.A."),
    "ITSA3": ("7617",  "Itaúsa S.A."),
    "ITSA4": ("7617",  "Itaúsa S.A."),
    "CYRE3": ("14460", "Cyrela Brazil Realty S.A."),
    "SLCE3": ("20745", "SLC Agrícola S.A."),
    "AGRO3": ("20036", "BrasilAgro - Cia Bras de Prop Agricolas"),

    # ── Aviação ───────────────────────────────────────────────────────────────
    "AZUL4": ("24112", "Azul S.A."),
    "GOLL4": ("19569", "Gol Linhas Aéreas Inteligentes S.A."),
}

def validar_ticker(ticker: str) -> dict:
    """
    Valida o formato do ticker e resolve o código CVM correspondente.

    Returns:
        dict com valido (bool) e, se válido, ticker e codigo_cvm; caso
        contrário, motivo com a mensagem exibida ao usuário. Ticker não
        encontrado falha explicitamente: analisar a empresa errada seria
        pior do que não analisar.
    """
    ticker = ticker.upper().strip()
    # Radical de 4 caracteres (começa com letra, mas pode conter dígito — ex.:
    # B3SA3, da própria B3) + sufixo de 1 ou 2 números.
    if not re.match(r'^[A-Z][A-Z0-9]{3}\d{1,2}$', ticker):
        return {
            "valido": False,
            "motivo": f"Formato inválido: '{ticker}'. Use o código de negociação da B3 "
                      "(4 caracteres + 1 ou 2 números — ex: WEGE3, B3SA3)"
        }
    resultado = buscar_codigo_cvm(ticker)
    if not resultado:
        return {
            "valido": False,
            "motivo": (
                f"Ticker '{ticker}' não encontrado no cadastro oficial da CVM (FCA). "
                "Nenhuma análise foi gerada, para evitar dados de empresa incorreta. "
                "Verifique se o código está correto (ex: PETR4, WEGE3, BBAS3). "
                "Se a CVM estiver temporariamente indisponível, tente novamente em alguns instantes."
            )
        }
    return {"valido": True, "ticker": ticker, "codigo_cvm": resultado[0]}

def buscar_codigo_cvm(ticker: str) -> tuple | None:
    """
    Resolve ticker → (código CVM, nome) em três níveis, do mais barato ao mais caro.

    Mapa embutido, depois o cache local em dados/ticker_map.csv e, por fim, o
    cadastro oficial FCA da CVM. Devolve None se nenhum nível resolver.
    """
    ticker = ticker.upper().strip()

    # 1. Mapeamento embutido
    if ticker in TICKER_MAP_EMBUTIDO:
        return TICKER_MAP_EMBUTIDO[ticker]

    # 2. Mapeamento local salvo pelo usuário
    mapa = _carregar_mapa_local()
    if ticker in mapa:
        return mapa[ticker]

    # 3. Resolução exata pelo cadastro oficial FCA da CVM
    return _buscar_no_fca(ticker)

def buscar_nome_empresa(codigo_cvm: str) -> str:
    """Nome da empresa a partir do código CVM; devolve rótulo genérico se desconhecido."""
    for ticker, (cod, nome) in TICKER_MAP_EMBUTIDO.items():
        if cod == str(codigo_cvm):
            return nome
    mapa = _carregar_mapa_local()
    for ticker, (cod, nome) in mapa.items():
        if cod == str(codigo_cvm):
            return nome
    return f"Empresa CVM {codigo_cvm}"

def salvar_mapa_local(ticker: str, codigo_cvm: str, nome: str):
    """Registra em dados/ticker_map.csv um ticker resolvido pelo FCA, evitando nova consulta."""
    os.makedirs("dados", exist_ok=True)
    mapa = _carregar_mapa_local()
    mapa[ticker.upper()] = (codigo_cvm, nome)
    rows = [{"TICKER": t, "CD_CVM": c, "NOME": n} for t, (c, n) in mapa.items()]
    pd.DataFrame(rows).to_csv(TICKER_MAP_PATH, index=False)
    print(f"[ticker] OK '{ticker}' salvo em {TICKER_MAP_PATH}")

def _carregar_mapa_local() -> dict:
    if not os.path.exists(TICKER_MAP_PATH):
        return {}
    try:
        df = pd.read_csv(TICKER_MAP_PATH, dtype=str)
        return {
            row["TICKER"]: (row["CD_CVM"], row["NOME"])
            for _, row in df.iterrows()
            if pd.notna(row.get("TICKER"))
        }
    except Exception:
        return {}

# ── Resolução exata via FCA (Formulário Cadastral) da CVM ────────────────────
#
# O FCA liga o código de negociação (ticker) ao código CVM de forma oficial:
#   • fca_cia_aberta_valor_mobiliario_{ano}.csv → Codigo_Negociacao + CNPJ_Companhia
#   • fca_cia_aberta_geral_{ano}.csv            → CNPJ_Companhia + Codigo_CVM + nome
# O match é sempre por IGUALDADE (nunca substring). Qualquer ambiguidade ou
# ausência resulta em None — o sistema falha explicitamente, não adivinha.

FCA_CACHE_HORAS = 24

_fca_cache: dict[int, tuple[pd.DataFrame, pd.DataFrame] | None] = {}


def _carregar_fca_ano(ano: int) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """
    Retorna (valor_mobiliario, geral) do FCA de um ano, com cache em memória
    e em disco (mesma estratégia de cvm._carregar_indice_ano).
    """
    if ano in _fca_cache:
        return _fca_cache[ano]

    caminho_vm    = os.path.join("dados", f"fca_valor_mobiliario_{ano}.csv")
    caminho_geral = os.path.join("dados", f"fca_geral_{ano}.csv")

    # Cache em disco válido
    if os.path.exists(caminho_vm) and os.path.exists(caminho_geral):
        idade_h = (time.time() - os.path.getmtime(caminho_vm)) / 3600
        if idade_h < FCA_CACHE_HORAS:
            vm    = pd.read_csv(caminho_vm,    sep=";", encoding="latin-1", dtype=str)
            geral = pd.read_csv(caminho_geral, sep=";", encoding="latin-1", dtype=str)
            _fca_cache[ano] = (vm, geral)
            return vm, geral

    url = f"{BASE_URL_CVM}/FCA/DADOS/fca_cia_aberta_{ano}.zip"
    print(f"[ticker] Baixando cadastro FCA {ano}...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 404:
            print(f"[ticker] FCA {ano} não encontrado (404).")
            _fca_cache[ano] = None
            return None
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            with z.open(f"fca_cia_aberta_valor_mobiliario_{ano}.csv") as f:
                vm = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)
            with z.open(f"fca_cia_aberta_geral_{ano}.csv") as f:
                geral = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)

        os.makedirs("dados", exist_ok=True)
        vm.to_csv(caminho_vm,       sep=";", index=False, encoding="latin-1")
        geral.to_csv(caminho_geral, sep=";", index=False, encoding="latin-1")
        _fca_cache[ano] = (vm, geral)
        print(f"[ticker] OK: FCA {ano} carregado ({len(vm):,} valores mobiliários)")
        return vm, geral

    except Exception as e:
        print(f"[ticker] Erro ao baixar FCA {ano}: {e}")

    # Fallback: cache em disco expirado
    if os.path.exists(caminho_vm) and os.path.exists(caminho_geral):
        print(f"[ticker] Usando cache FCA expirado como fallback ({caminho_vm}).")
        vm    = pd.read_csv(caminho_vm,    sep=";", encoding="latin-1", dtype=str)
        geral = pd.read_csv(caminho_geral, sep=";", encoding="latin-1", dtype=str)
        _fca_cache[ano] = (vm, geral)
        return vm, geral

    return None


def _buscar_no_fca(ticker: str) -> tuple | None:
    """
    Resolve ticker → (código CVM, nome) por igualdade exata no FCA.
    Tenta o ano corrente e o anterior (o FCA do ano vigente fica incompleto
    até meados do ano). Retorna None — sem gravar nada — se o ticker não
    existir no cadastro ou se houver ambiguidade de CNPJ/código CVM.
    """
    from datetime import datetime

    ticker = ticker.upper().strip()
    ano    = datetime.now().year

    for a in (ano, ano - 1):
        dados = _carregar_fca_ano(a)
        if dados is None:
            continue
        vm, geral = dados

        m = vm[vm["Codigo_Negociacao"].astype(str).str.strip().str.upper() == ticker]
        if m.empty:
            continue

        # Prefere registros de negociação ativos (sem Data_Fim_Negociacao)
        fim = m["Data_Fim_Negociacao"].astype(str).str.strip()
        ativos = m[m["Data_Fim_Negociacao"].isna() | fim.isin(["", "nan"])]
        if not ativos.empty:
            m = ativos

        # Restringe à referência mais recente e exige CNPJ único
        if "Data_Referencia" in m.columns:
            m = m[m["Data_Referencia"] == m["Data_Referencia"].max()]
        cnpjs = set(m["CNPJ_Companhia"].astype(str).str.strip())
        if len(cnpjs) != 1:
            print(f"[ticker] '{ticker}' ambíguo no FCA {a} (CNPJs: {cnpjs}) — não resolvido.")
            return None
        cnpj = cnpjs.pop()

        g = geral[geral["CNPJ_Companhia"].astype(str).str.strip() == cnpj]
        g = g[g["Codigo_CVM"].notna()]
        if g.empty:
            continue
        codigos = set(g["Codigo_CVM"].astype(str).str.strip().str.lstrip("0"))
        if len(codigos) != 1:
            print(f"[ticker] CNPJ {cnpj} com códigos CVM conflitantes ({codigos}) — não resolvido.")
            return None

        g    = g[g["Data_Referencia"] == g["Data_Referencia"].max()] if "Data_Referencia" in g.columns else g
        cod  = str(g.iloc[0]["Codigo_CVM"]).strip().lstrip("0")
        nome = str(g.iloc[0]["Nome_Empresarial"]).strip()
        salvar_mapa_local(ticker, cod, nome)
        print(f"[ticker] Resolvido pelo FCA: {ticker} -> {nome} (CVM {cod})")
        return (cod, nome)

    return None

# modulos/cvm.py
#
# Fonte de dados: CVM Open Data (dados.cvm.gov.br)
#
# As URLs /META/ITR_CIA_ABERTA_{ano}.csv estão inativas (404).
# O ZIP correto é /DADOS/itr_cia_aberta_{ano}.zip, que contém:
#   • itr_cia_aberta_{ano}.csv          → índice de documentos (empresa, período, link)
#   • itr_cia_aberta_DRE_con_{ano}.csv  → demonstrações financeiras
#   • itr_cia_aberta_BPA_con_{ano}.csv  → balanço ativo
#   • itr_cia_aberta_BPP_con_{ano}.csv  → balanço passivo
#   • itr_cia_aberta_DFC_MD_con_{ano}.csv → fluxo de caixa
#   • ... demais demonstrações

import requests
import zipfile
import io
import os
import time
import pandas as pd
from datetime import datetime

BASE_DADOS  = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
CACHE_DIR   = "dados"
CACHE_HORAS = 24

# ── Cache em memória (por tipo + ano) ────────────────────────────────────────
# Armazena o índice já extraído para evitar re-download no mesmo processo
_indice_cache: dict[str, pd.DataFrame] = {}


# ── URLs ──────────────────────────────────────────────────────────────────────

def _url_dados_zip(tipo: str, ano: int) -> str:
    """URL do ZIP anual de dados estruturados."""
    return f"{BASE_DADOS}/{tipo}/DADOS/{tipo.lower()}_cia_aberta_{ano}.zip"


def _cache_path_indice(tipo: str, ano: int) -> str:
    """Caminho local do índice de documentos extraído do ZIP."""
    return os.path.join(CACHE_DIR, f"meta_{tipo.lower()}_{ano}.csv")


# ── Carregamento do índice de documentos ─────────────────────────────────────

def _carregar_indice_ano(tipo: str, ano: int) -> pd.DataFrame | None:
    """
    Retorna o DataFrame-índice de documentos para um dado tipo/ano.

    Estratégia de cache (em ordem de prioridade):
      1. Memória (mesmo processo)
      2. Disco (arquivo CSV local com menos de CACHE_HORAS)
      3. Download do ZIP → extrai só o arquivo-índice → salva em disco
      4. Fallback: cache em disco expirado (se o download falhar)
    """
    chave = f"{tipo}_{ano}"

    # 1. Memória
    if chave in _indice_cache:
        return _indice_cache[chave]

    # 2. Disco (cache válido)
    caminho = _cache_path_indice(tipo, ano)
    if os.path.exists(caminho):
        idade_h = (time.time() - os.path.getmtime(caminho)) / 3600
        if idade_h < CACHE_HORAS:
            df = pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str)
            _indice_cache[chave] = df
            return df

    # 3. Download
    url = _url_dados_zip(tipo, ano)
    print(f"[cvm] Baixando índice {tipo} {ano}...")
    try:
        resp = requests.get(url, timeout=120)
        if resp.status_code == 404:
            print(f"[cvm] ZIP {tipo}/{ano} não encontrado (404).")
            return None
        resp.raise_for_status()

        nome_indice = f"{tipo.lower()}_cia_aberta_{ano}.csv"
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            if nome_indice not in z.namelist():
                # Tenta o primeiro CSV disponível como índice
                candidatos = [n for n in z.namelist() if n.endswith(".csv")
                              and "_" not in n.replace(f"{tipo.lower()}_cia_aberta_", "").replace(f"_{ano}.csv", "")]
                if not candidatos:
                    print(f"[cvm] Arquivo-índice não encontrado no ZIP {tipo}/{ano}.")
                    return None
                nome_indice = candidatos[0]
            with z.open(nome_indice) as f:
                df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)

        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(caminho, sep=";", index=False, encoding="latin-1")
        _indice_cache[chave] = df
        print(f"[cvm] OK:{len(df):,} registros no indice {tipo}/{ano}")
        return df

    except Exception as e:
        print(f"[cvm] Erro ao baixar indice {tipo}/{ano}: {e}")

    # 4. Fallback: cache expirado
    if os.path.exists(caminho):
        print(f"[cvm] Usando cache expirado como fallback ({caminho}).")
        df = pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str)
        _indice_cache[chave] = df
        return df

    return None


# ── Busca do documento mais recente ──────────────────────────────────────────

def buscar_documento_mais_recente(codigo_cvm: str, tipo: str = "ITR") -> dict | None:
    """
    Encontra o documento mais recente para a empresa.
    Tenta o ano atual e, se necessário, o anterior.
    Retorna dict com periodo, link, ano, etc.; ou None se não encontrar.
    """
    ano_atual = datetime.now().year
    codigo_norm = str(codigo_cvm).lstrip("0")

    for ano in (ano_atual, ano_atual - 1):
        df = _carregar_indice_ano(tipo, ano)
        if df is None:
            continue

        # Localiza colunas por nome (insensível a case)
        cols = {c.upper(): c for c in df.columns}
        col_cvm  = cols.get("CD_CVM")
        col_ref  = cols.get("DT_REFER")
        col_rec  = cols.get("DT_RECEB")
        col_nome = cols.get("DENOM_CIA")
        col_link = cols.get("LINK_DOC")
        col_id   = cols.get("ID_DOC")
        col_cat  = cols.get("CATEG_DOC")

        if not col_cvm or not col_ref:
            print(f"[cvm] Colunas CD_CVM/DT_REFER ausentes no índice {tipo}/{ano}. "
                  f"Colunas encontradas: {list(df.columns)}")
            continue

        empresa = df[df[col_cvm].astype(str).str.lstrip("0") == codigo_norm]

        # Filtra por categoria de documento quando disponível
        if col_cat:
            empresa = empresa[empresa[col_cat].astype(str).str.upper() == tipo.upper()]

        if empresa.empty:
            continue

        empresa = empresa.sort_values(col_ref, ascending=False)
        doc     = empresa.iloc[0]
        periodo = str(doc[col_ref]).strip()

        return {
            "empresa":      str(doc[col_nome]).strip() if col_nome else "—",
            "periodo":      periodo,
            "data_entrega": str(doc[col_rec]).strip()  if col_rec  else "—",
            # O índice da CVM traz o link em http://, mas o servidor RAD só
            # responde em https:// — normaliza para o download funcionar.
            "link":         str(doc[col_link]).strip().replace("http://", "https://", 1)
                            if col_link else "—",
            "id_doc":       str(doc[col_id]).strip()   if col_id   else "",
            "versao":       "1",
            "ano":          int(periodo[:4]) if len(periodo) >= 4 else ano_atual,
        }

    return None


# ── Seções financeiras que serão extraídas ───────────────────────────────────

SECOES_RELEVANTES = {
    "DRE_con":            "Demonstração de Resultado (Consolidado)",
    "DRE_ind":            "Demonstração de Resultado (Individual)",
    "BPA_con":            "Balanço Patrimonial — Ativo (Consolidado)",
    "BPP_con":            "Balanço Patrimonial — Passivo (Consolidado)",
    # A CVM publica a DFC em dois formatos: método indireto (DFC_MI, usado pela
    # quase totalidade das empresas — é o que traz a linha de depreciação e
    # amortização, insumo do EBITDA) e método direto (DFC_MD). Tenta o MI
    # primeiro; o MD fica como alternativa. Títulos iguais: só um é gravado.
    "DFC_MI_con":         "Demonstração de Fluxo de Caixa (Consolidado)",
    "DFC_MD_con":         "Demonstração de Fluxo de Caixa (Consolidado)",
    "composicao_capital": "Composição do Capital Social",
}


# ── Download e formatação dos dados financeiros ───────────────────────────────

def baixar_documento(link: str, destino: str,
                     codigo_cvm: str = "", tipo: str = "ITR",
                     periodo: str = "", ano: int = 0) -> str:
    """
    Baixa os demonstrativos financeiros estruturados do ZIP de dados da CVM
    e grava um arquivo .txt formatado para o pipeline de RAG.

    Tenta o ano do documento e, em caso de 404, o ano anterior.
    Lança RuntimeError se nenhuma fonte produzir dados para a empresa.
    """
    if not codigo_cvm:
        raise ValueError("codigo_cvm é obrigatório para baixar_documento")
    if not ano:
        ano = int(periodo[:4]) if periodo else datetime.now().year

    codigo_norm   = str(codigo_cvm).lstrip("0")
    periodo_curto = periodo[:7] if periodo else ""   # ex: "2026-03"

    # Tenta baixar o ZIP do ano do documento, depois o anterior
    conteudo_zip: bytes | None = None
    ano_usado: int | None = None

    for a in (ano, ano - 1):
        url = _url_dados_zip(tipo, a)
        print(f"[cvm] Baixando dados estruturados {tipo} {a}...")
        try:
            resp = requests.get(url, timeout=120)
            if resp.status_code == 404:
                print(f"[cvm] ZIP {a} não disponível (404) — tentando {a - 1}...")
                continue
            resp.raise_for_status()
            conteudo_zip = resp.content
            ano_usado    = a
            print(f"[cvm] OK:ZIP {tipo}/{a} baixado ({len(conteudo_zip) / 1024:.0f} KB)")
            break
        except requests.HTTPError as e:
            print(f"[cvm] HTTP {e.response.status_code} para {tipo}/{a}")
        except Exception as e:
            print(f"[cvm] Erro ao baixar ZIP {tipo}/{a}: {e}")

    if conteudo_zip is None or ano_usado is None:
        raise RuntimeError(
            f"Dados estruturados {tipo} indisponíveis para {ano} e {ano - 1}. "
            "Verifique a conectividade ou tente novamente mais tarde."
        )

    secoes_texto = [
        f"DOCUMENTO: {tipo} — {periodo}",
        f"EMPRESA CVM: {codigo_cvm}",
        "",
    ]

    secoes_gravadas: set[str] = set()

    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        arquivos_zip = set(z.namelist())
        for sufixo, nome_secao in SECOES_RELEVANTES.items():
            if nome_secao in secoes_gravadas:
                continue
            # Nome canônico do CSV dentro do ZIP
            nome_csv = f"{tipo.lower()}_cia_aberta_{sufixo}_{ano_usado}.csv"
            if nome_csv not in arquivos_zip:
                # Busca por correspondência parcial do sufixo
                candidatos = sorted(
                    n for n in arquivos_zip
                    if sufixo.lower() in n.lower() and n.endswith(".csv")
                )
                if not candidatos:
                    continue
                nome_csv = candidatos[0]

            try:
                with z.open(nome_csv) as f:
                    df = pd.read_csv(f, sep=";", encoding="latin-1", dtype=str)
            except Exception as e:
                print(f"[cvm] Erro ao ler {nome_csv}: {e}")
                continue

            col_cvm_df = next((c for c in df.columns if "CD_CVM" in c.upper()), None)
            if not col_cvm_df:
                continue

            empresa_df = df[df[col_cvm_df].astype(str).str.lstrip("0") == codigo_norm]
            if empresa_df.empty:
                continue

            # Restringe ao período do documento quando possível
            col_ref = next((c for c in df.columns if "DT_REFER" in c.upper()), None)
            if col_ref and periodo_curto:
                filtrado = empresa_df[
                    empresa_df[col_ref].astype(str).str.startswith(periodo_curto)
                ]
                if not filtrado.empty:
                    empresa_df = filtrado

            secoes_texto.append(f"\n{'='*50}")
            secoes_texto.append(nome_secao)
            secoes_texto.append("=" * 50)
            secoes_texto.append(_formatar_df_financeiro(empresa_df))
            secoes_gravadas.add(nome_secao)

    if len(secoes_texto) <= 3:
        raise RuntimeError(
            f"Nenhum dado estruturado encontrado para CVM {codigo_cvm} "
            f"no período '{periodo}'. "
            "Verifique se o código CVM está correto e se a empresa entregou ITR nesse período."
        )

    # Garante extensão .txt (o destino pode vir como .pdf em fluxos legados)
    destino_final = (destino if destino.endswith(".txt")
                     else os.path.splitext(destino)[0] + ".txt")
    os.makedirs(os.path.dirname(os.path.abspath(destino_final)), exist_ok=True)

    with open(destino_final, "w", encoding="utf-8") as f:
        f.write("\n".join(secoes_texto))

    tamanho = os.path.getsize(destino_final) / 1024
    print(f"[cvm] Documento salvo: {destino_final} ({tamanho:.0f} KB)")
    return destino_final


# ── Formatação dos dados financeiros ─────────────────────────────────────────

def _formatar_df_financeiro(df: pd.DataFrame) -> str:
    """
    Formata as linhas do demonstrativo financeiro em texto legível.
    Exibe valor atual e, quando disponível, o valor do período anterior.
    """
    col_conta  = next((c for c in df.columns if "DS_CONTA"     in c.upper()), None)
    col_valor  = next((c for c in df.columns if "VL_CONTA"     in c.upper()), None)
    col_ordem  = next((c for c in df.columns if "ORDEM_EXERC"  in c.upper()), None)
    col_codigo = next((c for c in df.columns if "CD_CONTA"     in c.upper()), None)
    col_ini    = next((c for c in df.columns if "DT_INI_EXERC" in c.upper()), None)

    if not col_conta or not col_valor:
        return df.to_string(index=False, max_rows=50)

    # A chave é o CÓDIGO da conta: contas distintas repetem o mesmo nome (ex:
    # "Empréstimos e Financiamentos" no circulante e no não circulante) e,
    # indexando por nome, uma sobrescreveria a outra.
    col_chave = col_codigo or col_conta

    # No ITR de 2º/3º trimestre, a DRE e a DFC trazem DUAS linhas ÚLTIMO por
    # conta: o ACUMULADO do ano (DT_INI_EXERC = 01/01) e o TRIMESTRE ISOLADO
    # (DT_INI_EXERC = início do trimestre). Sem tratar isso, as duas duplicam e
    # a escolha do valor fica ao acaso da ordem do CSV — podendo até misturar
    # receita acumulada com lucro trimestral. Mantemos sempre o ACUMULADO (a
    # menor DT_INI_EXERC por conta), que é a base da análise fundamentalista e
    # a mesma do valor "anterior". A ordem original das linhas é preservada
    # (não fazemos sort), porque metricas.py rastreia blocos pela ordem. Os
    # balanços não têm DT_INI_EXERC (são posições pontuais) e passam intactos.
    def _manter_acumulado(sub: pd.DataFrame) -> pd.DataFrame:
        if col_ini is None or sub.empty:
            return sub
        ini     = sub[col_ini].astype(str)
        ini_min = ini.groupby(sub[col_chave]).transform("min")
        return sub[ini.eq(ini_min)].drop_duplicates(subset=[col_chave], keep="first")

    if col_ordem:
        # "LTIM" aparece em ÚLTIMO e em PENÚLTIMO; é preciso excluir o segundo
        # explicitamente para não duplicar as linhas no contexto.
        ordem_str   = df[col_ordem].astype(str).str.upper()
        mask_penult = ordem_str.str.contains("PEN.LTIM|PENULT", na=False, regex=True)
        mask_atual  = ordem_str.str.contains("LTIM", na=False) & ~mask_penult
        atual    = _manter_acumulado(df[mask_atual])
        anterior = _manter_acumulado(df[mask_penult])
    else:
        atual    = _manter_acumulado(df)
        anterior = pd.DataFrame()

    map_anterior: dict[str, str] = {}
    if not anterior.empty:
        for _, row in anterior.iterrows():
            map_anterior[str(row[col_chave])] = str(row[col_valor])

    linhas = []
    for _, row in atual.iterrows():
        conta = str(row[col_conta])
        valor = str(row[col_valor])
        var   = map_anterior.get(str(row[col_chave]), "")
        linhas.append(
            f"{conta:<55} {valor:>20}  (anterior: {var})" if var
            else f"{conta:<55} {valor:>20}"
        )
    return "\n".join(linhas)

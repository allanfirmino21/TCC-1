# modulos/metricas.py
#
# Melhoria 1 — Cálculo determinístico de métricas financeiras
#
# Antes, o Prompt 1 pedia ao LLM que extraísse valores e calculasse variações
# e margens — sujeito a erros de aritmética e arredondamento em cascata
# (ex.: margem 15,94% quando a exata era 15,99%). Este módulo substitui essa
# etapa: lê as seções estruturadas do documento da CVM (formato fixo,
# 100% parseável) e calcula tudo em Python. O LLM passa a receber os valores
# prontos e atua apenas como redator da narrativa (Prompt 2).
#
# O JSON produzido mantém o mesmo formato do Prompt 1, então as interfaces
# (React, Streamlit, PDF) e o Prompt 2 continuam funcionando sem alteração.

import re
from typing import List, Optional

# Linha das tabelas da CVM: "Nome da conta   VALOR  (anterior: VALOR)".
# Separador com \s+ (não \s{2,}): nomes de conta com mais de 55 caracteres
# estouram o padding do cvm.py e sobra um único espaço antes do valor.
_RE_LINHA = re.compile(
    r"^(.*?)\s+(-?\d+(?:\.\d+)?)\s+\(anterior:\s*(-?\d+(?:\.\d+)?)\)\s*$"
)

_RE_PERIODO = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ── Formatação (mesmo padrão canônico da normalização do Prompt 1) ───────────

def formatar_moeda(valor_mil: Optional[float]) -> str:
    """Formata um valor em R$ mil para o padrão canônico do sistema."""
    if valor_mil is None:
        return "nao_disponivel"
    negativo = valor_mil < 0
    milhoes = abs(valor_mil) / 1000.0
    if milhoes >= 1_000_000:
        s = "R$ " + f"{milhoes / 1_000_000:.2f}".replace(".", ",") + " trilhões"
    elif milhoes >= 1000:
        s = "R$ " + f"{milhoes / 1000:.2f}".replace(".", ",") + " bilhões"
    elif milhoes >= 1:
        s = "R$ " + f"{milhoes:.2f}".replace(".", ",") + " milhões"
    else:
        s = "R$ " + f"{abs(valor_mil):.0f}" + " mil"
    return ("-" + s) if negativo else s


def formatar_pct(pct: Optional[float], casas: int = 1) -> str:
    if pct is None:
        return "nao_disponivel"
    return f"{pct:+.{casas}f}%".replace(".", ",")


def variacao_pct(atual: Optional[float], anterior: Optional[float]) -> Optional[float]:
    """Variação percentual ((atual − anterior) / |anterior|) × 100."""
    if atual is None or anterior is None or anterior == 0:
        return None
    return (atual - anterior) / abs(anterior) * 100


def interpretar_variacao_lucro(atual: float, anterior: float) -> str:
    """
    Descreve a variação do lucro em linguagem correta mesmo com base negativa —
    "cair 150%" partindo de um prejuízo confunde o leitor; "prejuízo 2,5 vezes
    maior" não.
    """
    if anterior == 0:
        return "sem base de comparação no período anterior"
    if anterior > 0 and atual >= 0:
        pct = variacao_pct(atual, anterior)
        verbo = "cresceu" if pct >= 0 else "caiu"
        return f"o lucro {verbo} {abs(pct):.1f}%".replace(".", ",")
    if anterior < 0 and atual < 0:
        razao = atual / anterior
        if razao > 1:
            return f"o prejuízo ficou {razao:.1f} vezes maior".replace(".", ",")
        pct = (1 - razao) * 100
        return f"o prejuízo diminuiu {pct:.1f}%".replace(".", ",")
    if anterior < 0 <= atual:
        return "passou de prejuízo para lucro"
    return "passou de lucro para prejuízo"


# ── Rótulos dos períodos de comparação (Melhoria 3) ───────────────────────────
#
# Nos dados estruturados da CVM, a coluna "anterior" (ORDEM_EXERC = PENÚLTIMO)
# tem bases de comparação DIFERENTES por demonstração:
#   • ITR / DRE (receita, lucro)      → mesmo período do ano anterior
#   • ITR / Balanço (caixa, dívidas)  → fechamento do exercício anterior (31/12)
#   • DFP                             → exercício anterior, em ambas
# Rotular isso explicitamente evita o "período anterior" genérico na narrativa.

# No ITR, a DRE e a DFC ACUMULAM o resultado desde o início do ano (não é o
# trimestre isolado): 3 meses no 1º ITR, 6 no 2º, 9 no 3º. O rótulo tem que
# refletir o período acumulado — chamar o acumulado de 9 meses de "3º
# trimestre" seria enganoso. (O balanço é sempre pontual, na data de referência.)
_PERIODO_ITR = {
    3:  "1º trimestre",
    6:  "1º semestre (6 meses acumulados)",
    9:  "9 meses acumulados (janeiro a setembro)",
    12: "exercício completo (12 meses)",
}


def rotular_periodos(periodo: str, tipo_doc: str) -> dict:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", periodo or "")
    if not m:
        return {
            "periodo_atual":        "nao_disponivel",
            "comparacao_resultado": "período anterior",
            "comparacao_balanco":   "período anterior",
        }
    ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if tipo_doc.upper() == "DFP":
        return {
            "periodo_atual":        f"exercício de {ano} (encerrado em 31/12/{ano})",
            "comparacao_resultado": f"exercício de {ano - 1}",
            "comparacao_balanco":   f"31/12/{ano - 1} (fechamento do exercício anterior)",
            "nota": "No relatório anual (DFP), receita, lucro e balanço comparam "
                    "com o exercício anterior.",
        }

    rotulo = _PERIODO_ITR.get(mes)
    if rotulo:
        periodo_atual        = f"{rotulo} de {ano}, encerrado em {dia:02d}/{mes:02d}/{ano}"
        comparacao_resultado = f"{rotulo} de {ano - 1} (mesmo período do ano anterior)"
    else:
        periodo_atual        = f"período acumulado encerrado em {dia:02d}/{mes:02d}/{ano}"
        comparacao_resultado = f"mesmo período acumulado de {ano - 1}"
    return {
        "periodo_atual":        periodo_atual,
        "comparacao_resultado": comparacao_resultado,
        "comparacao_balanco":   f"31/12/{ano - 1} (fechamento do exercício anterior)",
        "nota": "No ITR, receita e lucro são acumulados desde o início do ano e "
                "comparam com o mesmo período acumulado do ano anterior; caixa, "
                "dívidas e demais contas do balanço são posições na data de "
                "referência e comparam com o fechamento do exercício anterior (31/12).",
    }


# ── Parsing das seções ────────────────────────────────────────────────────────

def _parsear_linhas(conteudo: str) -> list:
    """Extrai [(nome, atual, anterior)] das linhas de uma seção, na ordem."""
    linhas = []
    for linha in conteudo.split("\n"):
        m = _RE_LINHA.match(linha.strip())
        if m:
            nome = m.group(1).strip()
            linhas.append((nome, float(m.group(2)), float(m.group(3))))
    return linhas


def _primeira(linhas: list, *nomes: str):
    """Primeira ocorrência (atual, anterior) de qualquer um dos nomes exatos."""
    for alvo in nomes:
        for nome, atual, anterior in linhas:
            if nome == alvo:
                return atual, anterior
    return None, None


def _achar_secao(secoes: List, prefixo: str, base: str):
    for s in secoes:
        if s.titulo.startswith(prefixo) and s.base == base:
            return s
    return None


def _emprestimos_por_bloco(linhas: list) -> tuple:
    """
    No balanço passivo, "Empréstimos e Financiamentos" aparece dentro do
    Passivo Circulante e do Não Circulante. Percorre as linhas rastreando o
    bloco atual e captura a primeira ocorrência em cada um.
    Retorna ((circ_atual, circ_ant), (ncirc_atual, ncirc_ant)).
    """
    bloco = None
    circ = ncirc = (None, None)
    for nome, atual, anterior in linhas:
        if nome == "Passivo Circulante":
            bloco = "circ"
        elif nome == "Passivo Não Circulante":
            bloco = "ncirc"
        elif nome == "Empréstimos e Financiamentos":
            if bloco == "circ" and circ == (None, None):
                circ = (atual, anterior)
            elif bloco == "ncirc" and ncirc == (None, None):
                ncirc = (atual, anterior)
    return circ, ncirc


_RE_ARRENDAMENTO = re.compile(r"arrendament", re.IGNORECASE)


def _somar_arrendamentos(linhas: list) -> tuple:
    """
    Soma os passivos de arrendamento (IFRS 16) do balanço passivo — circulante
    e não circulante. Os nomes variam por empresa ("Obrigações com
    arrendamento", "Passivos de arrendamento(s)"...), por isso a busca é por
    radical. A linha padrão "Financiamento por Arrendamento" é EXCLUÍDA: ela é
    filha de "Empréstimos e Financiamentos" e, quando não zerada, já está
    contida na dívida bruta (somá-la seria dupla contagem).
    """
    total_a = total_ant = 0.0
    achou = False
    for nome, atual, anterior in linhas:
        if _RE_ARRENDAMENTO.search(nome) and nome != "Financiamento por Arrendamento":
            total_a   += atual
            total_ant += anterior
            if atual != 0 or anterior != 0:
                achou = True
    return (total_a, total_ant) if achou else (None, None)


def _aplicacoes_circulante(linhas: list) -> tuple:
    """
    Primeira linha "Aplicações Financeiras" dentro do Ativo Circulante —
    investimentos de curto prazo que funcionam como quase-caixa.
    """
    bloco = None
    for nome, atual, anterior in linhas:
        if nome == "Ativo Circulante":
            bloco = "circ"
        elif nome == "Ativo Não Circulante":
            bloco = "ncirc"
        elif nome == "Aplicações Financeiras" and bloco == "circ":
            return atual, anterior
    return None, None


_RE_DEP_AMORT = re.compile(r"deprecia|amortiza", re.IGNORECASE)
# "Amortização de Empréstimos/Debêntures/passivos de arrendamento" é pagamento
# de dívida (atividade de financiamento), não despesa de D&A — homônimos que
# não podem entrar na soma.
_RE_NAO_EH_DA = re.compile(r"empr[ée]stimo|financiament|deb[êe]ntur|passivo",
                           re.IGNORECASE)


def _somar_depreciacao_amortizacao(linhas: list) -> tuple:
    """
    Soma as linhas de depreciação/amortização/exaustão da DFC pelo método
    indireto — os ajustes que recompõem despesas sem efeito caixa sobre o
    lucro. Os nomes variam por empresa ("Depreciações e amortizações",
    "Depreciação, amortização e exaustão", "Amortização de arrendamentos"...),
    por isso a busca é por radical, com três guardas:
    - só o bloco operacional (os ajustes de D&A vivem antes de "Caixa Líquido
      Atividades de Investimento/Financiamento");
    - exclusão por nome dos homônimos de pagamento de dívida;
    - ajustes de D&A são sempre positivos — valores negativos são desembolsos.
    """
    total_a = total_ant = 0.0
    achou = False
    for nome, atual, anterior in linhas:
        if nome.startswith("Caixa Líquido Atividades de Investimento") or \
           nome.startswith("Caixa Líquido Atividades de Financiamento"):
            break
        if not _RE_DEP_AMORT.search(nome) or _RE_NAO_EH_DA.search(nome):
            continue
        if atual < 0 or anterior < 0:
            continue
        total_a   += atual
        total_ant += anterior
        if atual != 0 or anterior != 0:
            achou = True
    return (total_a, total_ant) if achou else (None, None)


# ── Cálculo principal ─────────────────────────────────────────────────────────

def calcular_metricas(secoes: List) -> dict:
    """
    Recebe as seções extraídas do documento (SecaoDocumento) e devolve o dict
    de métricas no mesmo formato do Prompt 1 — porém calculado em Python.

    Lança ValueError se o documento não tiver dados parseáveis suficientes
    (permite ao orquestrador cair no caminho legado via LLM).
    """
    # Período de referência e tipo: cabeçalho "DOCUMENTO: ITR — AAAA-MM-DD"
    periodo, tipo_doc = "nao_disponivel", "ITR"
    for s in secoes:
        if s.titulo == "Cabeçalho":
            m = _RE_PERIODO.search(s.conteudo)
            if m:
                periodo = m.group(1)
            m_tipo = re.search(r"DOCUMENTO:\s*([A-Z]+)", s.conteudo)
            if m_tipo:
                tipo_doc = m_tipo.group(1)
    periodos = rotular_periodos(periodo, tipo_doc)

    # DRE: preferir Consolidado; cair para Individual
    dre = _achar_secao(secoes, "Demonstração de Resultado", "Consolidado")
    base_dados = "Consolidado"
    if dre is None:
        dre = _achar_secao(secoes, "Demonstração de Resultado", "Individual")
        base_dados = "Individual"
    if dre is None:
        raise ValueError("Documento sem Demonstração de Resultado parseável.")
    dre_l = _parsear_linhas(dre.conteudo)

    ativo   = _achar_secao(secoes, "Balanço Patrimonial — Ativo", base_dados)
    passivo = _achar_secao(secoes, "Balanço Patrimonial — Passivo", base_dados)
    dfc     = _achar_secao(secoes, "Demonstração de Fluxo de Caixa", base_dados)
    ativo_l   = _parsear_linhas(ativo.conteudo) if ativo else []
    passivo_l = _parsear_linhas(passivo.conteudo) if passivo else []
    dfc_l     = _parsear_linhas(dfc.conteudo) if dfc else []

    # ── DRE ──
    desc_receita = "Receita de Venda de Bens e/ou Serviços"
    rec_a, rec_ant = _primeira(dre_l, desc_receita)
    if rec_a is None:
        # Bancos e financeiras
        for alt in ("Receitas de Intermediação Financeira",
                    "Receitas da Intermediação Financeira"):
            rec_a, rec_ant = _primeira(dre_l, alt)
            if rec_a is not None:
                desc_receita = alt
                break

    # Receita zerada (comum em holdings e seguradoras que não usam essa linha)
    # é tratada como indisponível — exibir "R$ 0" seria enganoso.
    if rec_a == 0 and rec_ant == 0:
        rec_a = rec_ant = None

    luc_a, luc_ant = _primeira(
        dre_l,
        "Lucro/Prejuízo Consolidado do Período",
        "Lucro ou Prejuízo Líquido Consolidado do Período",   # bancos
        "Lucro/Prejuízo do Período",
        "Resultado Líquido das Operações Continuadas",
        "Lucro ou Prejuízo das Operações Continuadas",        # bancos
    )
    if rec_a is None and luc_a is None:
        raise ValueError("Não foi possível identificar receita nem lucro no documento.")

    bruto_a, bruto_ant = _primeira(dre_l, "Resultado Bruto")
    ebit_a,  ebit_ant  = _primeira(dre_l, "Resultado Antes do Resultado Financeiro e dos Tributos")
    equiv_a, _         = _primeira(dre_l, "Resultado de Equivalência Patrimonial")
    ctrl_a,  _         = _primeira(dre_l, "Atribuído a Sócios da Empresa Controladora")
    minor_a, _         = _primeira(dre_l, "Atribuído a Sócios Não Controladores")

    # ── Balanço ──
    caixa_a, caixa_ant = _primeira(ativo_l, "Caixa e Equivalentes de Caixa")
    atv_a,   atv_ant   = _primeira(ativo_l, "Ativo Total")
    pl_a,    pl_ant    = _primeira(passivo_l, "Patrimônio Líquido Consolidado",
                                   "Patrimônio Líquido")
    (ec_a, ec_ant), (enc_a, enc_ant) = _emprestimos_por_bloco(passivo_l)

    arr_a,   arr_ant   = _somar_arrendamentos(passivo_l)
    aplic_a, aplic_ant = _aplicacoes_circulante(ativo_l)

    # ── Detecção de instituição financeira ──
    # Bancos usam plano de contas próprio na CVM: não existe "Empréstimos e
    # Financiamentos" nem circulante/não circulante no passivo — o funding vem
    # de Depósitos e Captação no Mercado Aberto. Para eles, dívida líquida não
    # é um indicador aplicável (captar recursos É o negócio bancário).
    dep_a,  dep_ant  = _primeira(passivo_l, "Depósitos")
    capt_a, capt_ant = _primeira(passivo_l, "Captação no Mercado Aberto")
    eh_banco = ("Intermediação Financeira" in desc_receita) or bool(dep_a)

    # ── EBITDA aproximado = EBIT (DRE) + depreciação e amortização (DFC) ──
    # A CVM não publica EBITDA como conta; a aproximação clássica recompõe o
    # D&A (que está na DFC pelo método indireto) sobre o resultado operacional.
    da_a, da_ant = _somar_depreciacao_amortizacao(dfc_l)
    ebitda_a = ebitda_ant = None
    if not eh_banco and ebit_a is not None and da_a is not None:
        ebitda_a = ebit_a + da_a
        if ebit_ant is not None and da_ant is not None:
            ebitda_ant = ebit_ant + da_ant

    div_a = div_ant = None
    if ec_a is not None or enc_a is not None:
        div_a   = (ec_a or 0) + (enc_a or 0)
        div_ant = (ec_ant or 0) + (enc_ant or 0)

    # Liquidez total = caixa e equivalentes + aplicações financeiras de curto
    # prazo (quase-caixa). Se não houver linha de aplicações, usa só o caixa.
    liq_a = liq_ant = None
    if caixa_a is not None:
        liq_a = caixa_a + (aplic_a or 0)
        if caixa_ant is not None:
            liq_ant = caixa_ant + (aplic_ant or 0)

    # Dívida líquida (critério principal) = empréstimos − liquidez total.
    # Visão ampliada (IFRS 16) = (empréstimos + arrendamentos) − liquidez total.
    divliq_a = divliq_ant = None
    divliq_arr_a = None
    if div_a is not None and liq_a is not None:
        divliq_a = div_a - liq_a
        if liq_ant is not None:
            divliq_ant = div_ant - liq_ant
        if arr_a is not None:
            divliq_arr_a = div_a + arr_a - liq_a

    # ── Montagem do JSON (formato compatível com o antigo Prompt 1) ──
    dados_ausentes = ([] if eh_banco or ebitda_a is not None
                      else ["ebitda.valor_atual", "ebitda.margem_pct"])
    advertencias, destaques = [], []

    # EBITDA — aproximado quando DRE e DFC permitem; nao_aplicavel para bancos
    if eh_banco:
        ebitda_json = {
            "valor_atual": "nao_aplicavel",
            "margem_pct":  "nao_aplicavel",
            "nota": "EBITDA não é um indicador usado para instituições financeiras: "
                    "o resultado de um banco vem da intermediação financeira (juros "
                    "e captação), não de uma operação industrial ou comercial.",
        }
    elif ebitda_a is not None:
        ebitda_json = {
            "valor_atual":    formatar_moeda(ebitda_a),
            "valor_anterior": formatar_moeda(ebitda_ant),
            "variacao_pct":   formatar_pct(variacao_pct(ebitda_a, ebitda_ant)),
            "comparacao":     periodos["comparacao_resultado"],
            "criterio": "EBITDA aproximado = resultado antes do resultado financeiro "
                        "e dos tributos (DRE) + depreciação e amortização (DFC). A CVM "
                        "não publica o EBITDA nos dados estruturados; esta aproximação "
                        "pode diferir do valor divulgado pela empresa.",
        }
        if rec_a:
            margem_e = ebitda_a / rec_a * 100
            if abs(margem_e) <= 100:
                ebitda_json["margem_pct"] = f"{margem_e:.2f}%".replace(".", ",")
        ebitda_json.setdefault("margem_pct", "nao_disponivel")
    else:
        ebitda_json = {
            "valor_atual": "nao_disponivel",
            "margem_pct":  "nao_disponivel",
            "nota": "Não foi possível aproximar o EBITDA: o documento não traz "
                    "demonstração de fluxo de caixa parseável (linha de depreciação "
                    "e amortização) ou resultado operacional.",
        }

    # Receita
    receita = {
        "descricao":      desc_receita,
        "valor_atual":    formatar_moeda(rec_a),
        "valor_anterior": formatar_moeda(rec_ant),
        "variacao_pct":   formatar_pct(variacao_pct(rec_a, rec_ant)),
        "comparacao":     periodos["comparacao_resultado"],
    }
    if rec_a is None:
        dados_ausentes.append("receita_principal")

    # Lucro — com margem exata e interpretação correta de base negativa
    lucro = {
        "valor_atual":    formatar_moeda(luc_a),
        "valor_anterior": formatar_moeda(luc_ant),
        "variacao_pct":   formatar_pct(variacao_pct(luc_a, luc_ant)),
        "comparacao":     periodos["comparacao_resultado"],
    }
    if luc_a is not None and luc_ant is not None:
        lucro["interpretacao_variacao"] = interpretar_variacao_lucro(luc_a, luc_ant)
    if luc_a is not None and rec_a:
        margem = luc_a / rec_a * 100
        if abs(margem) > 100:
            # Lucro maior que a receita: típico de holdings, cujo resultado vem
            # de participações (equivalência patrimonial). A margem perde o
            # sentido usual — omitir em vez de confundir o leitor.
            advertencias.append(
                "O lucro é maior que a receita principal — comum em holdings, "
                "cujo resultado vem de participações em outras empresas "
                "(equivalência patrimonial). A margem sobre a receita não é "
                "um indicador útil neste caso."
            )
        else:
            lucro["margem_liquida_pct"] = f"{margem:.2f}%".replace(".", ",")
            por_100 = f"{abs(margem):.2f}".replace(".", ",")
            lucro["contexto_por_100_reais"] = (
                f"a cada R$ 100 de receita, sobraram R$ {por_100} de lucro"
                if margem >= 0 else
                f"a cada R$ 100 de receita, houve perda de R$ {por_100}"
            )
    if luc_a is None:
        dados_ausentes.append("lucro_liquido")
    elif luc_a < 0:
        advertencias.append(
            f"A empresa registrou prejuízo de {formatar_moeda(abs(luc_a))} no período."
        )
        if luc_ant is not None and luc_ant < 0:
            advertencias.append(
                f"Comparação com o período anterior: {lucro['interpretacao_variacao']}."
            )

    # Endividamento — critérios explícitos (Melhoria 4)
    if eh_banco:
        # Instituição financeira: dívida líquida marcada como NÃO APLICÁVEL
        # (não como dado faltante) e indicadores de funding no lugar.
        endividamento = {
            "criterio": "Instituição financeira: dívida líquida e liquidez total "
                        "não são indicadores usados para bancos — captar recursos "
                        "(depósitos, mercado aberto) é parte da operação bancária. "
                        "Indicadores de referência: depósitos de clientes e "
                        "captação no mercado aberto.",
            "divida_bruta":         "nao_aplicavel",
            "divida_liquida":       "nao_aplicavel",
            "caixa_e_equivalentes": formatar_moeda(caixa_a),
            "caixa_anterior":       formatar_moeda(caixa_ant),
            "variacao_caixa_pct":   formatar_pct(variacao_pct(caixa_a, caixa_ant)),
            "depositos":            formatar_moeda(dep_a),
            "depositos_anterior":   formatar_moeda(dep_ant),
            "variacao_depositos_pct": formatar_pct(variacao_pct(dep_a, dep_ant)),
            "captacao_mercado_aberto": formatar_moeda(capt_a),
            "comparacao":           periodos["comparacao_balanco"],
            "nota": "Dívida líquida não se aplica a bancos. A análise de solidez "
                    "de um banco usa outros indicadores (ex.: índice de Basileia, "
                    "inadimplência), que não constam nos dados estruturados da CVM.",
        }
        if dep_a is not None:
            destaques.append(
                f"Depósitos de clientes: {formatar_moeda(dep_a)} "
                f"(variação {formatar_pct(variacao_pct(dep_a, dep_ant))})"
            )
        if capt_a is not None:
            destaques.append(
                f"Captação no mercado aberto: {formatar_moeda(capt_a)} "
                f"(variação {formatar_pct(variacao_pct(capt_a, capt_ant))})"
            )
    else:
        endividamento = {
            "criterio": "Dívida bruta = empréstimos e financiamentos (circulante + não "
                        "circulante). Liquidez total = caixa e equivalentes + aplicações "
                        "financeiras de curto prazo. Dívida líquida = dívida bruta − "
                        "liquidez total. Passivos de arrendamento (IFRS 16, aluguéis "
                        "contratados) são informados separadamente na visão ampliada.",
            "divida_bruta":         formatar_moeda(div_a),
            "divida_bruta_anterior": formatar_moeda(div_ant),
            "variacao_divida_pct":  formatar_pct(variacao_pct(div_a, div_ant)),
            "caixa_e_equivalentes": formatar_moeda(caixa_a),
            "caixa_anterior":       formatar_moeda(caixa_ant),
            "variacao_caixa_pct":   formatar_pct(variacao_pct(caixa_a, caixa_ant)),
            "aplicacoes_financeiras": formatar_moeda(aplic_a),
            "liquidez_total":       formatar_moeda(liq_a),
            "divida_liquida":       formatar_moeda(divliq_a),
            "divida_liquida_anterior": formatar_moeda(divliq_ant),
            "comparacao":           periodos["comparacao_balanco"],
        }
        if arr_a is not None:
            endividamento["passivos_arrendamento"] = formatar_moeda(arr_a)
            endividamento["divida_bruta_com_arrendamentos"] = formatar_moeda((div_a or 0) + arr_a)
            if divliq_arr_a is not None:
                endividamento["divida_liquida_com_arrendamentos"] = formatar_moeda(divliq_arr_a)
            # Arrendamento relevante (>10% da dívida bruta): destacar para o leitor
            if div_a and arr_a / div_a > 0.10:
                destaques.append(
                    f"Além dos empréstimos ({formatar_moeda(div_a)}), a empresa tem "
                    f"{formatar_moeda(arr_a)} em passivos de arrendamento (aluguéis "
                    f"contratados, IFRS 16) — incluindo-os, a dívida total é "
                    f"{formatar_moeda((div_a or 0) + arr_a)}."
                )
        if divliq_a is not None and divliq_a < 0:
            endividamento["nota"] = (
                "A dívida líquida é negativa: a empresa tem mais caixa e aplicações "
                "do que dívida (posição de caixa líquido)."
            )
        if div_a is None:
            dados_ausentes.append("endividamento.divida_bruta")
    vc = variacao_pct(caixa_a, caixa_ant)
    if vc is not None and vc < -20:
        advertencias.append(
            f"O caixa e equivalentes caiu {formatar_pct(vc)} "
            f"(de {formatar_moeda(caixa_ant)} para {formatar_moeda(caixa_a)})."
        )

    # Outros destaques e advertências por regra
    if pl_a is not None:
        destaques.append(
            f"Patrimônio Líquido: {formatar_moeda(pl_a)} "
            f"(variação {formatar_pct(variacao_pct(pl_a, pl_ant))})"
        )
    if atv_a is not None:
        destaques.append(
            f"Ativo Total: {formatar_moeda(atv_a)} "
            f"(variação {formatar_pct(variacao_pct(atv_a, atv_ant))})"
        )
        va = variacao_pct(atv_a, atv_ant)
        if va is not None and va < 0:
            advertencias.append(
                f"O Ativo Total diminuiu {formatar_pct(va)} no período."
            )
    if bruto_a is not None:
        destaques.append(f"Resultado Bruto: {formatar_moeda(bruto_a)}")
    if ebit_a is not None:
        if ebit_ant is not None and (ebit_a < 0) != (ebit_ant < 0):
            transicao = ("passou de lucro para prejuízo" if ebit_a < 0
                         else "passou de prejuízo para lucro")
            destaques.append(
                f"Resultado operacional (antes de juros e impostos): {transicao} — "
                f"de {formatar_moeda(ebit_ant)} para {formatar_moeda(ebit_a)}"
            )
            if ebit_a < 0:
                advertencias.append(
                    "O resultado operacional (antes de juros e impostos) passou de "
                    "lucro para prejuízo."
                )
        else:
            destaques.append(
                f"Resultado operacional (antes de juros e impostos): {formatar_moeda(ebit_a)} "
                f"(variação {formatar_pct(variacao_pct(ebit_a, ebit_ant))})"
            )
    if equiv_a:
        destaques.append(f"Resultado de Equivalência Patrimonial: {formatar_moeda(equiv_a)}")
    if ctrl_a is not None and luc_a is not None and ctrl_a != luc_a:
        destaques.append(
            f"Lucro atribuído a sócios da controladora: {formatar_moeda(ctrl_a)}"
        )
    if minor_a is not None and luc_a is not None and minor_a < 0 < luc_a:
        advertencias.append(
            f"O lucro atribuído a sócios não controladores é negativo "
            f"({formatar_moeda(minor_a)}), enquanto o resultado consolidado é positivo."
        )
    vr = variacao_pct(rec_a, rec_ant)
    if vr is not None and vr < 0:
        advertencias.append(f"A receita principal caiu {formatar_pct(vr)} no período.")

    return {
        "periodo_referencia": periodo,
        "periodos":           periodos,
        "base_dados":         base_dados,
        "escala_original":    "R$ milhares (mil reais)",
        "metodo_calculo":     "deterministico_python",
        "receita_principal":  receita,
        "lucro_liquido":      lucro,
        "ebitda":             ebitda_json,
        "endividamento":      endividamento,
        "outros_destaques": destaques,
        "dados_ausentes":   dados_ausentes,
        "advertencias":     advertencias,
    }

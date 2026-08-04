# modulos/auditoria.py
#
# Melhoria 2 — Auditoria automática de fidelidade numérica
#
# Verifica, após a geração da narrativa, se cada número citado pelo LLM
# existe de fato na fonte: o documento estruturado da CVM ou as métricas
# calculadas deterministicamente (modulos/metricas.py). Produz a métrica
# "taxa de conformidade numérica", complementar ao RAGAS: enquanto o RAGAS
# mede consistência semântica, esta auditoria mede exatidão aritmética.
#
# Cada verificação registra a PROVENIÊNCIA do fato usado na comparação
# (linha do documento CVM com valor bruto, ou métrica calculada), para que
# qualquer pessoa possa conferir a fonte por conta própria — o selo mostra
# o trabalho, não só a conclusão.
#
# Vereditos por número citado:
#   CONFERE        — bate com um fato da fonte, com sinal e direção compatíveis
#   DIVERGENTE     — próximo de um fato mas fora da tolerância, com sinal
#                    trocado, com direção do verbo invertida, ou percentual que
#                    só existe como derivação do documento (provável cálculo
#                    próprio do LLM)
#   NAO_ENCONTRADO — não corresponde a nenhum fato: possível alucinação
#   IGNORADO       — recurso didático ("a cada R$ 100..."), não conta na taxa
#
# Endurecimentos após verificação independente (falsos CONFERE detectados):
#   1. Sinal: "lucrou R$ 1,47 mi" quando o fato é −1,47 não passa mais.
#   2. Tolerância de percentuais: só a base curada (métricas calculadas) dá
#      CONFERE; match apenas com variações deriváveis do documento → DIVERGENTE.
#   3. Direção: o verbo (cresceu/caiu) deve bater com o sinal da variação;
#      "prejuízo aumentou X%" inverte a polaridade.

import re
from typing import List

from modulos.metricas import formatar_moeda, variacao_pct

# ── Regex de tokens numéricos na narrativa ────────────────────────────────────

# "R$ 1,10 trilhões" | "R$ 1,66 bilhões" | "-R$ 108,86 milhoes" | "R$ 523 mil"
_RE_MOEDA = re.compile(
    r"(-\s*)?R\$\s*([\d.]+(?:,\d+)?)\s*"
    r"(trilh(?:ão|ao|ões|oes)|bilh(?:ão|ao|ões|oes)|milh(?:ão|ao|ões|oes)|mil)\b",
    re.IGNORECASE,
)
# "R$ 15,99" sem unidade (contexto "a cada R$ 100...")
_RE_REAIS = re.compile(r"-?\s*R\$\s*([\d.]+(?:,\d+)?)(?!\s*(?:trilh|bilh|milh|mil))",
                       re.IGNORECASE)
# "8,9%" | "+17,0%" | "-1,3%"
_RE_PCT = re.compile(r"([+\-]?)\s*(\d+(?:,\d+)?)\s*%")
# "2,5 vezes"
_RE_RAZAO = re.compile(r"(\d+(?:,\d+)?)\s*vez(?:es)?\b", re.IGNORECASE)

# Separador nome→valor com \s+ (não \s{2,}): nomes de conta com mais de 55
# caracteres estouram o padding do cvm.py e sobra um único espaço. O âncora
# "(anterior: ...)" no fim da linha evita ambiguidade.
_RE_LINHA_DOC = re.compile(
    r"^(.*?)\s+(-?\d+(?:\.\d+)?)\s+\(anterior:\s*(-?\d+(?:\.\d+)?)\)\s*$"
)


def _num_br(texto: str) -> float:
    """'1.655,24' → 1655.24"""
    return float(texto.replace(".", "").replace(",", "."))


def _fmt_mil(v: float) -> str:
    """1655238.0 → '1.655.238' (para exibir o valor bruto da fonte)."""
    return f"{v:,.0f}".replace(",", ".")


def _moeda_para_mil(valor: float, unidade: str) -> float:
    u = unidade.lower()
    if u.startswith("trilh"):
        return valor * 1_000_000_000
    if u.startswith("bilh"):
        return valor * 1_000_000
    if u.startswith("milh"):
        return valor * 1_000
    return valor  # mil


# ── Sinal e direção reivindicados pelo texto ──────────────────────────────────

_MARCA_NEG = ("prejuízo", "prejuizo", "perda", "perdeu", "negativo", "negativa")
_MARCA_POS = ("lucro", "lucrou", "ganho", "ganhou", "sobraram", "sobrou")

_VERBO_POS = ("cresceu", "crescimento", "subiu", "aumentou", "aumento", "alta",
              "avançou", "avancou", "elevou", "elevação", "elevacao", "elevando")
_VERBO_NEG = ("caiu", "queda", "diminuiu", "diminuição", "diminuicao", "recuou",
              "reduziu", "redução", "reducao", "baixa", "retração", "retracao")

# Substantivos que invertem a polaridade do verbo: "o prejuízo aumentou 150%"
# descreve uma variação NEGATIVA do resultado.
_POLARIDADE_NEG = ("prejuízo", "prejuizo", "perda")


def _mais_proximo_no_trecho(trecho: str, palavras: tuple) -> int:
    """Posição da última ocorrência de qualquer palavra no trecho (-1 se nenhuma)."""
    return max((trecho.rfind(p) for p in palavras), default=-1)


def _sinal_contexto(texto: str, inicio: int, janela: int = 45) -> int:
    """
    Sinal reivindicado pelo texto para um valor monetário: -1, +1 ou 0 (neutro).
    Decide pelo marcador mais próximo antes do valor.
    "variação negativa/positiva" descreve o percentual (auditado à parte),
    não o sinal da moeda — é neutralizado antes da busca por marcadores.
    """
    trecho = texto[max(0, inicio - janela):inicio].lower()
    trecho = re.sub(r"varia[çc][ãa]o\s+(negativ|positiv)\w*", " ", trecho)
    pos_neg = _mais_proximo_no_trecho(trecho, _MARCA_NEG)
    pos_pos = _mais_proximo_no_trecho(trecho, _MARCA_POS)
    if pos_neg < 0 and pos_pos < 0:
        return 0
    return -1 if pos_neg > pos_pos else +1


def _direcao_contexto(texto: str, inicio: int, janela: int = 60) -> int:
    """
    Direção reivindicada pelo verbo antes de um percentual: -1, +1 ou 0.
    "prejuízo"/"perda" na janela invertem a polaridade do verbo.
    """
    trecho = texto[max(0, inicio - janela):inicio].lower()
    pos_neg = _mais_proximo_no_trecho(trecho, _VERBO_NEG)
    pos_pos = _mais_proximo_no_trecho(trecho, _VERBO_POS)
    if pos_neg < 0 and pos_pos < 0:
        return 0
    direcao = -1 if pos_neg > pos_pos else +1
    if _mais_proximo_no_trecho(trecho, _POLARIDADE_NEG) >= 0:
        direcao = -direcao
    return direcao


# ── Base de fatos: (valor com sinal, origem legível) ──────────────────────────

def _fatos_do_documento(secoes_doc: List) -> tuple:
    """
    Valores (em R$ mil) e variações % deriváveis de cada linha do documento,
    cada um acompanhado da origem: nome da conta e valor bruto, para que o
    leitor possa localizar a linha no documento da CVM.
    Retorna (moedas, pcts) como listas de (valor, origem).
    """
    moedas, pcts = [], []
    for s in secoes_doc:
        for linha in s.conteudo.split("\n"):
            m = _RE_LINHA_DOC.match(linha.strip())
            if not m:
                continue
            nome = m.group(1).strip()
            atual, anterior = float(m.group(2)), float(m.group(3))
            if atual != 0:
                moedas.append((atual, f'documento CVM: "{nome}" = {_fmt_mil(atual)} (R$ mil)'))
            if anterior != 0:
                moedas.append((anterior,
                               f'documento CVM: "{nome}" (anterior) = {_fmt_mil(anterior)} (R$ mil)'))
            var = variacao_pct(atual, anterior)
            if var is not None:
                pcts.append((round(var, 1),
                             f'variação derivável de "{nome}" ({var:+.1f}%)'.replace(".", ",")))
    return moedas, pcts


def _fatos_dos_dados(dados: dict) -> tuple:
    """
    Valores presentes nas métricas calculadas (strings formatadas), com a
    origem apontando o campo do JSON de métricas de onde vieram.
    Retorna (moedas, pcts, razoes, reais) como listas de (valor, origem).
    """
    moedas, pcts, razoes, reais = [], [], [], []

    def _varrer(obj, caminho):
        if isinstance(obj, str):
            origem = f"métrica calculada: {caminho}" if caminho else "métrica calculada"
            for m in _RE_MOEDA.finditer(obj):
                v = _moeda_para_mil(_num_br(m.group(2)), m.group(3))
                moedas.append((-v if m.group(1) else v, origem))
            sem_moeda = _RE_MOEDA.sub(" ", obj)
            for m in _RE_REAIS.finditer(sem_moeda):
                reais.append((_num_br(m.group(1)), origem))
            for m in _RE_PCT.finditer(obj):
                v = _num_br(m.group(2))
                pcts.append((-v if m.group(1) == "-" else v, origem))
            for m in _RE_RAZAO.finditer(obj):
                razoes.append((_num_br(m.group(1)), origem))
        elif isinstance(obj, list):
            for x in obj:
                _varrer(x, caminho)
        elif isinstance(obj, dict):
            for k, x in obj.items():
                _varrer(x, f"{caminho}.{k}" if caminho else k)

    _varrer(dados, "")
    return moedas, pcts, razoes, reais


# ── Comparação com tolerância, sinal e direção ────────────────────────────────

def _compativel(sinal_reivindicado: int, fato: float) -> bool:
    if sinal_reivindicado == 0:
        return True
    return fato >= 0 if sinal_reivindicado > 0 else fato < 0


def _match_moeda(valor_mil: float, sinal: int, fatos: list) -> tuple:
    """
    Compara magnitude (tolerância relativa/arredondamento canônico) exigindo
    sinal compatível para CONFERE.
    Retorna (veredito, motivo, fato_valor, origem).
    """
    def _bate(v, f, rel):
        return rel <= 0.005 or formatar_moeda(abs(v)) == formatar_moeda(abs(f))

    melhor = melhor_ok = None            # (valor, origem)
    rel_melhor = rel_ok = float("inf")
    for f, origem in fatos:
        rel = abs(abs(valor_mil) - abs(f)) / max(abs(f), 1.0)
        if rel < rel_melhor:
            melhor, rel_melhor = (f, origem), rel
        if _compativel(sinal, f) and rel < rel_ok:
            melhor_ok, rel_ok = (f, origem), rel

    if melhor_ok is not None and _bate(valor_mil, melhor_ok[0], rel_ok):
        return "CONFERE", None, melhor_ok[0], melhor_ok[1]
    if melhor is not None and _bate(valor_mil, melhor[0], rel_melhor):
        return "DIVERGENTE", "sinal incompatível com o fato", melhor[0], melhor[1]
    if melhor is not None and rel_melhor <= 0.02:
        return "DIVERGENTE", "valor próximo, provável arredondamento incorreto", melhor[0], melhor[1]
    return "NAO_ENCONTRADO", None, (melhor[0] if melhor else None), (melhor[1] if melhor else None)


def _match_pct(valor: float, direcao: int, fatos_dados: list, fatos_doc: list) -> tuple:
    """
    Percentuais: só a base curada (métricas calculadas) dá CONFERE, e a direção
    do verbo precisa ser compatível com o sinal do fato.
    Retorna (veredito, motivo, fato_valor, origem).
    """
    def _melhor_abs(fatos):
        melhor, menor = None, float("inf")
        for f, origem in fatos:
            d = abs(valor - abs(f))
            if d < menor:
                melhor, menor = (f, origem), d
        return melhor, menor

    # 1. Base curada (métricas calculadas)
    candidatos = [(f, o) for f, o in fatos_dados if abs(valor - abs(f)) <= 0.06]
    if candidatos:
        compativeis = [(f, o) for f, o in candidatos if _compativel(direcao, f)]
        if compativeis:
            f, o = compativeis[0]
            return "CONFERE", None, f, o
        f, o = candidatos[0]
        return "DIVERGENTE", "direção do verbo incompatível com o sinal da variação", f, o

    # 2. Só bate com variação derivável do documento
    fato_doc, dif_doc = _melhor_abs(fatos_doc)
    if fato_doc is not None and dif_doc <= 0.06:
        return ("DIVERGENTE",
                "não consta nas métricas calculadas; coincide apenas com variação "
                "derivável do documento", fato_doc[0], fato_doc[1])

    # 3. Próximo de algo, mas errado
    fato_dd, dif_dd = _melhor_abs(fatos_dados)
    if fato_dd is not None and (fato_doc is None or dif_dd <= dif_doc):
        fato_prox, dif_prox = fato_dd, dif_dd
    else:
        fato_prox, dif_prox = fato_doc, dif_doc
    if fato_prox is not None and dif_prox <= 0.55:
        return "DIVERGENTE", "valor próximo, provável arredondamento incorreto", fato_prox[0], fato_prox[1]
    return "NAO_ENCONTRADO", None, (fato_prox[0] if fato_prox else None), (fato_prox[1] if fato_prox else None)


# ── Auditoria principal ───────────────────────────────────────────────────────

def auditar_narrativa(secoes_narrativa: dict, secoes_doc: List, dados: dict) -> dict:
    """
    Confere cada número citado nas seções da narrativa contra a base de fatos.
    Retorna {"verificacoes": [...], "resumo": {...}}. Cada verificação carrega
    a origem do fato usado (linha do documento CVM ou métrica calculada).
    """
    doc_moedas, doc_pcts = _fatos_do_documento(secoes_doc)
    dd_moedas, dd_pcts, dd_razoes, dd_reais = _fatos_dos_dados(dados)
    fatos_moedas = doc_moedas + dd_moedas

    verificacoes = []

    def _registrar(secao, trecho, tipo, veredito, motivo, fato_fmt, origem):
        v = {
            "secao":   secao,
            "trecho":  trecho,
            "tipo":    tipo,
            "veredito": veredito,
            "fato_mais_proximo": fato_fmt,
            "origem_fato": origem,
        }
        if motivo:
            v["motivo"] = motivo
        verificacoes.append(v)

    for nome_secao, texto in (secoes_narrativa or {}).items():
        if not texto:
            continue

        # 1. Moedas com unidade — magnitude + sinal reivindicado
        for m in _RE_MOEDA.finditer(texto):
            valor_mil = _moeda_para_mil(_num_br(m.group(2)), m.group(3))
            sinal = -1 if m.group(1) else _sinal_contexto(texto, m.start())
            veredito, motivo, fato, origem = _match_moeda(valor_mil, sinal, fatos_moedas)
            _registrar(nome_secao, m.group(0).strip(), "moeda", veredito, motivo,
                       formatar_moeda(fato) if fato is not None else None, origem)

        # 2. Valores "R$ X" sem unidade — contexto didático por R$ 100
        sem_moeda = _RE_MOEDA.sub(" ", texto)
        for m in _RE_REAIS.finditer(sem_moeda):
            valor = _num_br(m.group(1))
            if valor == 100:               # "a cada R$ 100..." — recurso didático
                _registrar(nome_secao, m.group(0).strip(), "reais", "IGNORADO", None,
                           None, "recurso didático (não conta na taxa)")
                continue
            fato, origem, dif = None, None, float("inf")
            for f, o in dd_reais:
                d = abs(valor - f)
                if d < dif:
                    fato, origem, dif = f, o, d
            if fato is not None and dif <= 0.011:
                _registrar(nome_secao, m.group(0).strip(), "reais", "CONFERE", None,
                           f"R$ {fato}".replace(".", ","), origem)
                continue
            # Fallback: o LLM pode ter copiado um valor bruto do documento (que
            # está em R$ mil) sem converter a escala — ex.: "R$ 113.787" quando
            # a linha da CVM diz 113787 (= R$ 113,79 milhões).
            fato_mil, origem_mil, rel_mil = None, None, float("inf")
            for f, o in fatos_moedas:
                rel = abs(valor - abs(f)) / max(abs(f), 1.0)
                if rel < rel_mil:
                    fato_mil, origem_mil, rel_mil = f, o, rel
            if fato_mil is not None and rel_mil <= 0.005:
                _registrar(nome_secao, m.group(0).strip(), "reais", "DIVERGENTE",
                           "valor em R$ mil citado sem conversão de escala",
                           formatar_moeda(fato_mil), origem_mil)
            else:
                _registrar(nome_secao, m.group(0).strip(), "reais", "NAO_ENCONTRADO", None,
                           f"R$ {fato}".replace(".", ",") if fato is not None else None, origem)

        # 3. Percentuais — base curada + direção do verbo
        for m in _RE_PCT.finditer(texto):
            valor = _num_br(m.group(2))
            if m.group(1):                          # sinal explícito no texto
                direcao = -1 if m.group(1) == "-" else +1
            else:
                direcao = _direcao_contexto(texto, m.start())
            veredito, motivo, fato, origem = _match_pct(valor, direcao, dd_pcts, doc_pcts)
            _registrar(nome_secao, m.group(0).strip(), "percentual", veredito, motivo,
                       f"{fato}%".replace(".", ",") if fato is not None else None, origem)

        # 4. Razões ("2,5 vezes")
        for m in _RE_RAZAO.finditer(texto):
            valor = _num_br(m.group(1))
            fato, origem, dif = None, None, float("inf")
            for f, o in dd_razoes:
                d = abs(valor - f)
                if d < dif:
                    fato, origem, dif = f, o, d
            veredito = "CONFERE" if fato is not None and dif <= 0.06 else "NAO_ENCONTRADO"
            _registrar(nome_secao, m.group(0).strip(), "razao", veredito, None,
                       f"{fato} vezes".replace(".", ",") if fato is not None else None, origem)

    # ── Resumo ──
    contadas = [v for v in verificacoes if v["veredito"] != "IGNORADO"]
    conferem = sum(1 for v in contadas if v["veredito"] == "CONFERE")
    resumo = {
        "total_numeros":     len(contadas),
        "conferem":          conferem,
        "divergentes":       sum(1 for v in contadas if v["veredito"] == "DIVERGENTE"),
        "nao_encontrados":   sum(1 for v in contadas if v["veredito"] == "NAO_ENCONTRADO"),
        "taxa_conformidade": round(conferem / len(contadas) * 100, 1) if contadas else None,
        "escopo": "Verifica valores monetários, percentuais e razões citados no texto, "
                  "com sinal e direção. Não verifica afirmações qualitativas nem números "
                  "por extenso.",
    }
    return {"verificacoes": verificacoes, "resumo": resumo}

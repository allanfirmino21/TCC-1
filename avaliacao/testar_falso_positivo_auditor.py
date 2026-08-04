# testar_falso_positivo_auditor.py
#
# Teste estatístico de falso-positivo do auditor de fidelidade numérica
# (modulos/auditoria.py), com varredura de sementes.
#
# Autocontido: base de fatos fixa (documento sintético + métricas calculadas
# de exemplo), sem CVM e sem LLM. Não altera nenhum módulo do sistema — apenas
# importa e exercita o auditor.
#
# O que mede:
#   1. FALSO-POSITIVO — para cada semente de 0 a 19, gera 20 percentuais e
#      20 valores monetários aleatórios que NÃO estão na base de fatos e conta
#      quantos o auditor carimba como CONFERE (deveria ser nenhum). Reporta
#      média, mínimo e máximo entre as sementes.
#   2. CONTROLE DE SENSIBILIDADE — confere que números LEGÍTIMOS (presentes na
#      base) continuam recebendo CONFERE, para garantir que a tolerância não
#      ficou rígida demais.
#
# Definição de "não está na base":
#   - percentual: o valor (1 casa decimal) difere de todos os percentuais
#     curados (métricas calculadas) e de todas as variações deriváveis do
#     documento — igualdade seria numericamente indistinguível de um acerto;
#   - moeda: a forma canônica ("R$ X,XX milhões/bilhões", via formatar_moeda)
#     difere da forma canônica de todos os fatos — mesmo critério.
#   O que sobra de CONFERE é coincidência acidental genuína (valor aleatório
#   que caiu dentro da tolerância de um fato sem ser igual a ele).
#
# Densidade: documentos reais do cache têm ~280-300 linhas de valores
# (POMO4: 277, WEGE3: 305, ZAMP3: 298). A base sintética usa 30 linhas
# realistas + 250 linhas sintéticas determinísticas (semente fixa própria,
# independente das sementes de teste), totalizando densidade equivalente.
#
# Observação de projeto: percentuais que só existem como variação derivável do
# documento recebem DIVERGENTE por decisão do endurecimento do auditor (não é
# falso-positivo nem rigidez indevida) — por isso o controle de sensibilidade
# usa apenas fatos da base curada.
#
# Uso:  python testar_falso_positivo_auditor.py

import random
import statistics
from types import SimpleNamespace

from modulos.auditoria import (auditar_narrativa, _fatos_do_documento,
                               _fatos_dos_dados)
from modulos.metricas import formatar_moeda

N_SEMENTES     = 20
N_POR_SEMENTE  = 20
SEMENTE_BASE   = 20260715   # fixa — só para gerar a base sintética
N_SINTETICAS   = 250

# ── Base de fatos fixa ─────────────────────────────────────────────────────────
# Núcleo realista: DRE + balanço + DFC consistentes entre si (valores em R$ mil,
# formato de linha idêntico ao do cache: "Nome  VALOR  (anterior: VALOR)").

_DRE = """\
Receita de Venda de Bens e/ou Serviços   9468313.00  (anterior: 10078571.00)
Custo dos Bens e/ou Serviços Vendidos   -6392145.00  (anterior: -6805442.00)
Resultado Bruto   3076168.00  (anterior: 3273129.00)
Despesas/Receitas Operacionais   -1240310.00  (anterior: -1305226.00)
Resultado Antes do Resultado Financeiro e dos Tributos   1835858.00  (anterior: 1967903.00)
Resultado Financeiro   145210.00  (anterior: 98462.00)
Resultado Antes dos Tributos sobre o Lucro   1981068.00  (anterior: 2066365.00)
Imposto de Renda e Contribuição Social   -401367.00  (anterior: -486664.00)
Lucro/Prejuízo Consolidado do Período   1579701.00  (anterior: 1447230.00)
Atribuído a Sócios da Empresa Controladora   1551200.00  (anterior: 1420110.00)
Atribuído a Sócios Não Controladores   28501.00  (anterior: 27120.00)
"""

_ATIVO = """\
Ativo Total   45123456.00  (anterior: 43987654.00)
Ativo Circulante   24567890.00  (anterior: 23456789.00)
Caixa e Equivalentes de Caixa   4321987.00  (anterior: 5123456.00)
Aplicações Financeiras   2876543.00  (anterior: 2345678.00)
Contas a Receber   7654321.00  (anterior: 7123456.00)
Estoques   6543210.00  (anterior: 6234567.00)
Ativo Não Circulante   20555566.00  (anterior: 20530865.00)
Imobilizado   9876543.00  (anterior: 9765432.00)
Intangível   3210987.00  (anterior: 3198765.00)
"""

_PASSIVO = """\
Passivo Total   45123456.00  (anterior: 43987654.00)
Passivo Circulante   12345678.00  (anterior: 12234567.00)
Empréstimos e Financiamentos   3456789.00  (anterior: 3654321.00)
Fornecedores   4123456.00  (anterior: 3987654.00)
Passivo Não Circulante   10790124.00  (anterior: 10876544.00)
Empréstimos e Financiamentos   2345678.00  (anterior: 2456789.00)
Patrimônio Líquido Consolidado   21987654.00  (anterior: 20876543.00)
"""

_DFC = """\
Depreciação, Amortização e Exaustão   312456.00  (anterior: 289765.00)
Caixa Líquido Atividades Operacionais   1876543.00  (anterior: 1654321.00)
Caixa Líquido Atividades de Investimento   -987654.00  (anterior: -876543.00)
Caixa Líquido Atividades de Financiamento   -1690370.00  (anterior: -543211.00)
Aumento (Redução) de Caixa e Equivalentes   -801481.00  (anterior: 234567.00)
"""

# Métricas calculadas de exemplo (base curada), consistentes com o documento
# acima e no formato exato de metricas.py.
DADOS = {
    "periodo_referencia": "2026-03-31",
    "base_dados": "Consolidado",
    "receita_principal": {
        "valor_atual":    "R$ 9,47 bilhões",
        "valor_anterior": "R$ 10,08 bilhões",
        "variacao_pct":   "-6,1%",
    },
    "lucro_liquido": {
        "valor_atual":    "R$ 1,58 bilhões",
        "valor_anterior": "R$ 1,45 bilhões",
        "variacao_pct":   "+9,2%",
        "margem_liquida_pct": "16,68%",
    },
    "ebitda": {
        "valor_atual":    "R$ 2,15 bilhões",
        "valor_anterior": "R$ 2,26 bilhões",
        "variacao_pct":   "-4,8%",
        "margem_pct":     "22,69%",
    },
    "endividamento": {
        "divida_bruta":         "R$ 5,80 bilhões",
        "caixa_e_equivalentes": "R$ 4,32 bilhões",
        "aplicacoes_financeiras": "R$ 2,88 bilhões",
        "liquidez_total":       "R$ 7,20 bilhões",
        "divida_liquida":       "-R$ 1,40 bilhões",
        "nota": "a liquidez total equivale a 1,2 vezes a dívida bruta",
    },
    "patrimonio_liquido": {
        "valor_atual":  "R$ 21,99 bilhões",
        "variacao_pct": "+5,3%",
    },
}


def montar_secoes():
    """Núcleo realista + linhas sintéticas determinísticas até a densidade real."""
    rng = random.Random(SEMENTE_BASE)
    linhas = []
    for i in range(1, N_SINTETICAS + 1):
        atual = 10 ** rng.uniform(2.0, 7.7)          # R$ 100 mil a ~R$ 50 bi
        if rng.random() < 0.3:
            atual = -atual
        anterior = atual * rng.uniform(0.7, 1.3)
        linhas.append(f"Conta Sintética {i:03d}   {atual:.2f}  (anterior: {anterior:.2f})")
    return [
        SimpleNamespace(titulo="Demonstração de Resultado",       conteudo=_DRE),
        SimpleNamespace(titulo="Balanço Patrimonial — Ativo",     conteudo=_ATIVO),
        SimpleNamespace(titulo="Balanço Patrimonial — Passivo",   conteudo=_PASSIVO),
        SimpleNamespace(titulo="Demonstração de Fluxo de Caixa",  conteudo=_DFC),
        SimpleNamespace(titulo="Notas Sintéticas",                conteudo="\n".join(linhas)),
    ]


SECOES_DOC = montar_secoes()


def montar_exclusoes():
    """Conjuntos de valores que 'estão na base', na resolução do auditor."""
    doc_moedas, doc_pcts = _fatos_do_documento(SECOES_DOC)
    dd_moedas, dd_pcts, _razoes, _reais = _fatos_dos_dados(DADOS)
    moedas_canonicas = {formatar_moeda(abs(f)) for f, _ in doc_moedas + dd_moedas}
    pcts_1dec        = {round(abs(f), 1) for f, _ in doc_pcts + dd_pcts}
    return moedas_canonicas, pcts_1dec, len(doc_moedas) + len(dd_moedas), len(dd_pcts), len(doc_pcts)


def auditar_texto(texto: str, tipo: str) -> list:
    """Roda o auditor sobre um texto e devolve só as verificações do tipo dado."""
    res = auditar_narrativa({"TESTE": texto}, SECOES_DOC, DADOS)
    return [v for v in res["verificacoes"] if v["tipo"] == tipo]


# ── 1. Controle de sensibilidade: números legítimos devem dar CONFERE ─────────

FRASES_LEGITIMAS = (
    "A receita líquida somou R$ 9,47 bilhões no trimestre. "
    "No período anterior, a receita havia sido de R$ 10,08 bilhões. "
    "Em relação ao mesmo trimestre do ano anterior, a receita caiu 6,1%. "
    "O lucro líquido cresceu 9,2%, somando R$ 1,58 bilhões. "
    "A margem líquida ficou em 16,68%. "
    "O resultado bruto foi de R$ 3,08 bilhões. "
    "A dívida líquida ficou negativa em R$ 1,40 bilhões. "
    "A liquidez total equivale a 1,2 vezes a dívida bruta."
)
# 5 moedas + 3 percentuais + 1 razão = 9 números, todos presentes na base.
LEGITIMOS_ESPERADOS = 9


def testar_legitimos() -> tuple:
    res = auditar_narrativa({"TESTE": FRASES_LEGITIMAS}, SECOES_DOC, DADOS)
    checks = [v for v in res["verificacoes"] if v["veredito"] != "IGNORADO"]
    conferem = [v for v in checks if v["veredito"] == "CONFERE"]
    falhas   = [v for v in checks if v["veredito"] != "CONFERE"]
    return len(conferem), len(checks), falhas


# ── 2. Falso-positivo com varredura de sementes ───────────────────────────────

def gerar_pcts_fora_da_base(rng: random.Random, pcts_excl: set) -> list:
    valores = []
    while len(valores) < N_POR_SEMENTE:
        v = round(rng.uniform(0.1, 120.0), 1)
        if v == 0.0 or v in pcts_excl:
            continue
        valores.append(v)
    return valores


def gerar_moedas_fora_da_base(rng: random.Random, moedas_excl: set) -> list:
    valores = []
    while len(valores) < N_POR_SEMENTE:
        v_mil = 10 ** rng.uniform(2.0, 7.7)          # mesma faixa dos fatos
        canonico = formatar_moeda(v_mil)
        if canonico in moedas_excl:
            continue
        valores.append(canonico)
    return valores


def rodar_semente(semente: int, moedas_excl: set, pcts_excl: set) -> dict:
    rng = random.Random(semente)

    pcts = gerar_pcts_fora_da_base(rng, pcts_excl)
    texto_pct = " ".join(
        f"O indicador apurado ficou em {str(v).replace('.', ',')}%." for v in pcts
    )
    checks_pct = auditar_texto(texto_pct, "percentual")
    assert len(checks_pct) == N_POR_SEMENTE, f"esperava {N_POR_SEMENTE} percentuais, achei {len(checks_pct)}"

    moedas = gerar_moedas_fora_da_base(rng, moedas_excl)
    texto_moeda = " ".join(f"O montante registrado foi de {m}." for m in moedas)
    checks_moeda = auditar_texto(texto_moeda, "moeda")
    assert len(checks_moeda) == N_POR_SEMENTE, f"esperava {N_POR_SEMENTE} moedas, achei {len(checks_moeda)}"

    def _contar(checks):
        return {
            "CONFERE":        sum(1 for c in checks if c["veredito"] == "CONFERE"),
            "DIVERGENTE":     sum(1 for c in checks if c["veredito"] == "DIVERGENTE"),
            "NAO_ENCONTRADO": sum(1 for c in checks if c["veredito"] == "NAO_ENCONTRADO"),
        }

    return {"pct": _contar(checks_pct), "moeda": _contar(checks_moeda)}


def resumir(fps: list) -> str:
    total = sum(fps)
    n     = len(fps) * N_POR_SEMENTE
    return (f"media {statistics.mean(fps):.2f}/{N_POR_SEMENTE} por semente "
            f"(min {min(fps)}, max {max(fps)}) - "
            f"total {total}/{n} = {total / n * 100:.1f}%")


def main():
    moedas_excl, pcts_excl, n_moedas, n_pcts_curados, n_pcts_doc = montar_exclusoes()
    n_linhas = sum(1 for s in SECOES_DOC for l in s.conteudo.split("\n") if "(anterior:" in l)

    print("=" * 74)
    print("TESTE DE FALSO-POSITIVO DO AUDITOR - varredura de sementes")
    print("=" * 74)
    print(f"Base de fatos fixa: {n_linhas} linhas de valores "
          f"(documentos reais: ~280-300) -> {n_moedas} fatos de moeda, "
          f"{n_pcts_curados} percentuais curados, {n_pcts_doc} variacoes derivaveis.")
    print(f"Varredura: sementes 0..{N_SEMENTES - 1}, {N_POR_SEMENTE} percentuais e "
          f"{N_POR_SEMENTE} moedas aleatorios (fora da base) por semente.\n")

    # Controle de sensibilidade
    ok, total, falhas = testar_legitimos()
    status = "OK" if (ok == total == LEGITIMOS_ESPERADOS and not falhas) else "FALHOU"
    print(f"[Controle] numeros legitimos com CONFERE: {ok}/{total} "
          f"(esperado {LEGITIMOS_ESPERADOS}/{LEGITIMOS_ESPERADOS}) - {status}")
    for f in falhas:
        print(f"  ! {f['trecho']!r} -> {f['veredito']} "
              f"({f.get('motivo', 'sem motivo')}; fato mais próximo: {f['fato_mais_proximo']})")
    print()

    # Varredura
    fp_pct, fp_moeda = [], []
    agg = {"pct": {"DIVERGENTE": 0, "NAO_ENCONTRADO": 0},
           "moeda": {"DIVERGENTE": 0, "NAO_ENCONTRADO": 0}}
    print(f"{'semente':>8} | {'FP percentuais':>15} | {'FP moedas':>10}")
    print("-" * 42)
    for semente in range(N_SEMENTES):
        r = rodar_semente(semente, moedas_excl, pcts_excl)
        fp_pct.append(r["pct"]["CONFERE"])
        fp_moeda.append(r["moeda"]["CONFERE"])
        for tipo in ("pct", "moeda"):
            for verd in ("DIVERGENTE", "NAO_ENCONTRADO"):
                agg[tipo][verd] += r[tipo][verd]
        print(f"{semente:>8} | {r['pct']['CONFERE']:>15} | {r['moeda']['CONFERE']:>10}")

    print("-" * 42)
    print("\nRESULTADO - falso-positivo (CONFERE indevido):")
    print(f"  Percentuais: {resumir(fp_pct)}")
    print(f"  Moedas:      {resumir(fp_moeda)}")
    print("\nDestino dos numeros aleatorios que nao passaram:")
    print(f"  Percentuais: {agg['pct']['DIVERGENTE']} DIVERGENTE, "
          f"{agg['pct']['NAO_ENCONTRADO']} NAO_ENCONTRADO")
    print(f"  Moedas:      {agg['moeda']['DIVERGENTE']} DIVERGENTE, "
          f"{agg['moeda']['NAO_ENCONTRADO']} NAO_ENCONTRADO")


if __name__ == "__main__":
    main()

# avaliacao/injetar_ground_truth.py
#
# Injeta o ground_truth em cada entrada do respostas_coletadas.json.
# Faz o match por (ticker, question) — ordem no arquivo não importa.
#
# Uso: python avaliacao/injetar_ground_truth.py
# Saída: avaliacao/respostas_coletadas.json (atualizado in-place)

import json
import os
import sys

# ── Ground truth extraído dos documentos CVM (valores em R$ milhares na fonte)
# Todos os valores já convertidos para linguagem legível.

GROUND_TRUTH = {
    # ── WEGE3 ──────────────────────────────────────────────────────────────────
    ("WEGE3", "Qual foi a receita líquida da WEG no último trimestre reportado?"):
        "R$ 9.468.313 mil (aproximadamente R$ 9,47 bilhões), queda de 6,1% "
        "em relação aos R$ 10.078.571 mil do período anterior.",

    ("WEGE3", "Qual foi o lucro líquido consolidado da WEG?"):
        "R$ 1.579.701 mil (aproximadamente R$ 1,58 bilhão), queda de 3,5% "
        "em relação aos R$ 1.637.180 mil do período anterior.",

    ("WEGE3", "Qual é a margem líquida da WEG?"):
        "Aproximadamente 16,7% — lucro líquido de R$ 1.579.701 mil "
        "sobre receita de R$ 9.468.313 mil.",

    ("WEGE3", "A WEG tem mais caixa ou mais dívidas?"):
        "A WEG tem mais caixa do que dívidas. Caixa e equivalentes: "
        "R$ 6.360.547 mil. Dívida bruta total (circulante R$ 3.099.649 mil + "
        "não circulante R$ 992.832 mil) = R$ 4.092.481 mil. "
        "Dívida líquida negativa de aproximadamente R$ 2,27 bilhões.",

    ("WEGE3", "Qual é o patrimônio líquido consolidado da WEG?"):
        "R$ 19.083.629 mil (aproximadamente R$ 19,08 bilhões), crescimento "
        "em relação aos R$ 18.553.364 mil do período anterior.",

    # ── LWSA3 ──────────────────────────────────────────────────────────────────
    ("LWSA3", "Qual foi a receita líquida da Locaweb no último trimestre?"):
        "R$ 362.780 mil (aproximadamente R$ 362,8 milhões), crescimento de "
        "4,0% em relação aos R$ 348.890 mil do período anterior.",

    ("LWSA3", "Qual foi o lucro líquido da Locaweb?"):
        "R$ 21.515 mil (aproximadamente R$ 21,5 milhões), crescimento de "
        "45,3% em relação aos R$ 14.808 mil do período anterior.",

    ("LWSA3", "Qual é a margem líquida da Locaweb?"):
        "Aproximadamente 5,9% — lucro líquido de R$ 21.515 mil "
        "sobre receita de R$ 362.780 mil.",

    ("LWSA3", "Como está a posição de caixa e dívida da Locaweb?"):
        "Caixa e equivalentes: R$ 288.599 mil. Empréstimos e financiamentos "
        "não circulantes (arrendamento): R$ 52.423 mil. A empresa tem "
        "dívida líquida negativa — mais caixa do que dívidas totais.",

    ("LWSA3", "O resultado operacional da Locaweb melhorou ou piorou?"):
        "Melhorou significativamente. EBIT (Resultado Antes do Resultado "
        "Financeiro e dos Tributos) foi de R$ 49.731 mil, crescimento de "
        "55,7% em relação aos R$ 31.948 mil do período anterior.",

    # ── LAVV3 ──────────────────────────────────────────────────────────────────
    ("LAVV3", "Qual foi a receita da Lavvi no último trimestre?"):
        "R$ 372.958 mil (aproximadamente R$ 373 milhões), crescimento de "
        "11,5% em relação aos R$ 334.630 mil do período anterior.",

    ("LAVV3", "Qual foi o lucro líquido da Lavvi?"):
        "R$ 82.073 mil (aproximadamente R$ 82,1 milhões), queda de 14,8% "
        "em relação aos R$ 96.354 mil do período anterior.",

    ("LAVV3", "Por que o lucro da Lavvi caiu mesmo com a receita crescendo?"):
        "As despesas financeiras saltaram de R$ 17.145 mil para R$ 28.475 mil "
        "(+66%), e o custo dos bens e serviços vendidos cresceu de "
        "R$ 209.067 mil para R$ 253.913 mil (+21,4%), comprimindo a margem "
        "apesar do crescimento da receita.",

    ("LAVV3", "Qual é a situação de endividamento da Lavvi?"):
        "Empréstimos e financiamentos circulantes somados a não circulantes "
        "são consideráveis. O patrimônio líquido consolidado caiu de "
        "R$ 1.780.796 mil para R$ 1.624.061 mil (queda de 8,8%). "
        "A empresa carrega dívida líquida positiva — mais dívidas que caixa "
        "(caixa de R$ 196.180 mil contra dívidas significativamente maiores).",

    ("LAVV3", "Qual é a margem líquida da Lavvi?"):
        "Aproximadamente 22% — lucro líquido de R$ 82.073 mil "
        "sobre receita de R$ 372.958 mil.",
}


def main():
    # Caminho do JSON relativo ao diretório do projeto
    base = os.path.dirname(os.path.abspath(__file__))
    caminho_json = os.path.join(base, "respostas_coletadas.json")

    if not os.path.exists(caminho_json):
        sys.exit(
            f"Arquivo não encontrado: {caminho_json}\n"
            "Rode coletar_respostas.py primeiro."
        )

    with open(caminho_json, "r", encoding="utf-8") as f:
        dados = json.load(f)

    nao_encontrados = []
    atualizados = 0

    for entrada in dados:
        chave = (entrada["ticker"], entrada["question"])
        gt = GROUND_TRUTH.get(chave)
        if gt:
            entrada["ground_truth"] = gt
            atualizados += 1
        else:
            entrada.setdefault("ground_truth", "")
            nao_encontrados.append(chave)

    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"OK: {atualizados} entradas atualizadas com ground_truth.")
    if nao_encontrados:
        print(f"AVISO: {len(nao_encontrados)} entradas sem ground_truth:")
        for ticker, question in nao_encontrados:
            print(f"   [{ticker}] {question}")
    else:
        print("OK: Todos os pares encontrados - dataset completo.")


if __name__ == "__main__":
    main()

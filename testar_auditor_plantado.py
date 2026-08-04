# testar_auditor_plantado.py
#
# Demonstração dirigida do auditor de fidelidade numérica (modulos/auditoria.py):
# 5 frases plantadas com vereditos esperados conhecidos, para mostrar o detector
# pegando cada tipo de problema (valor inexistente, sinal trocado, verbo
# invertido) e confirmando os casos legítimos.
#
# Autocontido: base de fatos fixa (métricas curadas de exemplo), SEM CVM e SEM
# LLM. Não altera nenhum módulo do sistema — apenas importa e exercita o auditor.
#
# Base de fatos (o que "existe" na fonte para este teste):
#   • receita ........ R$ 1,66 bilhões   (variação -1,3%)
#   • lucro .......... -R$ 1,47 milhões  (prejuízo — sinal negativo)
#
# Uso:  python testar_auditor_plantado.py

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")   # saída legível no console do Windows
except Exception:
    pass

from modulos.auditoria import auditar_narrativa

# ── Base de fatos fixa (métricas calculadas de exemplo) ───────────────────────
# O auditor extrai os fatos daqui: R$ 1,66 bi (receita, positivo), -R$ 1,47 mi
# (lucro, negativo) e a variação -1,3% da receita (base curada, dá CONFERE).
DADOS = {
    "receita_principal": {
        "valor_atual":  "R$ 1,66 bilhões",
        "variacao_pct": "-1,3%",
    },
    "lucro_liquido": {
        "valor_atual":  "-R$ 1,47 milhões",   # prejuízo: sinal negativo na fonte
    },
}

# Sem seções de documento: a base curada acima já basta para o teste.
SECOES_DOC = []

# ── Frases plantadas: (frase, veredito esperado, por quê) ─────────────────────
CASOS = [
    ("a empresa lucrou R$ 9,99 bilhões", "NAO_ENCONTRADO",
     "valor inexistente na base"),
    ("a receita foi de R$ 1,66 bilhões", "CONFERE",
     "valor correto"),
    ("a empresa lucrou R$ 1,47 milhões", "DIVERGENTE",
     "o fato é -1,47 (prejuízo): sinal trocado"),
    ("a receita cresceu 1,3%", "DIVERGENTE",
     "o fato é -1,3%: direção do verbo invertida"),
    ("a receita caiu 1,3%", "CONFERE",
     "direção e valor corretos"),
]


def veredito_da_frase(frase: str) -> str:
    """Roda o auditor sobre uma frase e devolve o veredito da verificação
    relevante (a única que conta, ignorando o recurso didático 'R$ 100')."""
    res = auditar_narrativa({"TESTE": frase}, SECOES_DOC, DADOS)
    contadas = [v for v in res["verificacoes"] if v["veredito"] != "IGNORADO"]
    if not contadas:
        return "SEM_NUMERO"
    return contadas[0]["veredito"]


def main():
    print("=" * 72)
    print("AUDITOR DE FIDELIDADE — 5 frases plantadas")
    print("=" * 72)
    print("Base de fatos: receita R$ 1,66 bi (var -1,3%) · lucro -R$ 1,47 mi\n")

    acertos = 0
    for frase, esperado, porque in CASOS:
        obtido = veredito_da_frase(frase)
        ok = (obtido == esperado)
        acertos += ok
        marca = "OK " if ok else "XX "
        print(f"[{marca}] \"{frase}\"")
        print(f"        esperado: {esperado:<15} obtido: {obtido:<15} ({porque})")

    print("\n" + "-" * 72)
    print(f"RESUMO: {acertos}/{len(CASOS)} frases com o veredito esperado — "
          f"{'TODAS CORRETAS' if acertos == len(CASOS) else 'HÁ DIVERGÊNCIA'}")


if __name__ == "__main__":
    main()

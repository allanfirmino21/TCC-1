# avaliacao/inspecionar_contexto.py
#
# Inspeciona o que o canal numerico do RAG devolve para um ticker.
# Uso: python avaliacao/inspecionar_contexto.py [TICKER] [TIPO_DOC] [PERIODO]

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modulos.recuperacao import recuperar_contexto

ticker   = sys.argv[1] if len(sys.argv) > 1 else "WEGE3"
tipo_doc = sys.argv[2] if len(sys.argv) > 2 else "ITR"
periodo  = sys.argv[3] if len(sys.argv) > 3 else "2026-03-31"

ctx_num, ctx_nar = recuperar_contexto(ticker, tipo_doc, periodo)

print(f"=== ctx_num para {ticker} {tipo_doc} {periodo} ({len(ctx_num):,} chars) ===\n")
print(ctx_num)

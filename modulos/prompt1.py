# modulos/prompt1.py
#
# Prompt 1 — Extração estruturada de dados financeiros
#
# Recebe: trechos numéricos do documento (DRE, Balanço, DFC)
# Devolve: JSON com métricas-chave padronizadas

import re
import json
import os
from google import genai
from google.genai import types as genai_types
from config import MODELO_LLM, MAX_TOKENS_EXTRACAO

# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT_EXTRACAO = """
Você é um especialista em demonstrações financeiras brasileiras. Sua única tarefa é
ler os trechos abaixo e preencher o JSON indicado com os valores encontrados.

## COMO INTERPRETAR OS DADOS
Os trechos vêm de planilhas da CVM no seguinte formato:

  Nome da conta          VALOR_ATUAL  (anterior: VALOR_ANTERIOR)

Regras de leitura:
- VALOR_ATUAL  = resultado do período atual (trimestre ou ano que está sendo analisado)
- VALOR_ANTERIOR = resultado do período imediatamente anterior (base de comparação)
- Todos os valores monetários estão em R$ milhares (mil reais).
  Para converter: divida por 1.000 para obter milhões, ou por 1.000.000 para bilhões.
  Exemplos: 9.468.313 → R$ 9,47 bilhões | 847.500 → R$ 847,5 milhões
- Prefira sempre dados do demonstrativo CONSOLIDADO ao INDIVIDUAL quando ambos existirem.
- "Receita de Venda de Bens e/ou Serviços" equivale à "Receita Líquida" para fins de análise.
- Para bancos e financeiras, "Receitas de Intermediação Financeira" equivale à receita principal.

## REGRAS DE PREENCHIMENTO
1. Use SOMENTE o que está explicitamente escrito nos trechos.
2. Você PODE calcular variação percentual quando VALOR_ATUAL e VALOR_ANTERIOR estiverem presentes.
   Fórmula: ((atual - anterior) / |anterior|) × 100, arredonde para 1 casa decimal com sinal.
   Exemplo: ((9468 - 10078) / 10078) × 100 = -6,1%
3. Quando um dado não existir nos trechos, use exatamente a string: "nao_disponivel"
4. Formate valores monetários como "R$ X,XX bilhoes" se o valor for maior ou igual a
   R$ 1 bilhão, ou "R$ X,XX milhoes" caso contrário. Nunca use milhares na saída.
   Exemplo: 1.655.238 (mil reais) → "R$ 1,66 bilhoes", nunca "R$ 1.655,24 milhoes".
5. Retorne SOMENTE o JSON — sem texto antes, sem explicacao depois, sem bloco markdown.

## ESTRUTURA DE SAIDA OBRIGATORIA
{{
  "periodo_referencia": "<AAAA-MM-DD>",
  "base_dados": "<Consolidado | Individual | Misto>",
  "escala_original": "R$ milhares (mil reais)",
  "receita_principal": {{
    "descricao": "<nome exato da linha no DRE, ex: Receita de Venda de Bens e/ou Servicos>",
    "valor_atual":    "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "valor_anterior": "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "variacao_pct":   "<+X,X% | -X,X% | nao_disponivel>"
  }},
  "lucro_liquido": {{
    "valor_atual":    "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "valor_anterior": "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "variacao_pct":   "<+X,X% | -X,X% | nao_disponivel>"
  }},
  "ebitda": {{
    "valor_atual": "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "margem_pct":  "<X,X% da receita principal | nao_disponivel>",
    "nota": "<'Nao consta no relatorio estruturado da CVM — comum em ITRs' se ausente>"
  }},
  "endividamento": {{
    "divida_bruta":         "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "caixa_e_equivalentes": "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "divida_liquida":       "<R$ X,XX bilhoes/milhoes | nao_disponivel>",
    "nota": "<observacao relevante, ex: empresa tem mais caixa do que divida>"
  }},
  "outros_destaques": [
    "<fato numerico relevante presente nos trechos que nao se encaixa nas categorias acima>"
  ],
  "dados_ausentes": [
    "<nome de cada metrica que nao foi encontrada nos trechos — seja especifico>"
  ],
  "advertencias": [
    "<inconsistencia, limitacao ou ponto de atencao identificado nos dados>"
  ]
}}

## TRECHOS DO DOCUMENTO
{contexto_numerico}
"""

# ── Execução ──────────────────────────────────────────────────────────────────

def executar_prompt_extracao(contexto_numerico: str) -> dict:
    """
    Envia o prompt de extração ao Gemini e retorna o JSON parseado.
    Retorna {"sucesso": True, "dados": {...}} ou {"sucesso": False, "erro": "...", ...}.
    """
    cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt  = PROMPT_EXTRACAO.format(contexto_numerico=contexto_numerico)

    try:
        resp = cliente.models.generate_content(
            model    = MODELO_LLM,
            contents = prompt,
            config   = genai_types.GenerateContentConfig(
                temperature        = 0.1,   # baixa para respostas determinísticas
                max_output_tokens  = MAX_TOKENS_EXTRACAO,
                response_mime_type = "application/json",  # força JSON puro, sem prosa
            ),
        )
        texto = resp.text
    except Exception as e:
        erro_str = str(e).lower()
        if any(k in erro_str for k in ("timeout", "deadline", "timed out", "connection")):
            return {
                "sucesso": False,
                "erro": (
                    "Tempo limite excedido ao chamar a API Gemini. "
                    "Verifique sua conexão e tente novamente em alguns instantes."
                ),
                "dados": {},
            }
        if any(k in erro_str for k in ("quota", "resource exhausted", "429")):
            return {
                "sucesso": False,
                "erro": (
                    "Limite de requisições da API Gemini atingido (quota). "
                    "Aguarde alguns minutos e tente novamente."
                ),
                "dados": {},
            }
        if any(k in erro_str for k in ("api key", "invalid key", "401", "403")):
            return {
                "sucesso": False,
                "erro": "Chave de API Gemini inválida ou sem permissão. Verifique a API Key informada.",
                "dados": {},
            }
        return {"sucesso": False, "erro": f"Erro na API Gemini: {e}", "dados": {}}

    # Verifica se a resposta foi interrompida pelo limite de tokens
    finish = "STOP"
    try:
        if resp.candidates:
            finish = resp.candidates[0].finish_reason.name
    except Exception:
        pass

    dados = _extrair_json(texto)
    if dados is None:
        if finish == "MAX_TOKENS":
            msg = (
                "O modelo atingiu o limite de tokens antes de concluir a extração. "
                "O sistema tentou recuperar os dados parciais mas não obteve JSON válido. "
                "Tente novamente — a resposta pode variar entre execuções."
            )
        else:
            msg = (
                "A API retornou uma resposta que não pôde ser interpretada como JSON. "
                "Tente novamente. Se o problema persistir, verifique se o modelo está disponível."
            )
        return {
            "sucesso":        False,
            "erro":           msg,
            "resposta_bruta": texto[:500] if texto else "",
            "dados":          {},
        }
    return {"sucesso": True, "dados": _normalizar_valores(dados)}


# ── Normalização de valores monetários ────────────────────────────────────────
#
# O LLM pode expressar o mesmo valor em unidades diferentes entre execuções
# (ex: "R$ 1.655,24 milhoes" vs "R$ 1,66 bilhoes"). Para a saída ser
# determinística, todo valor monetário do JSON é reformatado para uma unidade
# canônica: bilhões quando ≥ R$ 1 bilhão, milhões quando ≥ R$ 1 milhão,
# mil abaixo disso.

_RE_MONETARIO = re.compile(
    r"R\$\s*([\d.]+(?:,\d+)?)\s*(bilh(?:ão|ao|ões|oes)|milh(?:ão|ao|ões|oes)|mil)\b",
    re.IGNORECASE,
)

def _reformatar_moeda(m: re.Match) -> str:
    bruto, unidade = m.group(1), m.group(2).lower()
    try:
        numero = float(bruto.replace(".", "").replace(",", "."))
    except ValueError:
        return m.group(0)
    if unidade.startswith("bilh"):
        milhoes = numero * 1000
    elif unidade.startswith("milh"):
        milhoes = numero
    else:  # mil
        milhoes = numero / 1000
    if milhoes >= 1000:
        return "R$ " + f"{milhoes / 1000:.2f}".replace(".", ",") + " bilhões"
    if milhoes >= 1:
        return "R$ " + f"{milhoes:.2f}".replace(".", ",") + " milhões"
    return "R$ " + f"{milhoes * 1000:.0f}" + " mil"


def _normalizar_valores(obj):
    """Aplica a reformatação monetária a todas as strings do JSON, recursivamente."""
    if isinstance(obj, str):
        return _RE_MONETARIO.sub(_reformatar_moeda, obj)
    if isinstance(obj, list):
        return [_normalizar_valores(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _normalizar_valores(v) for k, v in obj.items()}
    return obj


def _extrair_json(texto: str) -> dict | None:
    """
    Extrai o primeiro objeto JSON válido do texto.
    Três tentativas em ordem crescente de permissividade:
      1. Texto completo (após remover cercas markdown)
      2. Bloco do primeiro '{' até o último '}' — cobre prosa antes/depois
      3. Truncamento: adiciona '}' faltantes para recuperar JSON cortado no limite de tokens
    """
    # Remove cercas de markdown ```json … ```
    limpo = re.sub(r"```(?:json)?\s*|\s*```", "", texto).strip()

    # Tentativa 1: texto completo como JSON
    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass

    # Tentativa 2: do primeiro '{' até o ÚLTIMO '}' (ignora prosa ao redor)
    inicio = limpo.find('{')
    fim    = limpo.rfind('}')
    if inicio != -1 and fim != -1 and fim > inicio:
        try:
            return json.loads(limpo[inicio:fim + 1])
        except json.JSONDecodeError:
            pass

    # Tentativa 3: JSON truncado — fecha chaves/colchetes abertos iterativamente
    if inicio != -1:
        fragmento = limpo[inicio:]
        # Conta chaves e colchetes abertos e fecha os que faltam
        pilha = []
        fechar = {'{': '}', '[': ']'}
        for ch in fragmento:
            if ch in '{[':
                pilha.append(fechar[ch])
            elif ch in '}]' and pilha and pilha[-1] == ch:
                pilha.pop()
        sufixo = ''.join(reversed(pilha))
        if sufixo:
            try:
                return json.loads(fragmento + sufixo)
            except json.JSONDecodeError:
                pass

    return None

# modulos/prompt2.py
#
# Prompt 2 — Narrativa para o investidor iniciante
#
# Recebe: JSON do Prompt 1 + trechos narrativos do documento
# Devolve: análise em linguagem simples, estruturada em 7 seções

import re
import json
import os
from google import genai
from google.genai import types as genai_types
from config import MODELO_LLM, MAX_TOKENS_NARRATIVA

# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT_NARRATIVA = """
Você é um comunicador financeiro. Sua missão é transformar dados de relatórios
corporativos em uma explicação que qualquer pessoa entenda — sem precisar saber
nada de finanças ou contabilidade.

## PERFIL DO LEITOR
Investidor iniciante que:
- Nunca leu um balanço patrimonial na vida
- Quer saber em linguagem direta se a empresa foi bem ou mal
- Precisa de contexto para entender o que os números significam
- Não quer recomendação de compra ou venda

## REGRAS ABSOLUTAS — VIOLÁ-LAS INVALIDA A ANÁLISE
1. Use APENAS o que está nos dados e trechos abaixo. Nunca invente, nunca especule.
2. TERMOS PROIBIDOS sem explicação entre parênteses:
   EBITDA, DRE, BPA, BPP, DFC, EBIT, LAJIDA, alavancagem, provisão,
   amortização, depreciação, ativo, passivo, patrimônio líquido, PL,
   exercício social, resultado financeiro (use "receitas e despesas com juros").
   Se precisar usar algum desses, explique logo depois: "EBITDA (lucro antes de
   descontar juros, impostos e depreciação)".
3. Não recomende compra, venda, manutenção ou qualquer ação do investidor.
4. Se os resultados pioraram, diga claramente: "o lucro caiu X%". Nunca suavize.
5. Ignore campos marcados como "nao_disponivel" — não mencione o que não existe.
   Campos "nao_aplicavel" são DIFERENTES: o indicador não faz sentido para esse
   tipo de empresa (ex.: dívida líquida para bancos). Explique isso brevemente
   em vez de tratar como informação faltante, e NUNCA liste "nao_aplicavel"
   entre as limitações da análise.
6. Números sempre formatados: "R$ 9,5 bilhões", nunca "9468313000".
   ATENÇÃO À ESCALA: os valores das tabelas do documento estão em R$ MIL.
   Uma linha "Despesas Financeiras   165751" significa R$ 165.751 mil, ou seja,
   R$ 165,8 milhões. NUNCA copie o número bruto da tabela com "R$" na frente —
   "R$ 165.751" está ERRADO (dá a entender um valor mil vezes menor).
   Prefira os valores já formatados dos DADOS FINANCEIROS EXTRAÍDOS; se citar
   um valor que só existe nos trechos do documento, converta para
   "R$ X,XX milhões/bilhões".
7. Variações sempre contextualizadas: "cresceu 12%", "caiu 6%", "ficou estável".
   Nunca escreva apenas o percentual sem o verbo.
8. Use "trimestre" ou "período" — nunca "exercício social".
9. PERÍODOS DE COMPARAÇÃO: os dados trazem o campo "comparacao" em cada métrica
   e o bloco "periodos" com os rótulos exatos. Use-os sempre:
   - Receita e lucro comparam com o campo "comparacao" deles (mesmo período do
     ano anterior).
   - Caixa e dívidas comparam com o campo "comparacao" do endividamento
     (fechamento do exercício anterior, 31/12).
   Nunca escreva apenas "período anterior" quando o rótulo exato existir, e
   nunca misture as duas bases de comparação como se fossem a mesma.

## FORMATO DE SAÍDA
Escreva exatamente 7 seções, cada uma começando na forma: ### NOME DA SEÇÃO
Não omita nenhuma seção. Se faltar dado, diga isso dentro da seção.

---

### RESUMO
3 a 5 frases. Responda: o que aconteceu com essa empresa nesse período?
Inclua obrigatoriamente: o nome da empresa, o período exato, se foi um
resultado melhor ou pior que o anterior, e o principal número que resume tudo.
Termine com uma frase que indique o que mais merece atenção.

### O QUE A EMPRESA FATURA
O que a empresa vende ou faz? Quanto faturou nesse período?
Cresceu ou caiu em relação ao período anterior? Por quantos por cento?
Explique de forma simples o que representa essa receita para o negócio.
Se não houver dado de receita: "Não foi possível identificar os dados de
faturamento com as informações disponíveis neste relatório."

### LUCRO
Quanto a empresa lucrou? Cresceu ou caiu?
Sempre contextualize: "a cada R$ 100 que a empresa faturou, sobrou R$ X de lucro".
Se o lucro caiu, explique o que os dados mostram como causa (se houver).
Se não houver dado de lucro: "Não foi possível identificar dados de lucro
neste relatório."

### SAÚDE DO CAIXA E DÍVIDAS
CASO BANCO (dívida marcada como "nao_aplicavel"): explique que dívida líquida
não é um indicador usado para bancos — captar dinheiro (depósitos de clientes,
mercado aberto) faz parte do negócio bancário, não é sinal de endividamento.
Apresente os "depositos" e a "captacao_mercado_aberto" com suas variações como
referência do tamanho do funding. Não lamente a ausência de dívida líquida.
CASO EMPRESA COMUM:
A empresa tem mais dinheiro guardado ou mais dívidas?
Use a "liquidez_total" (caixa + aplicações financeiras de curto prazo) como o
"dinheiro disponível" da empresa — explique entre parênteses que inclui
aplicações de curto prazo.
A dívida cresceu ou diminuiu em relação ao período de comparação?
Se houver "passivos_arrendamento", mencione-os: são compromissos de aluguéis
contratados (semelhantes a dívidas) e cite a "divida_bruta_com_arrendamentos".
O que isso significa na prática para a empresa?
Se não houver dados de endividamento: "Não foi possível avaliar a situação
financeira com os dados disponíveis."

### O QUE FOI POSITIVO
Lista de 2 a 4 pontos concretos e positivos encontrados nos dados.
Cada item deve ser uma frase curta e direta, ancorada em um número ou fato.
Comece cada item com "- ".
Se não houver pontos positivos claros: "- Não foram identificados destaques
positivos evidentes com os dados disponíveis."

### O QUE MERECE ATENÇÃO
Lista de 2 a 4 pontos que merecem acompanhamento — quedas, riscos, tendências.
Baseie-se apenas no que os dados mostram. Não especule sobre causas externas.
Comece cada item com "- ".
Se não houver dados suficientes: "- Não foi possível identificar pontos de
atenção com os dados disponíveis."

### LIMITAÇÕES DESTA ANÁLISE
O que esta análise NÃO pode responder? Por quê?
Seja específico: cite os dados que estavam ausentes (use o campo dados_ausentes).
Sempre inclua esta frase ao final: "Esta análise é baseada nos dados estruturados
do relatório da CVM e não substitui a leitura do documento completo."

---

## DADOS FINANCEIROS EXTRAÍDOS
{dados_json}

## TRECHOS NARRATIVOS DO DOCUMENTO
{contexto_narrativo}

## CONTEXTO
Empresa: {nome_empresa} ({ticker})
Periodo do relatorio: {periodo}
"""

# Mapeamento canônico: nome exato no prompt → chave do dicionário retornado
_SECOES_CANONICAS = [
    "RESUMO",
    "O QUE A EMPRESA FATURA",
    "LUCRO",
    "SAUDE DO CAIXA E DIVIDAS",
    "O QUE FOI POSITIVO",
    "O QUE MERECE ATENCAO",
    "LIMITACOES DESTA ANALISE",
]

# ── Execução ──────────────────────────────────────────────────────────────────

def executar_prompt_narrativa(
    dados_extracao:    dict,
    contexto_narrativo: str,
    ticker:            str,
    nome_empresa:      str,
    periodo:           str = "",
) -> dict:
    """
    Gera a narrativa para o investidor usando os dados do Prompt 1.
    Aceita `periodo` externo (do orquestrador) para não depender do Prompt 1.
    Sempre retorna um dict com chaves: sucesso, narrativa_completa, secoes, periodo.
    """
    dados   = dados_extracao.get("dados", {})
    periodo = periodo or dados.get("periodo_referencia", "nao identificado")

    cliente = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt  = PROMPT_NARRATIVA.format(
        dados_json         = json.dumps(dados, ensure_ascii=False, indent=2),
        contexto_narrativo = contexto_narrativo,
        ticker             = ticker,
        nome_empresa       = nome_empresa,
        periodo            = periodo,
    )

    try:
        resp = cliente.models.generate_content(
            model    = MODELO_LLM,
            contents = prompt,
            config   = genai_types.GenerateContentConfig(
                temperature       = 0.3,   # alguma fluidez narrativa, sem alucinação
                max_output_tokens = MAX_TOKENS_NARRATIVA,
            ),
        )
        texto = resp.text
    except Exception as e:
        erro_str = str(e).lower()
        if any(k in erro_str for k in ("timeout", "deadline", "timed out", "connection")):
            msg = (
                "Tempo limite excedido ao chamar a API Gemini na etapa de narrativa. "
                "Verifique sua conexão e tente novamente em alguns instantes."
            )
        elif any(k in erro_str for k in ("quota", "resource exhausted", "429")):
            msg = (
                "Limite de requisições da API Gemini atingido (quota). "
                "Aguarde alguns minutos e tente novamente."
            )
        elif any(k in erro_str for k in ("api key", "invalid key", "401", "403")):
            msg = "Chave de API Gemini inválida ou sem permissão. Verifique a API Key informada."
        else:
            msg = f"Erro na API Gemini ao gerar narrativa: {e}"
        return {
            "sucesso":            False,
            "erro":               msg,
            "narrativa_completa": "",
            "secoes":             {s: "" for s in _SECOES_CANONICAS},
            "periodo":            periodo,
        }

    # Verifica se a resposta foi interrompida pelo limite de tokens
    finish = "STOP"
    try:
        if resp.candidates:
            finish = resp.candidates[0].finish_reason.name
    except Exception:
        pass

    secoes = _parsear_secoes(texto)

    # Verifica se a narrativa tem conteúdo mínimo nas seções
    total_conteudo = sum(len(v) for v in secoes.values())
    if total_conteudo < 200:
        if finish == "MAX_TOKENS":
            msg = (
                "O modelo atingiu o limite de tokens antes de concluir a narrativa. "
                "Tente novamente — a geração pode variar entre execuções."
            )
        else:
            msg = (
                "A narrativa gerada não continha seções legíveis. "
                "Tente novamente. Se o problema persistir, verifique a API Key."
            )
        return {
            "sucesso":            False,
            "erro":               msg,
            "narrativa_completa": texto,
            "secoes":             secoes,
            "periodo":            periodo,
        }

    return {
        "sucesso":            True,
        "narrativa_completa": texto,
        "secoes":             secoes,
        "periodo":            periodo,
    }


def _parsear_secoes(texto: str) -> dict:
    """
    Extrai seções do texto dividindo em marcadores '### NOME'.
    Robusto a variações de espaçamento, capitalização e acentuação.
    Retorna um dict cujas chaves são os nomes normalizados das seções.
    """
    # Insere \n antes do primeiro ### para que o split capture tudo
    partes = re.split(r'\n###\s+', '\n' + texto.strip())

    secoes: dict[str, str] = {}
    for parte in partes[1:]:   # parte[0] é o texto antes do primeiro ###
        quebra = parte.find('\n')
        if quebra == -1:
            nome_bruto, conteudo = parte.strip(), ""
        else:
            nome_bruto = parte[:quebra].strip()
            conteudo   = parte[quebra:].strip()

        # Normaliza a chave: maiúsculas, sem acentos, sem caracteres especiais
        chave = _normalizar(nome_bruto)
        secoes[chave] = conteudo

    # Garante que todas as seções canônicas existem (vazio se o LLM omitiu)
    for secao in _SECOES_CANONICAS:
        if secao not in secoes:
            secoes[secao] = ""

    return secoes


def _normalizar(texto: str) -> str:
    """
    Converte para maiúsculas, remove acentos e pontuação extra.
    Usando dict no maketrans para evitar exigência de strings iguais.
    """
    mapa = str.maketrans({
        ord('Á'): 'A', ord('À'): 'A', ord('Ã'): 'A', ord('Â'): 'A', ord('Ä'): 'A',
        ord('É'): 'E', ord('È'): 'E', ord('Ê'): 'E', ord('Ë'): 'E',
        ord('Í'): 'I', ord('Ì'): 'I', ord('Î'): 'I', ord('Ï'): 'I',
        ord('Ó'): 'O', ord('Ò'): 'O', ord('Õ'): 'O', ord('Ô'): 'O', ord('Ö'): 'O',
        ord('Ú'): 'U', ord('Ù'): 'U', ord('Û'): 'U', ord('Ü'): 'U',
        ord('Ç'): 'C',
        # minúsculas (antes do .upper(), por precaução)
        ord('á'): 'A', ord('à'): 'A', ord('ã'): 'A', ord('â'): 'A', ord('ä'): 'A',
        ord('é'): 'E', ord('è'): 'E', ord('ê'): 'E', ord('ë'): 'E',
        ord('í'): 'I', ord('ì'): 'I', ord('î'): 'I', ord('ï'): 'I',
        ord('ó'): 'O', ord('ò'): 'O', ord('õ'): 'O', ord('ô'): 'O', ord('ö'): 'O',
        ord('ú'): 'U', ord('ù'): 'U', ord('û'): 'U', ord('ü'): 'U',
        ord('ç'): 'C',
    })
    sem_acento = texto.upper().translate(mapa)
    # Remove parênteses e pontuação que o LLM possa adicionar
    return re.sub(r'[^\w\s]', '', sem_acento).strip()

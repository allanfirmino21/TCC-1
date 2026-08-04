# fundIA — Análise Fundamentalista com IA

Lê os documentos financeiros de uma empresa listada na B3 e gera uma análise fundamentalista estruturada em linguagem natural.

---

## O problema que resolve

Relatórios financeiros (ITR e DFP) entregues à CVM são longos, técnicos e fragmentados em dezenas de arquivos CSV. Ler e interpretar esses dados manualmente exige horas de trabalho e conhecimento contábil específico. O fundIA automatiza esse processo: dado um ticker como `PETR4`, baixa os dados mais recentes, extrai o que importa e entrega uma análise em texto direto.

---

## Como funciona

O pipeline executa 8 etapas em sequência:

1. **Validação do ticker** — resolve o ticker para o código CVM em três níveis: mapa embutido no código, `dados/ticker_map.csv` (cache local) e, por fim, o cadastro oficial FCA da CVM, com match exato por `Codigo_Negociacao` e junção por CNPJ para obter código CVM e nome da empresa
2. **Busca do documento** — localiza o ITR ou DFP mais recente disponível no portal de dados abertos da CVM
3. **Download** — baixa os arquivos estruturados e salva em cache local para evitar downloads repetidos
4. **Extração de seções** — lê os CSVs e organiza as seções contábeis relevantes em texto
5. **Chunking e indexação** — divide o texto em chunks com sobreposição e indexa embeddings no ChromaDB
6. **Recuperação RAG** — recupera os chunks mais relevantes separando contexto numérico do narrativo
7. **Métricas + narrativa** — as métricas (receita, lucro, variações, margem, dívida bruta/líquida) são calculadas **deterministicamente em Python** a partir do documento estruturado (`modulos/metricas.py`), eliminando erros de aritmética do LLM. Os períodos de comparação são rotulados conforme a convenção da CVM (`ORDEM_EXERC = PENÚLTIMO`): no ITR, receita e lucro comparam com o **mesmo período do ano anterior**, enquanto caixa e dívidas comparam com o **fechamento do exercício anterior (31/12)**; na DFP, tudo compara com o exercício anterior. Os critérios de endividamento são explícitos: dívida bruta = empréstimos e financiamentos; liquidez total = caixa + aplicações financeiras de curto prazo; dívida líquida = dívida bruta − liquidez total; passivos de arrendamento (IFRS 16) são informados separadamente na visão ampliada. Instituições financeiras são detectadas automaticamente (plano de contas próprio na CVM): dívida líquida é marcada como não aplicável — captar recursos é o negócio bancário — e os indicadores exibidos passam a ser depósitos de clientes e captação no mercado aberto; em seguida o LLM atua apenas como redator, gerando a narrativa em 7 seções (resumo, receita, lucro, caixa/dívidas, pontos positivos, pontos de atenção, limitações). Se o documento não for parseável (ex.: PDF antigo), o sistema cai no caminho legado de extração via LLM (Prompt 1)
8. **Auditoria de fidelidade numérica** — cada número citado na narrativa (valores em R$, percentuais, razões) é conferido automaticamente contra o documento da CVM e as métricas calculadas (`modulos/auditoria.py`); o resultado inclui a **taxa de conformidade numérica** e a lista de valores divergentes ou não encontrados (possíveis alucinações)

---

## Tecnologias utilizadas

- Python 3.11+
- FastAPI + Uvicorn — API REST do backend (progresso em tempo real via SSE)
- React + Vite — interface web (`frontend/`)
- Streamlit — interface legada (`app.py`, opcional)
- Google Gemini 2.5 Flash — geração de texto
- sentence-transformers (`paraphrase-multilingual-mpnet-base-v2`) — embeddings
- ChromaDB — banco vetorial local persistente em disco (`chroma_db/`, via `PersistentClient`)
- RAGAS — avaliação automática de qualidade RAG
- Portal de Dados Abertos CVM — fonte dos documentos

---

## Como rodar

```bash
# 1. Instale as dependências do backend
pip install -r requirements.txt

# 2. Instale as dependências do frontend (requer Node.js 18+)
cd frontend && npm install && cd ..

# 3. Defina a chave da API do Gemini
set GEMINI_API_KEY=sua_chave_aqui   # Windows
export GEMINI_API_KEY=sua_chave_aqui  # Linux/macOS
# (alternativa: salve a chave em api_key.txt na raiz do projeto)

# 4. Inicie o backend (terminal 1)
uvicorn api:app --port 8000

# 5. Inicie o frontend (terminal 2)
cd frontend && npm run dev
```

Acesse `http://localhost:5173`, digite o ticker (ex: `WEGE3`), escolha o tipo de documento (ITR ou DFP) e clique em **Analisar**. O progresso das 7 etapas aparece em tempo real (Server-Sent Events).

A interface Streamlit legada continua disponível: `streamlit run app.py`.

---

## Estrutura de arquivos

```
api.py                          — backend FastAPI (SSE de progresso + PDF)
frontend/                       — interface React (Vite); consome a API via proxy
app.py                          — interface Streamlit legada
config.py                       — todas as constantes configuráveis do projeto
modulos/
  orquestrador.py               — executa as 7 etapas do pipeline
  ticker.py                     — resolve tickers via mapa embutido, ticker_map.csv e cadastro FCA da CVM
  cvm.py                        — busca e baixa documentos do portal da CVM
  extracao.py                   — lê os CSVs e extrai seções contábeis
  chunking.py                   — divide texto em chunks e indexa no ChromaDB
  recuperacao.py                — recupera contexto numérico e narrativo via RAG
  metricas.py                   — cálculo determinístico das métricas financeiras
  auditoria.py                  — auditoria automática de fidelidade numérica da narrativa
  prompt1.py                    — Prompt 1 (legado): extração via LLM, fallback para PDFs
  prompt2.py                    — Prompt 2: geração da narrativa em 7 seções
  relatorio_pdf.py              — gera o PDF da análise (usado pela API)
avaliacao/
  coletar_respostas.py          — recupera o contexto RAG das collections já indexadas e chama o Gemini com um prompt de QA próprio (não usa os Prompts 1 e 2 do pipeline)
  injetar_ground_truth.py       — adiciona respostas de referência ao JSON de entrada
  rodar_ragas.py                — calcula faithfulness e answer_relevancy via RAGAS
  respostas_coletadas.json      — entrada da avaliação
  resultados_ragas.json         — saída com scores por amostra e médias
dados/
  cache/                        — documentos baixados da CVM (evita re-download)
  ticker_map.csv                — cache local de tickers resolvidos via FCA
  fca_*.csv                     — cadastro FCA da CVM em cache (valor mobiliário + geral)
  meta_*.csv                    — índices anuais de documentos ITR/DFP em cache
```

---

## Avaliação

A qualidade do sistema é medida em duas frentes complementares:

**1. Taxa de conformidade numérica** (própria do projeto) — a etapa 8 do pipeline confere automaticamente cada número citado na narrativa contra o documento oficial da CVM, com tolerância de arredondamento. Enquanto o RAGAS mede consistência semântica, esta métrica mede exatidão aritmética — e detecta alucinações numéricas.

**2. RAGAS** — framework de avaliação usando um modelo de linguagem como juiz (`gemini-2.5-flash`), em duas métricas: **faithfulness** (a resposta se apoia apenas no contexto recuperado?) e **answer\_relevancy** (a resposta responde à pergunta feita? — esta métrica usa também o modelo de embeddings do projeto). Cada amostra é avaliada individualmente com timeout de 120 segundos e salva de forma progressiva, permitindo retomar a avaliação em caso de falha. Os resultados ficam em `avaliacao/resultados_ragas.json`.

---

## Limitações conhecidas

- Cobre apenas empresas com documentos disponíveis no portal de dados abertos da CVM; empresas estrangeiras e fundos não são suportados
- A análise depende da qualidade dos CSVs entregues à CVM — dados ausentes ou mal formatados reduzem a cobertura da extração
- O modelo não tem acesso a informações de mercado em tempo real (cotação, múltiplos de valuation)
- Documentos muito antigos podem ter formato diferente e falhar na etapa de extração
- O cache local não expira automaticamente; para reprocessar um ticker, use `forcar=True`
- A avaliação RAGAS mede consistência interna, não se a análise está "correta" do ponto de vista financeiro

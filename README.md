# fundIA

Sistema de análise fundamentalista automatizada de companhias abertas
brasileiras. A partir de um código de negociação da B3, obtém o documento
contábil mais recente entregue à Comissão de Valores Mobiliários (CVM), calcula
os indicadores financeiros em Python, gera uma explicação em linguagem acessível
com um modelo de linguagem e verifica automaticamente cada número dessa
explicação contra o documento de origem.

## Motivação

As demonstrações contábeis entregues à CVM são públicas e gratuitas, mas de
leitura difícil para quem não tem formação em contabilidade: os relatórios
completos passam de duzentas páginas e os dados estruturados vêm distribuídos em
CSVs anuais que reúnem todas as companhias, com valores expressos em milhares de
reais e plano de contas que varia por setor.

Modelos de linguagem traduzem esse material com fluência, mas podem produzir
números incorretos em texto convincente — risco incompatível com o domínio
financeiro, em que o leitor leigo não tem como perceber o erro. Este projeto
adota uma separação estrita de responsabilidades:

    fonte oficial → cálculo determinístico → redação pelo modelo → auditoria

O modelo de linguagem não executa nenhuma operação aritmética. Ele recebe os
indicadores já calculados e formatados, e sua saída é integralmente verificada
por um auditor determinístico, que produz a métrica central do sistema: a **taxa
de conformidade numérica**, acompanhada da proveniência de cada verificação.

## Arquitetura

O pipeline executa oito etapas em sequência (`modulos/orquestrador.py`):

1. **Validação do ticker** (`ticker.py`) — resolve o código de negociação para o
   código CVM em três níveis: mapa embutido, cache local em
   `dados/ticker_map.csv` e cadastro oficial FCA da CVM. Ticker não resolvido
   interrompe a execução, em vez de analisar empresa incorreta.
2. **Busca do documento** (`cvm.py`) — localiza o ITR ou DFP mais recente da
   companhia no índice anual da CVM.
3. **Download dos CSVs** (`cvm.py`) — baixa os dados estruturados (resultado,
   balanço patrimonial e fluxo de caixa), recorta as linhas da empresa e grava
   um extrato em `dados/cache/`.
4. **Extração de seções** (`extracao.py`) — organiza o extrato em seções
   contábeis identificadas.
5. **Chunking e indexação** (`chunking.py`) — segmenta o conteúdo e grava os
   embeddings em uma collection própria do documento no ChromaDB.
6. **Recuperação** (`recuperacao.py`) — recupera contexto em dois canais
   independentes, numérico e narrativo.
7. **Cálculo e narrativa** (`metricas.py`, `prompt2.py`) — os indicadores são
   calculados em Python, com o critério de cada agregado declarado na saída; o
   modelo de linguagem recebe os valores prontos e redige a análise em sete
   seções. Documentos não parseáveis recorrem à extração via modelo
   (`prompt1.py`).
8. **Auditoria de fidelidade numérica** (`auditoria.py`) — extrai da narrativa
   todo valor monetário, percentual e razão, e os confere contra as linhas do
   documento e os indicadores calculados, verificando magnitude, sinal e direção
   dos verbos. Cada verificação registra sua proveniência.

Os vereditos possíveis são `CONFERE`, `DIVERGENTE` (com motivo),
`NAO_ENCONTRADO` e `IGNORADO`. A taxa de conformidade numérica é a proporção de
valores auditáveis com veredito `CONFERE`.

As decisões de critério e o histórico técnico do projeto estão em
[`NOTAS_DESENVOLVIMENTO.md`](NOTAS_DESENVOLVIMENTO.md).

## Requisitos

- Python 3.12
- Node.js 18 ou superior (para a interface React)
- Chave de API do Google Gemini

## Instalação

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

Configure a chave da API por variável de ambiente ou arquivo local:

```bash
export GEMINI_API_KEY="sua-chave"        # Linux/macOS
$env:GEMINI_API_KEY = "sua-chave"        # Windows PowerShell
```

Alternativamente, grave a chave em `api_key.txt` na raiz do projeto. Esse
arquivo está listado no `.gitignore` e não deve ser versionado.

## Execução

Em dois terminais:

```bash
uvicorn api:app --port 8000
```

```bash
cd frontend && npm run dev
```

A interface fica em `http://localhost:5173`. Informe o ticker (por exemplo,
`WEGE3`), escolha o tipo de documento — ITR trimestral ou DFP anual — e execute
a análise. O progresso das oito etapas é transmitido em tempo real por
Server-Sent Events.

A primeira execução baixa o modelo de embeddings (aproximadamente 1 GB) e o
pacote anual da CVM, e por isso é sensivelmente mais lenta.

A interface Streamlit, versão inicial do projeto preservada para comparação,
é iniciada com `streamlit run app.py`.

## Estrutura

```
api.py                     backend FastAPI: progresso via SSE, fonte e PDF
app.py                     interface Streamlit (versão inicial)
config.py                  constantes de configuração
requirements.txt           dependências Python com versões
modulos/
  orquestrador.py          executa as oito etapas do pipeline
  ticker.py                resolução de ticker para código CVM
  cvm.py                   busca e download dos dados da CVM
  extracao.py              leitura dos CSVs e separação em seções
  chunking.py              segmentação e indexação vetorial
  recuperacao.py           recuperação de contexto (canais numérico e narrativo)
  metricas.py              cálculo determinístico dos indicadores
  auditoria.py             auditoria de fidelidade numérica
  prompt1.py               extração via modelo (caminho alternativo)
  prompt2.py               geração da narrativa em sete seções
  relatorio_pdf.py         geração do PDF da análise
frontend/                  interface React (Vite)
avaliacao/                 experimentos de avaliação e artefatos de resultado
dados/
  ticker_map.csv           mapa ticker → código CVM (versionado)
  cache/                   extratos da CVM baixados (gerado)
```

### Dados baixados automaticamente

Os índices anuais de documentos e o cadastro FCA (`dados/meta_*.csv`,
`dados/fca_*.csv`) não são versionados: o pipeline os obtém da CVM na primeira
execução e os revalida a cada 24 horas. O mesmo vale para `dados/cache/`
(extratos por empresa) e `chroma_db/` (banco vetorial). Nenhuma ação manual é
necessária — basta executar uma análise.

## Tecnologias

| Componente | Versão |
|---|---|
| Python | 3.12 |
| FastAPI | 0.136.3 |
| Uvicorn | 0.46.0 |
| google-genai (Gemini 2.5 Flash) | 2.2.0 |
| ChromaDB | 1.5.9 |
| sentence-transformers | 5.5.0 |
| pandas | 2.2.3 |
| pdfplumber | 0.11.9 |
| ReportLab | 4.5.1 |
| Streamlit | 1.44.1 |
| React | 19.2 |
| Vite | 8.1 |

O modelo de embeddings é o `paraphrase-multilingual-mpnet-base-v2`, executado
localmente.

## Reprodução dos experimentos

Os artefatos em `avaliacao/` são as evidências citadas no trabalho e estão
versionados. Os dois experimentos abaixo não dependem de rede nem de chave de
API, e reproduzem exatamente os valores publicados.

**Falso-positivo do auditor** — mede com que frequência um número aleatório
ausente da fonte recebe veredito `CONFERE`, sobre uma base fixa de 282 linhas,
com 20 sementes e 20 valores por semente:

```bash
python avaliacao/testar_falso_positivo_auditor.py
```

Resultado esperado: 0/400 em percentuais, 123/400 (30,8%) em valores monetários
neutros, e 9/9 no controle de sensibilidade com números legítimos. Saída
arquivada em `avaliacao/resultado_falso_positivo_2026-07-19.txt`.

**Detecção em frases plantadas** — cinco frases com defeitos conhecidos (erro de
escala, sinal trocado, direção do verbo) e seus vereditos esperados:

```bash
python avaliacao/testar_auditor_plantado.py
```

Resultado esperado: 5/5 vereditos corretos.

Os experimentos seguintes exigem chave de API e acesso à rede:

```bash
python avaliacao/coletar_respostas.py       # respostas do pipeline RAG
python avaliacao/injetar_ground_truth.py    # respostas de referência
python avaliacao/rodar_ragas.py             # faithfulness e answer_relevancy
python avaliacao/comparar_modelos.py        # narrativas com Flash e com Pro
```

As dependências do RAGAS estão listadas ao final do `requirements.txt` e não
são necessárias para executar o sistema.

### Artefatos arquivados

| Arquivo | Conteúdo |
|---|---|
| `evidencia_fidelidade_WEGE3.csv` | conferência manual contra a CVM, antes da correção de contas homônimas |
| `evidencia_fidelidade_WEGE3_v2.csv` | mesma conferência após a correção |
| `demonstracao_VALE3.json` | execução completa, ITR de março de 2026 |
| `demonstracao_VALE3_ITR_2026-06-30.json` | execução completa, ITR de junho de 2026 |
| `auditoria_VALE3_2026-06-30.csv` | trilha de auditoria exportada |
| `resultados_ragas.json` | scores por amostra e médias |
| `respostas_coletadas.json` | perguntas, respostas e referências |
| `comparacao_modelos.json` | narrativas geradas com Flash e com Pro |
| `auditoria_por_modelo_2026-07-19.json` | conformidade numérica por modelo |
| `resultado_falso_positivo_2026-07-19.txt` | saída do teste de falso-positivo |

## Limitações

- Cobre apenas companhias com documentos no portal de dados abertos da CVM.
- A extração depende da qualidade dos CSVs entregues; formatos antigos podem
  falhar.
- O EBITDA é uma aproximação declarada e pode divergir do valor divulgado pela
  companhia.
- O auditor verifica a existência do número na fonte, não a associação entre
  número e conceito; não avalia afirmações qualitativas nem números por extenso.
- O sistema não acessa dados de mercado (cotação, múltiplos) nem emite
  recomendação de investimento.
- O cache local não expira automaticamente; use a opção de forçar novo download
  para reprocessar.

Outras limitações e as medições de falso-positivo estão detalhadas em
[`NOTAS_DESENVOLVIMENTO.md`](NOTAS_DESENVOLVIMENTO.md).

## Trabalho acadêmico

Este repositório acompanha o Trabalho de Conclusão de Curso do Bacharelado em
Ciência de Dados e Inteligência Artificial da Universidade Federal da Paraíba.

- Autor: [nome do autor]
- Orientação: [nome do orientador]
- Monografia: [link para o texto]

Fonte dos dados: [Portal de Dados Abertos da CVM](https://dados.cvm.gov.br).

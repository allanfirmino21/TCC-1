# CLAUDE.md — Contexto do projeto fundIA

Este arquivo é o handoff entre sessões do Claude Code. Leia antes de qualquer
tarefa: ele resume o estado do projeto, as decisões já tomadas e o que falta.

## O que é o projeto

**fundIA** — sistema de análise fundamentalista automatizada para o TCC do
usuário. Dado um ticker da B3 (ex.: `POMO4`), baixa o ITR/DFP mais recente do
Portal de Dados Abertos da CVM, calcula métricas financeiras em Python e gera
uma narrativa em linguagem simples com o Gemini 2.5 Flash, verificada por uma
auditoria automática de fidelidade numérica.

- **Backend**: FastAPI (`api.py`, porta 8000) — progresso em tempo real via SSE
- **Frontend**: React + Vite (`frontend/`, porta 5173, proxy `/api` → 8000)
- **Interface legada**: Streamlit (`app.py`) — mantida só para comparação
- **Chave Gemini**: lida de `GEMINI_API_KEY` ou de `api_key.txt` na raiz
  (NUNCA commitar esse arquivo)

## Como rodar

```bash
# Terminal 1
uvicorn api:app --port 8000        # demora ~15-30s na primeira subida
# Terminal 2
cd frontend && npm run dev         # abrir http://localhost:5173
```

Dependências: `pip install -r requirements.txt` e `cd frontend && npm install`.

## Pipeline (8 etapas — modulos/orquestrador.py)

1. Validação do ticker (mapa embutido → `dados/ticker_map.csv` → cadastro FCA)
2. Busca do documento mais recente na CVM
3. Download dos CSVs estruturados → cache em `dados/cache/*.txt`
4. Extração de seções (`extracao.py`)
5. Chunking + indexação no ChromaDB (`chunking.py`)
6. Recuperação RAG (`recuperacao.py`) — hoje só o contexto narrativo é usado
7. **Métricas determinísticas** (`metricas.py`) + narrativa via LLM (`prompt2.py`);
   fallback para extração via LLM (`prompt1.py`) se o documento não for parseável
8. **Auditoria de fidelidade numérica** (`auditoria.py`) — selo de conformidade

## Histórico: Grupo 1 de melhorias (CONCLUÍDO e verificado)

Motivado por auditorias manuais de POMO4 (Marcopolo, CVM 8451) e ZAMP3
(Zamp, CVM 24317), ITR 2026-03-31:

1. **Cálculo determinístico** (`metricas.py`): o LLM não faz mais aritmética —
   era fonte de erros de arredondamento em cascata (margem 15,94% vs exata
   15,99%). O LLM é só redator. Formato do JSON compatível com o antigo Prompt 1.
2. **Auditoria automática** (`auditoria.py`): confere cada número da narrativa
   (moedas, percentuais, razões) contra o documento CVM + métricas calculadas.
   Vereditos: CONFERE / DIVERGENTE / NAO_ENCONTRADO / IGNORADO ("R$ 100"
   didático). Métrica original do TCC: **taxa de conformidade numérica**.
3. **Períodos de comparação corretos**: no ITR, DRE compara com o mesmo
   trimestre do ano anterior; balanço compara com 31/12 anterior (convenção
   `ORDEM_EXERC = PENÚLTIMO` dos CSVs da CVM). Rótulos em `rotular_periodos()`.
4. **Critérios explícitos de dívida**: liquidez total = caixa + aplicações
   financeiras de curto prazo; dívida líquida = empréstimos − liquidez total;
   arrendamentos (IFRS 16) informados separadamente na visão ampliada
   ("Financiamento por Arrendamento" é excluído da soma — é filha de
   Empréstimos, evita dupla contagem). Campo `criterio` declara as definições.

### Endurecimento do auditor (pós-verificação independente)

Verificação independente (recálculo direto do ZIP oficial da CVM, por
CD_CONTA) confirmou os cálculos (18/18 números), mas achou 3 furos no auditor,
todos corrigidos em `auditoria.py`:
- **Sinal**: "lucrou R$ 1,47 mi" com fato −1,47 → agora DIVERGENTE (marcadores
  de contexto: prejuízo/perda/negativo vs lucro/ganho; o mais próximo vence)
- **Tolerância de percentuais**: só a base curada (métricas calculadas) dá
  CONFERE; match apenas com variações deriváveis do documento → DIVERGENTE.
  Falso-CONFERE de percentuais aleatórios: 0/400 (20 sementes × 20 valores,
  ver `testar_falso_positivo_auditor.py`; a medida antiga era 0/20, 1 rodada)
- **Direção do verbo**: cresceu/caiu deve bater com o sinal da variação;
  "prejuízo aumentou X%" inverte a polaridade

Transparência do selo (pacote "quem audita o auditor"): cada verificação
registra a proveniência (`origem_fato` — linha do documento CVM com valor
bruto, ou campo das métricas calculadas); o painel React mostra a tabela
completa de verificações, nota de escopo (o que verifica / não verifica) e
exportação da trilha em CSV. Botão principal baixa o documento analisado da
empresa via `GET /api/fonte` (serve o cache `dados/cache/<TICKER>_<TIPO>_
<PERIODO>.txt`, com sanitização de parâmetros) — a CVM não publica arquivo
por empresa, só o ZIP anual; o portal RAD (link por empresa) vive fora do ar
e ficou como botão secundário rotulado "instável", junto com o link para os
dados abertos. Pendente (a decidir com o usuário): botão "teste o auditor"
que adultera um número de propósito e mostra o detector pegando — forte para
a demo da banca.

Limitações conhecidas do auditor (documentar no TCC, não corrigidas):
abreviações "R$ 1,66 bi" viram falso alarme; números por extenso ("dobrou")
passam sem verificação; moedas neutras têm **30,8% de coincidência acidental**
(123/400, média 6,15/20 por semente, mín 2 / máx 12 — medido por
`testar_falso_positivo_auditor.py` com base na densidade de um documento real,
~280 linhas; a estimativa antiga de ~10% veio de uma rodada única e está
superada). Enquadramento para a banca: o auditor verifica EXISTÊNCIA do número
na fonte, não a associação número↔conceito — sinal e direção mitigam nos casos
com contexto (lucro/prejuízo, verbos de variação).

Teste estatístico de falso-positivo: `testar_falso_positivo_auditor.py` na
raiz (autocontido, sem CVM/LLM; base de fatos fixa com 282 linhas + métricas
curadas de exemplo). Rodar com `python testar_falso_positivo_auditor.py`.
Resultados (2026-07-16): controle de sensibilidade 9/9 CONFERE (legítimos);
percentuais 0/400 falso-positivos; moedas 123/400 (30,8%).

(O script `testar_auditor_plantado.py` que demonstrava as frases plantadas foi
usado e apagado pelo usuário; se precisar de novo, recriar: base de fatos fixa
+ 5 frases com vereditos esperados, sem CVM/LLM.)

### Tratamento de bancos (pós-Grupo 1)

Bancos usam plano de contas próprio na CVM (sem "Empréstimos e Financiamentos"
nem circulante/não circulante no passivo). Correções em `metricas.py`:
- Detecção: receita de "Intermediação Financeira" OU linha "Depósitos" no passivo
- Dívida bruta/líquida = `nao_aplicavel` (≠ `nao_disponivel`) — prompt2 explica
  que o indicador não se aplica (captar é o negócio bancário) e NUNCA lista
  como limitação; o card React mostra "Depósitos" no lugar de "Dívida Líquida"
- Indicadores substitutos: depósitos de clientes + captação no mercado aberto
- `formatar_moeda()` ganhou escala trilhões (Itaú: depósitos R$ 1,10 tri);
  auditor reconhece "trilhão/trilhões"
- Bug corrigido no parsing: nomes de conta >55 chars estouram o padding do
  cvm.py e deixam 1 espaço só — regexes de linha usam `\s+` (não `\s{2,}`),
  ancoradas no "(anterior: ...)". Sem isso, linhas longas ficavam fora da
  base de fatos do auditor (falso alarme em "Operações de Crédito" do ITUB4).
Verificado: ITUB4 e BBAS3 detectados como bancos; POMO4/ZAMP3/ITSA4/CXSE3
inalterados; ITUB4 fim-a-fim com conformidade 21/21 (100%).

## Interface React (redesign editorial + fintech)

- Temas claro (padrão: papel quente + verde-floresta `#0e7a5f`) e escuro,
  alternados pelo botão sol/lua; implementação via `data-tema` no `<html>` +
  variáveis CSS em `index.css`, persistido em `localStorage['fundia-tema']`
- Fontes self-hosted via npm (`@fontsource-variable/fraunces` títulos serif,
  `@fontsource-variable/inter` corpo) — a demo funciona sem internet
- Ícones: `lucide-react` (nada de emoji na UI)
- Cartões de métrica têm barras comparativas anterior→atual (dois passos do
  mesmo matiz verde — codificação sequencial, validada pelo skill de dataviz);
  os valores são parseados das strings formatadas em `parseMoeda()` (Analise.jsx)
- Progresso das 8 etapas como linha do tempo com checks; painel de auditoria
  com selo, tabela de proveniência e botões de fonte
- Armadilha conhecida: instalar dependência npm com o `npm run dev` aberto
  duplica o React no cache do Vite ("Invalid hook call") — reiniciar o Vite
- O usuário roda os servidores nos terminais dele (uvicorn 8000 + npm 5173);
  antes de subir servidor de preview, conferir se as portas já estão em uso
  (erro WinError 10048) e NUNCA derrubar os processos do usuário. Mudanças em
  Python exigem restart do uvicorn; o frontend atualiza via HMR

## Decisões de critério (defender na monografia)

- Dívida líquida desconta aplicações financeiras (quase-caixa) — empresas
  divulgam critérios próprios; o campo `criterio` dá a transparência
- Variação com base negativa: reportar "prejuízo 2,5× maior", não "caiu 150%"
- Valores monetários: formato canônico "R$ X,XX bilhões/milhões" (≥1 bi →
  bilhões), 2 casas decimais — `formatar_moeda()` em `metricas.py`
- Receita de bancos: "Receitas de Intermediação Financeira"; receita zerada
  (holdings/seguradoras) tratada como indisponível; margem >100% omitida
  (holdings — lucro vem de equivalência patrimonial)

## Correções pós-Grupo 1 (concluídas e verificadas)

- **Escala R$ mil na narrativa**: o LLM copiava valores brutos do documento
  ("R$ 113.787" quando a linha da CVM dizia 113.787 mil = R$ 113,8 mi).
  Corrigido na regra 6 do `prompt2.py` (aviso explícito de escala) e no
  auditor (fallback: "R$ X" sem unidade que bate com um fato em R$ mil vira
  DIVERGENTE com motivo "valor em R$ mil citado sem conversão de escala").
- **Falso alarme de sinal**: "variação negativa de X%, chegando a R$ Y" fazia
  o marcador "negativa" reivindicar moeda negativa — `_sinal_contexto` agora
  neutraliza "variação negativa/positiva" antes da busca por marcadores.
- **Link RAD https**: o índice da CVM traz `LINK_DOC` em `http://`, mas o
  servidor RAD só responde em `https://` — normalizado em `cvm.py` e no botão
  React ("Relatório completo — ZIP oficial (RAD)", agora com destaque e antes
  de "Dados abertos"). O ZIP do RAD contém o PDF completo (200+ págs), que às
  vezes vem com padding de bytes nulos após o %%EOF (defeito da CVM).
- **Chip "caixa líquido"**: card de Dívida Líquida mostra chip verde quando o
  valor é negativo (prop `nota` genérico no componente `Metrica`).

## Próximos passos (Grupo 2 — aprovado pelo orientador)

5. **Avaliação em lote** (não iniciado): pipeline + conformidade numérica +
   RAGAS para 15–30 empresas de setores variados; tabela consolidada
   (capítulo de Resultados). Infra em `avaliacao/`. NOTA: a rodada antiga de
   RAGAS (3 tickers) deu faithfulness 0,44 comprovadamente por artefato do
   juiz LLM (auditoria manual confirmou 18/18 números) — no lote, apresentar
   RAGAS e conformidade lado a lado como argumento da métrica própria.
6. **Estudo de ablação do RAG** (não iniciado): comparar RAG atual vs mais
   chunks vs documento inteiro no contexto. Fundamenta a escolha arquitetural.
7. **EBITDA aproximado via DFC** — ✅ CONCLUÍDO (verificado fim-a-fim,
   WEGE3 27/27 na auditoria). Detalhes:
   - A CVM publica a DFC em 2 métodos: `DFC_MI_con` (indireto, ~98% das
     empresas, tem a linha de D&A) e `DFC_MD_con` (direto). O bug original:
     `cvm.py` só pedia o MD → nenhum cache tinha DFC. Agora tenta MI primeiro
     (títulos iguais, deduplicação em `secoes_gravadas`).
   - `metricas.py`: `_somar_depreciacao_amortizacao()` soma D&A da DFC com
     3 guardas — só o bloco operacional (para antes de "Caixa Líquido
     Atividades de Investimento"), exclusão por nome (Amortização de
     Empréstimos/Debêntures/passivos = pagamento de dívida, não D&A) e
     sinal (ajustes de D&A são sempre positivos). EBITDA = EBIT (DRE 3.05)
     + D&A, com `criterio` declarando a aproximação; bancos → `nao_aplicavel`.
   - Nomes de D&A variam: "Depreciação, amortização e exaustão" (WEG),
     "Depreciações e amortizações" (POMO), 2 linhas na ZAMP (D&A + amortização
     de arrendamentos IFRS16, ambas legítimas), armadilhas na ITSA (3 falsas).
   - Caches antigos não têm a seção DFC — regenerar com "Forçar novo download"
     (os 5 de teste ITR já foram regenerados; DFPs antigos ainda sem DFC →
     EBITDA `nao_disponivel`, caminho gracioso mantido).
   - Card React mostra "EBITDA (aproximado)" com delta e barras.

Ideia aprovada para o TCC 2 (não implementar agora): **seletor de
indicadores** — usuário escolhe indicadores extras de um cardápio; Python
calcula do cache, LLM explica em 2-3 frases, auditor confere (mesmo fluxo
determinístico→redator→auditor em miniatura).

Grupo 3 (menor prioridade): testes pytest, build único de produção
(`npm run build` + FastAPI servindo estático), histórico SQLite, análise
multi-período.

## Convenções

- Código e comentários em português; nomes de funções/variáveis em português
- Interfaces preservam o formato do JSON de `dados_extraidos` (React,
  Streamlit, PDF e prompt2 dependem dele)
- Testes/scripts temporários no scratchpad da sessão, não na raiz do projeto
- Empresas de teste com cache local: POMO4 e ZAMP3 (casos de lucro e prejuízo);
  ITUB4/BBAS3 (bancos), ITSA4 (holding) para casos especiais

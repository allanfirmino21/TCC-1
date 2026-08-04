# Notas de desenvolvimento — fundIA

Registro técnico das decisões de projeto, dos defeitos encontrados durante o
desenvolvimento e das correções aplicadas. Complementa o `README.md`, que trata
de instalação e uso; aqui ficam as razões por trás das escolhas e o histórico
que sustenta as afirmações do trabalho de conclusão de curso.

## Arquitetura em uma frase

O modelo de linguagem não calcula: as métricas são computadas em Python a partir
dos dados estruturados da CVM, o LLM apenas redige a narrativa e um auditor
determinístico confere cada número do texto contra a fonte.

Cadeia completa: fonte oficial → cálculo determinístico → redação pelo LLM →
auditoria → taxa de conformidade numérica.

## Decisões de critério

Escolhas que não são únicas na literatura e que, por isso, ficam declaradas no
campo `criterio` do JSON de saída — o leitor pode discordar do critério, mas não
fica sem saber qual foi usado.

- **Dívida líquida** desconta caixa *e* aplicações financeiras de curto prazo
  (quase-caixa). Empresas divulgam critérios próprios; o campo `criterio`
  explicita o adotado.
- **Passivos de arrendamento** (IFRS 16) entram apenas na visão ampliada, nunca
  na dívida bruta principal. A linha "Financiamento por Arrendamento" é excluída
  da soma por ser filha de "Empréstimos e Financiamentos" — somá-la seria dupla
  contagem.
- **Variação sobre base negativa** é reportada como razão ("prejuízo 2,5 vezes
  maior"), não como percentual. "Caiu 150%" partindo de prejuízo confunde o
  leitor.
- **Valores monetários** seguem formato canônico "R$ X,XX bilhões/milhões", duas
  casas decimais, com escala de trilhões para bancos.
- **Margem acima de 100%** é omitida: típica de holdings, cujo lucro vem de
  equivalência patrimonial, ela perde o sentido usual de margem sobre receita.
- **EBITDA** é declarado como aproximação: resultado operacional (DRE) somado à
  depreciação e amortização da DFC. A CVM não publica EBITDA nos dados
  estruturados; o valor pode divergir do divulgado pela empresa.

## Tratamento de casos setoriais

- **Instituições financeiras** usam plano de contas próprio: não existe
  "Empréstimos e Financiamentos" nem circulante/não circulante no passivo.
  A detecção é feita pela receita de intermediação financeira ou pela linha
  "Depósitos". Para elas, dívida líquida e EBITDA são marcados como
  `nao_aplicavel` — distinto de `nao_disponivel` — e substituídos por depósitos
  de clientes e captação no mercado aberto.
- **Holdings** frequentemente têm receita zerada na linha padrão; o sistema
  trata o campo como indisponível em vez de exibir "R$ 0", que seria enganoso.

## Histórico de defeitos e correções

Os dois primeiros casos são citados no texto do TCC e permanecem rastreáveis
pelos artefatos indicados.

### Contas homônimas no pareamento atual/anterior

O cache pareava o valor atual de uma conta com o valor anterior de outra de
**mesmo nome**. Na WEG (WEGE3, ITR de 31/03/2026), "Aplicações Financeiras"
existe em duas rubricas distintas do ativo circulante — `CD_CONTA` 1.01.01.02 e
1.01.02 — e o pareamento cruzado produziu variação falsa de **+327,6%**
(4.204.784 contra 983.367, valor anterior da rubrica errada) quando a variação
real é **−1,2%** (4.204.784 contra 4.255.539). O mesmo defeito afetou
"Empréstimos e Financiamentos" (`CD_CONTA` 2.01.04): **+197,6%** falso contra
**−12,7%** real.

Correção: o pareamento passou a usar `CD_CONTA` como chave, não o nome da conta.

Rastreabilidade: `avaliacao/evidencia_fidelidade_WEGE3.csv` registra o estado
com o defeito, incluindo a aritmética falsa;
`avaliacao/evidencia_fidelidade_WEGE3_v2.csv` registra o estado corrigido, com
anotação explícita da correção.

### Escala de milhares na narrativa

Os valores dos CSVs da CVM estão em R$ mil. Ao redigir a análise da DFP da WEG
(exercício de 2025), o modelo copiou valores brutos da tabela precedidos de
"R$" — citou "R$ 113.787" e "R$ 165.751" para a conta "Despesas Financeiras"
(`CD_CONTA` 3.06.02), cujos valores reais são R$ 113,79 milhões e R$ 165,75
milhões. Erro de três ordens de grandeza, em texto fluente.

A auditoria automática sinalizou os dois números. As correções foram aplicadas
em duas camadas: a regra 6 do `prompt2.py` passou a advertir explicitamente
sobre a escala, e o auditor ganhou verificação específica que reconhece o padrão
e emite veredito `DIVERGENTE` com o motivo "valor em R$ mil citado sem conversão
de escala", em vez do genérico "não encontrado".

Rastreabilidade: `modulos/auditoria.py` (tratamento de valores sem unidade) e
`modulos/prompt2.py` (regra 6).

### Acumulado do exercício confundido com trimestre isolado

Em ITRs do segundo trimestre em diante, os CSVs da CVM trazem duas linhas por
conta com `ORDEM_EXERC = ÚLTIMO`, distinguidas apenas por `DT_INI_EXERC`: o
acumulado do ano e o trimestre isolado. O código escolhia a primeira que
aparecesse no arquivo. No ITR de setembro de 2025 da Gol (GOLL4), o sistema
reportava R$ 16,0 bilhões (nove meses acumulados) sob o rótulo "3º trimestre" e,
pior, podia parear receita e lucro de períodos diferentes, corrompendo a margem.

O defeito passou despercebido porque quase todos os documentos do conjunto de
teste eram de primeiro trimestre, em que acumulado e trimestre coincidem.

Correção: filtro por `DT_INI_EXERC` mantendo o acumulado (função
`_manter_acumulado` em `modulos/cvm.py`), aplicado igualmente às colunas atual e
anterior para garantir bases comparáveis, mais rótulos honestos por mês de
referência em `rotular_periodos` ("1º semestre (6 meses acumulados)", "9 meses
acumulados").

Este defeito é o caso concreto da limitação "existência não é associação" do
auditor: os dois valores existem no documento, de modo que a verificação de
existência não o detectaria.

### Demonstração de fluxo de caixa ausente do cache

A CVM publica a DFC em dois métodos: indireto (`DFC_MI`), usado pela quase
totalidade das empresas e único que traz a linha de depreciação e amortização, e
direto (`DFC_MD`). O download pedia apenas o método direto, de modo que nenhum
cache continha a DFC e o EBITDA ficava permanentemente indisponível. Correção:
tentar o método indireto primeiro, com deduplicação por título de seção.

A soma de depreciação e amortização tem três salvaguardas, todas motivadas por
casos reais: limitar-se ao bloco operacional; excluir por nome os homônimos que
representam pagamento de dívida ("Amortização de Empréstimos", "de Debêntures",
"de passivos de arrendamento" — três armadilhas presentes na Itaúsa); e exigir
sinal positivo, já que ajustes de D&A nunca são desembolsos.

### Falso alarme na verificação de sinal

A frase "variação negativa de 19,8%, chegando a R$ 18,55 bilhões" fazia o
auditor interpretar "negativa" como reivindicação de valor monetário negativo,
gerando divergência indevida. A expressão qualifica o percentual, não a moeda:
`_sinal_contexto` passou a neutralizar "variação negativa/positiva" antes de
procurar marcadores de sinal.

### Ticker com dígito no radical

O validador exigia quatro letras seguidas de dígitos, o que rejeitava B3SA3 — a
própria B3. Corrigido para aceitar dígito a partir do segundo caractere do
radical.

## Limitações conhecidas do auditor

Documentadas por honestidade metodológica; nenhuma foi corrigida, por envolver
mudança de escopo do verificador.

- Não verifica números por extenso ("dobrou", "triplicou") nem afirmações
  qualitativas.
- Abreviações informais ("R$ 1,66 bi") podem gerar falso alarme.
- Verifica a **existência** do número na fonte, não a associação entre número e
  conceito. Sinal e direção do verbo mitigam os casos com contexto explícito
  (lucro contra prejuízo, cresceu contra caiu).
- Coincidência acidental medida em 30,8% para valores monetários neutros e 0%
  para percentuais (ver `avaliacao/testar_falso_positivo_auditor.py`).
- A base de fatos inclui as bases individual e consolidada, o que amplia a
  coincidência acidental. Restringi-la à consolidada exigiria refazer as
  medições de falso-positivo já reportadas.

## Interface

- Duas interfaces consomem o mesmo pipeline: React (`frontend/`), principal, e
  Streamlit (`app.py`), versão inicial preservada. Ambas dependem do formato do
  JSON de `dados_extraidos`.
- Temas claro e escuro via atributo `data-tema` e variáveis CSS, com preferência
  persistida no navegador.
- Fontes e ícones são servidos localmente, sem dependência de rede em execução.
- Cartões de métrica trazem barras comparativas entre período anterior e atual,
  o critério de cálculo e uma linha explicativa em linguagem simples.

## Convenções do código

- Código, comentários e identificadores em português.
- O formato do JSON de `dados_extraidos` é contrato entre backend, as duas
  interfaces, o gerador de PDF e o Prompt 2 — alterações exigem revisão dos
  quatro.
- Comentários explicam por que uma decisão foi tomada, não o que a linha faz.
- Empresas usadas como caso de teste: POMO4 e ZAMP3 (lucro e prejuízo), WEGE3
  (caixa líquido), ITUB4 e BBAS3 (bancos), ITSA4 (holding), GOLL4 (trimestre não
  inicial), VALE3 (demonstração de referência).

## Trabalhos futuros

- Avaliação em lote com 15 a 30 empresas, reportando taxa de conformidade e
  métricas RAGAS lado a lado.
- Estudo de ablação da recuperação: configuração atual contra mais fragmentos e
  contra o documento inteiro no contexto.
- Seletor de indicadores sob demanda, calculados em Python e explicados pelo
  LLM, reutilizando o mesmo fluxo de auditoria.
- Testes automatizados, build único de produção e histórico de análises.

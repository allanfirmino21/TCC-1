// Analise — painel de resultado: cabeçalho, métricas em destaque (com barras
// comparativas anterior→atual) e as 7 seções da narrativa.

import { useState } from 'react'
import {
  FileText, Banknote, TrendingUp, Landmark, CircleCheck, TriangleAlert,
  Info, ShieldCheck, Download, ArrowUpRight, ArrowDownRight, LoaderCircle,
  ExternalLink, FileDown, Wallet,
} from 'lucide-react'
import { baixarPdf } from '../api'

const ND = 'nao_disponivel'
const NA = 'nao_aplicavel'

/** Converte "nao_disponivel"/"nao_aplicavel" em travessão. */
function val(v) {
  return !v || v === ND || v === NA ? '—' : v
}

/** "R$ 1,66 bilhões" → 1.66e9 (para proporção das barras comparativas). */
function parseMoeda(s) {
  if (!s || s === ND || s === NA) return null
  const m = /(-?)\s*R\$\s*([\d.]+(?:,\d+)?)\s*(trilh|bilh|milh|mil)?/i.exec(s)
  if (!m) return null
  const n = parseFloat(m[2].replace(/\./g, '').replace(',', '.'))
  const u = (m[3] || '').toLowerCase()
  const mult = u === 'trilh' ? 1e12 : u === 'bilh' ? 1e9 : u === 'milh' ? 1e6 : u === 'mil' ? 1e3 : 1
  return (m[1] ? -1 : 1) * n * mult
}

/**
 * Renderiza o texto das seções: linhas iniciadas com "- " viram lista,
 * o restante vira parágrafos (a narrativa vem em texto simples do LLM).
 */
function Texto({ children }) {
  const linhas = (children || '').split('\n').map((l) => l.trim()).filter(Boolean)
  const blocos = []
  let lista = []

  const fechaLista = () => {
    if (lista.length) {
      blocos.push(<ul key={`ul-${blocos.length}`}>{lista.map((li, i) => <li key={i}>{li}</li>)}</ul>)
      lista = []
    }
  }

  linhas.forEach((linha, i) => {
    if (linha.startsWith('- ')) {
      lista.push(linha.slice(2))
    } else {
      fechaLista()
      blocos.push(<p key={`p-${i}`}>{linha}</p>)
    }
  })
  fechaLista()
  return <>{blocos}</>
}

/**
 * Stat tile: valor grande + chip de variação + barras comparativas
 * (período anterior em passo claro do mesmo matiz, atual no acento).
 * `nota` é um chip qualitativo opcional (ex.: "caixa líquido");
 * `explicacao` é a linha didática visível para o investidor iniciante.
 */
function Metrica({ rotulo, valor, delta, anterior, ajuda, nota, notaAjuda, explicacao }) {
  const negativo = delta?.startsWith('-')
  const vAtual = parseMoeda(valor)
  const vAnt = parseMoeda(anterior)
  const temBarras = vAtual > 0 && vAnt > 0
  const maximo = temBarras ? Math.max(vAtual, vAnt) : 1

  return (
    <div className="cartao metrica" title={ajuda}>
      <span className="metrica-rotulo">{rotulo}</span>
      <strong className="metrica-valor">{valor}</strong>
      {delta && delta !== ND && (
        <span className={`chip-delta ${negativo ? 'baixa' : 'alta'}`}>
          {negativo ? <ArrowDownRight size={13} /> : <ArrowUpRight size={13} />}
          {delta}
        </span>
      )}
      {nota && (
        <span className="chip-nota" title={notaAjuda}>
          <Wallet size={13} />
          {nota}
        </span>
      )}
      {temBarras && (
        <div className="barras" aria-hidden="true">
          <div className="barra anterior" style={{ width: `${(vAnt / maximo) * 100}%` }} />
          <div className="barra atual" style={{ width: `${(vAtual / maximo) * 100}%` }} />
          <span className="barras-legenda">anterior: {anterior}</span>
        </div>
      )}
      {explicacao && <p className="metrica-explicacao">{explicacao}</p>}
    </div>
  )
}

const ROTULO_VEREDITO = {
  CONFERE: '✔ confere',
  DIVERGENTE: '△ divergente',
  NAO_ENCONTRADO: '✕ não encontrado',
  IGNORADO: '· ignorado',
}

const SECAO_CURTA = {
  'RESUMO': 'Resumo',
  'O QUE A EMPRESA FATURA': 'Faturamento',
  'LUCRO': 'Lucro',
  'SAUDE DO CAIXA E DIVIDAS': 'Caixa e Dívidas',
  'O QUE FOI POSITIVO': 'Positivo',
  'O QUE MERECE ATENCAO': 'Atenção',
  'LIMITACOES DESTA ANALISE': 'Limitações',
}

/** Baixa a trilha de auditoria completa como CSV (para conferência externa). */
function exportarCsv(verificacoes, ticker, periodo) {
  const esc = (s) => `"${String(s ?? '').replace(/"/g, '""')}"`
  const linhas = [
    ['secao', 'numero_citado', 'tipo', 'veredito', 'motivo', 'conferido_contra', 'valor_na_fonte']
      .join(';'),
    ...verificacoes.map((v) => [
      esc(SECAO_CURTA[v.secao] || v.secao), esc(v.trecho), esc(v.tipo), esc(v.veredito),
      esc(v.motivo), esc(v.origem_fato), esc(v.fato_mais_proximo),
    ].join(';')),
  ]
  const blob = new Blob(['﻿' + linhas.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `auditoria_${ticker}_${periodo}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Selo de auditoria de fidelidade numérica — mostra o trabalho, não só a
 * conclusão: tabela completa com a proveniência de cada verificação, link
 * para o documento oficial e declaração explícita do escopo.
 */
function Auditoria({ auditoria, linkCvm, ticker, periodo, tipoDoc }) {
  if (!auditoria?.resumo) return null
  const { resumo, verificacoes } = auditoria
  const nivel = resumo.taxa_conformidade >= 99.9 ? 'ok'
    : resumo.taxa_conformidade >= 90 ? 'alerta' : 'falha'

  // Fonte primária de verdade: o Portal de Dados Abertos da CVM, de onde o
  // sistema baixa os CSVs. O link do portal RAD (visualizador de documentos)
  // fica como secundário — o serviço é instável com frequência.
  const doc = (tipoDoc || 'itr').toLowerCase()
  const linkDadosAbertos = `https://dados.cvm.gov.br/dataset/cia_aberta-doc-${doc}`

  return (
    <details className="cartao auditoria">
      <summary>
        <span><ShieldCheck size={18} /> Auditoria de fidelidade numérica</span>
        <span className={`selo ${nivel}`}>
          {resumo.conferem}/{resumo.total_numeros} números conferem · {resumo.taxa_conformidade}%
        </span>
      </summary>

      <p className="auditoria-explicacao">
        Cada valor citado na análise foi verificado automaticamente. A tabela
        abaixo mostra <strong>contra o quê</strong> cada número foi conferido —
        você pode localizar qualquer linha no documento oficial e confirmar por
        conta própria.
      </p>

      <div className="nota-escopo">
        <p><strong>O que este selo verifica:</strong> valores monetários (R$),
        percentuais (%) e razões ("2,5 vezes") citados no texto, comparados com o
        documento oficial da CVM e as métricas calculadas — incluindo o sinal
        (lucro vs. prejuízo) e a direção dos verbos ("cresceu" vs. "caiu").</p>
        <p><strong>O que ele não verifica:</strong> afirmações qualitativas
        ("o trimestre foi desafiador"), números por extenso ("dobrou") e
        interpretações. Esses continuam sendo responsabilidade do leitor.</p>
      </div>

      <div className="auditoria-acoes">
        <a className="botao-mini"
           href={`/api/fonte?ticker=${ticker}&tipo=${tipoDoc}&periodo=${periodo}`}
           title={`O extrato de ${ticker} baixado da CVM — exatamente o documento contra o qual cada número foi conferido`}>
          <FileDown size={14} /> Baixar o documento analisado ({ticker})
        </a>
        <button className="botao-mini" onClick={() => exportarCsv(verificacoes, ticker, periodo)}>
          <FileDown size={14} /> Exportar trilha de auditoria (CSV)
        </button>
        {linkCvm && (
          <a className="botao-mini"
             href={linkCvm.replace(/^http:\/\//i, 'https://')}
             target="_blank" rel="noreferrer"
             title="Baixa do portal RAD da CVM o pacote ZIP oficial deste documento, com o relatório completo em PDF (centenas de páginas). O servidor da CVM é instável — se o download falhar, tente novamente.">
            <FileDown size={14} /> Relatório completo — ZIP oficial (RAD)
          </a>
        )}
        <a className="botao-mini secundario" href={linkDadosAbertos} target="_blank" rel="noreferrer"
           title="Portal de Dados Abertos da CVM — pacote anual com todas as empresas, de onde o extrato foi retirado">
          <ExternalLink size={14} /> Dados abertos da CVM
        </a>
      </div>

      <div className="tabela-scroll">
        <table className="tabela-auditoria">
          <thead>
            <tr>
              <th>Número citado</th>
              <th>Seção</th>
              <th>Conferido contra</th>
              <th>Veredito</th>
            </tr>
          </thead>
          <tbody>
            {verificacoes.map((v, i) => (
              <tr key={i}>
                <td><code>{v.trecho}</code></td>
                <td>{SECAO_CURTA[v.secao] || v.secao}</td>
                <td className="origem">
                  {v.origem_fato || '—'}
                  {v.motivo && <span className="motivo"> · {v.motivo}</span>}
                </td>
                <td>
                  <span className={`veredito v-${v.veredito}`}>
                    {ROTULO_VEREDITO[v.veredito] || v.veredito}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export default function Analise({ resultado }) {
  const [gerandoPdf, setGerandoPdf] = useState(false)
  const [erroPdf, setErroPdf] = useState(null)

  const { analise, nome_empresa: empresa, ticker, tipo_documento: tipoDoc } = resultado
  const dados = analise.dados_extraidos
  const secoes = analise.secoes
  const periodo = analise.periodo

  const rec = dados.receita_principal || {}
  const lucro = dados.lucro_liquido || {}
  const divida = dados.endividamento || {}
  const ebitda = dados.ebitda || {}

  const aoBaixarPdf = async () => {
    setGerandoPdf(true)
    setErroPdf(null)
    try {
      await baixarPdf({ empresa, ticker, periodo, tipoDoc, secoes })
    } catch (e) {
      setErroPdf(e.message)
    } finally {
      setGerandoPdf(false)
    }
  }

  return (
    <div className="analise">
      {/* Cabeçalho */}
      <header className="cabecalho">
        <h1>{empresa}</h1>
        <div className="tags">
          <span className="tag">Ticker <code>{ticker}</code></span>
          <span className="tag">Período <code>{periodo}</code></span>
          <span className="tag">Relatório <code>{tipoDoc}</code></span>
          <span className="tag">Base <code>{val(dados.base_dados)}</code></span>
        </div>
      </header>

      {/* Métricas em destaque */}
      <section className="metricas">
        <Metrica
          rotulo={rec.descricao || 'Receita Principal'}
          valor={val(rec.valor_atual)}
          delta={rec.variacao_pct}
          anterior={rec.valor_anterior}
          ajuda="Primeiro nível de receita no demonstrativo de resultado"
          explicacao="Tudo o que a empresa recebeu com suas vendas no período, antes de descontar qualquer custo."
        />
        <Metrica
          rotulo="Lucro Líquido"
          valor={val(lucro.valor_atual)}
          delta={lucro.variacao_pct}
          anterior={lucro.valor_anterior}
          ajuda="Lucro líquido do período versus o mesmo período do ano anterior"
          explicacao="O que sobrou no bolso da empresa depois de pagar todos os custos, despesas e impostos."
        />
        {divida.depositos ? (
          <Metrica
            rotulo="Depósitos"
            valor={val(divida.depositos)}
            delta={divida.variacao_depositos_pct}
            anterior={divida.depositos_anterior}
            ajuda="Depósitos de clientes — para bancos, dívida líquida não se aplica: captar recursos faz parte do negócio"
            explicacao="Dinheiro que os clientes guardam no banco — a principal fonte de recursos de um banco (por isso não se fala em dívida líquida)."
          />
        ) : (
          <Metrica
            rotulo="Dívida Líquida"
            valor={val(divida.divida_liquida)}
            anterior={divida.divida_liquida_anterior}
            ajuda="Dívida bruta menos liquidez total (caixa + aplicações de curto prazo)"
            nota={parseMoeda(divida.divida_liquida) < 0 ? 'caixa líquido' : null}
            notaAjuda="Dívida líquida negativa: a liquidez total supera a dívida bruta — a empresa poderia quitar todas as dívidas e ainda sobraria dinheiro"
            explicacao={parseMoeda(divida.divida_liquida) < 0
              ? 'Dívidas menos o dinheiro disponível. Aqui é negativa: a empresa poderia quitar tudo o que deve e ainda sobraria esse valor.'
              : 'Dívidas menos o dinheiro disponível em caixa e aplicações — o que a empresa deve "de verdade".'}
          />
        )}
        <Metrica
          rotulo="EBITDA (aproximado)"
          valor={val(ebitda.valor_atual)}
          delta={ebitda.variacao_pct}
          anterior={ebitda.valor_anterior}
          ajuda="Aproximado: resultado operacional (DRE) + depreciação e amortização (DFC)"
          explicacao="Quanto a operação do negócio gera de resultado, antes de juros, impostos e do desgaste de máquinas e equipamentos (depreciação)."
        />
      </section>

      {/* Resumo executivo */}
      {secoes['RESUMO'] && (
        <section className="cartao destaque">
          <h2><span className="icone-secao"><FileText size={16} /></span> Resumo Executivo</h2>
          <Texto>{secoes['RESUMO']}</Texto>
        </section>
      )}

      {/* Faturamento | Lucro | Caixa */}
      <section className="grade-3">
        {[
          [Banknote, 'O Que a Empresa Fatura', 'O QUE A EMPRESA FATURA'],
          [TrendingUp, 'Lucro do Período', 'LUCRO'],
          [Landmark, 'Caixa e Dívidas', 'SAUDE DO CAIXA E DIVIDAS'],
        ].map(([Icone, titulo, chave]) => (
          <div className="cartao" key={chave}>
            <h3><span className="icone-secao"><Icone size={16} /></span> {titulo}</h3>
            {secoes[chave]
              ? <Texto>{secoes[chave]}</Texto>
              : <p className="vazio">Informação não disponível neste relatório.</p>}
          </div>
        ))}
      </section>

      {/* Positivo | Atenção */}
      <section className="grade-2">
        <div className="cartao positivo">
          <h3><span className="icone-secao"><CircleCheck size={16} /></span> O Que Foi Positivo</h3>
          {secoes['O QUE FOI POSITIVO']
            ? <Texto>{secoes['O QUE FOI POSITIVO']}</Texto>
            : <p className="vazio">Não identificados com os dados disponíveis.</p>}
        </div>
        <div className="cartao atencao">
          <h3><span className="icone-secao"><TriangleAlert size={16} /></span> O Que Merece Atenção</h3>
          {secoes['O QUE MERECE ATENCAO']
            ? <Texto>{secoes['O QUE MERECE ATENCAO']}</Texto>
            : <p className="vazio">Não identificados com os dados disponíveis.</p>}
        </div>
      </section>

      {/* Limitações */}
      <details className="cartao limitacoes">
        <summary><Info size={17} /> Limitações desta Análise</summary>
        <Texto>{secoes['LIMITACOES DESTA ANALISE'] || 'Nenhuma limitação identificada.'}</Texto>
      </details>

      {/* Auditoria de fidelidade numérica */}
      <Auditoria
        auditoria={analise.auditoria}
        linkCvm={resultado.documento?.link}
        ticker={ticker}
        periodo={periodo}
        tipoDoc={tipoDoc}
      />

      {/* Download PDF */}
      <div className="acoes">
        <button className="botao-pdf" onClick={aoBaixarPdf} disabled={gerandoPdf}>
          {gerandoPdf
            ? <><LoaderCircle size={16} className="girando" /> Gerando PDF…</>
            : <><Download size={16} /> Baixar análise completa (.pdf)</>}
        </button>
        {erroPdf && <span className="erro-inline">{erroPdf}</span>}
      </div>
    </div>
  )
}

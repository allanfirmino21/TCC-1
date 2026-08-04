// TelaInicial — boas-vindas editorial exibida antes da primeira análise

import { Download, FileSearch, Boxes, Sparkles, PenLine } from 'lucide-react'

const PASSOS = [
  [Download, 'Busca', 'o relatório ITR/DFP mais recente da empresa na CVM'],
  [FileSearch, 'Extrai', 'as demonstrações financeiras e calcula as métricas em código'],
  [Boxes, 'Indexa', 'os dados com embeddings multilíngues (RAG)'],
  [PenLine, 'Escreve', 'uma análise em linguagem simples com o Gemini 2.5 Flash'],
  [Sparkles, 'Audita', 'cada número citado contra o documento oficial da CVM'],
]

const EXEMPLOS = [
  ['WEGE3', 'WEG S.A.'],
  ['ITUB4', 'Itaú Unibanco'],
  ['PETR4', 'Petrobras'],
  ['VALE3', 'Vale S.A.'],
  ['POMO4', 'Marcopolo'],
  ['BBAS3', 'Banco do Brasil'],
]

export default function TelaInicial({ aoEscolherExemplo }) {
  return (
    <div className="tela-inicial">
      <h1>
        O balanço da empresa, <em>explicado em português claro</em> — e conferido
        número por número.
      </h1>
      <p className="subtitulo">
        Digite o código de uma ação da B3 ao lado e receba uma análise
        fundamentalista dos dados oficiais da CVM, com selo de auditoria numérica.
      </p>

      <div className="grade-2 inicial">
        <div className="cartao">
          <h3>Como funciona</h3>
          <ol className="passos">
            {PASSOS.map(([Icone, verbo, resto]) => (
              <li key={verbo}>
                <span className="passo-icone"><Icone size={15} /></span>
                <span><strong>{verbo}</strong> {resto}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="cartao">
          <h3>Experimente uma empresa</h3>
          <div className="exemplos">
            {EXEMPLOS.map(([tk, nome]) => (
              <button key={tk} className="exemplo" onClick={() => aoEscolherExemplo(tk)}>
                <code>{tk}</code>
                <span>{nome}</span>
              </button>
            ))}
          </div>
          <p className="dica">
            Qualquer empresa listada na B3 com código CVM pode ser analisada.
          </p>
        </div>
      </div>

      <p className="rodape-aviso">
        Fonte dos dados: CVM Open Data · Este sistema não constitui recomendação de investimento.
      </p>
    </div>
  )
}

// Progresso — linha do tempo das etapas do pipeline transmitidas via SSE

import { CircleCheck, LoaderCircle } from 'lucide-react'

export default function Progresso({ eventos, rodando }) {
  return (
    <div className="cartao progresso">
      <div className="progresso-cabecalho">
        <h2>{rodando ? 'Executando pipeline…' : 'Pipeline'}</h2>
      </div>
      <ol>
        {eventos.map((ev, i) => {
          const ultimo = i === eventos.length - 1
          const atual = ultimo && rodando
          return (
            <li key={i} className={atual ? 'atual' : ''}>
              <span className="icone-passo">
                {atual
                  ? <LoaderCircle size={15} className="girando" />
                  : <CircleCheck size={15} />}
              </span>
              <span className="etapa-chip">{ev.etapa}</span>
              <span>{ev.msg}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

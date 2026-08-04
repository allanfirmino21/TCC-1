// App — orquestra o estado da aplicação: formulário → progresso SSE → resultado

import { useEffect, useRef, useState } from 'react'
import { consultarStatus, analisar } from './api'
import Sidebar from './components/Sidebar'
import Progresso from './components/Progresso'
import Analise from './components/Analise'
import TelaInicial from './components/TelaInicial'

export default function App() {
  const [ticker, setTicker] = useState('WEGE3')
  const [tipo, setTipo] = useState('ITR')
  const [forcar, setForcar] = useState(false)

  // Tema claro/escuro: persiste no localStorage; padrão segue o sistema
  const [tema, setTema] = useState(() =>
    localStorage.getItem('fundia-tema') ||
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro'),
  )
  useEffect(() => {
    document.documentElement.dataset.tema = tema
    localStorage.setItem('fundia-tema', tema)
  }, [tema])

  const [apiOk, setApiOk] = useState(null)          // null = verificando
  const [rodando, setRodando] = useState(false)
  const [eventos, setEventos] = useState([])        // log de progresso
  const [resultado, setResultado] = useState(null)
  const [erro, setErro] = useState(null)
  const esRef = useRef(null)

  // Verifica a saúde da API ao carregar
  useEffect(() => {
    consultarStatus()
      .then((s) => setApiOk(s.api_key_configurada))
      .catch(() => setApiOk(false))
  }, [])

  // Fecha o SSE se o componente for desmontado no meio de uma análise
  useEffect(() => () => esRef.current?.close(), [])

  const aoAnalisar = () => {
    setRodando(true)
    setEventos([])
    setResultado(null)
    setErro(null)

    esRef.current = analisar(ticker, tipo, forcar, {
      aoProgresso: (etapa, msg) =>
        setEventos((prev) => [...prev, { etapa, msg }]),
      aoResultado: (res) => {
        setResultado(res)
        setRodando(false)
      },
      aoErro: (msg) => {
        setErro(msg)
        setRodando(false)
      },
    })
  }

  const aoEscolherExemplo = (tk) => setTicker(tk)

  return (
    <div className="layout">
      <Sidebar
        ticker={ticker} setTicker={setTicker}
        tipo={tipo} setTipo={setTipo}
        forcar={forcar} setForcar={setForcar}
        apiOk={apiOk} rodando={rodando}
        aoAnalisar={aoAnalisar}
        tema={tema} setTema={setTema}
      />

      <main className="conteudo">
        {erro && (
          <div className="alerta-erro">
            <strong>Erro na análise:</strong> {erro}
          </div>
        )}

        {(rodando || (eventos.length > 0 && !resultado && !erro)) && (
          <Progresso eventos={eventos} rodando={rodando} />
        )}

        {resultado && <Analise resultado={resultado} />}

        {!rodando && !resultado && !erro && (
          <TelaInicial aoEscolherExemplo={aoEscolherExemplo} />
        )}
      </main>
    </div>
  )
}

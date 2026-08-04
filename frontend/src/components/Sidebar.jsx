// Sidebar — formulário de análise, seletor de tema e status da API

import { ChartLine, Search, Sun, Moon, KeyRound, TriangleAlert, LoaderCircle } from 'lucide-react'

export default function Sidebar({
  ticker, setTicker, tipo, setTipo, forcar, setForcar,
  apiOk, rodando, aoAnalisar, tema, setTema,
}) {
  const podeAnalisar = apiOk && ticker.trim().length >= 5 && !rodando

  return (
    <aside className="sidebar">
      <div className="sidebar-topo">
        <div className="logo">
          <span className="logo-tile"><ChartLine size={20} strokeWidth={2.2} /></span>
          <div>
            <h1>fundIA</h1>
            <p>Análise fundamentalista via RAG + IA</p>
          </div>
        </div>
        <button
          className="toggle-tema"
          onClick={() => setTema(tema === 'escuro' ? 'claro' : 'escuro')}
          title={tema === 'escuro' ? 'Mudar para tema claro' : 'Mudar para tema escuro'}
          aria-label="Alternar tema"
        >
          {tema === 'escuro' ? <Sun size={17} /> : <Moon size={17} />}
        </button>
      </div>

      <div className="campo">
        <label htmlFor="ticker">Ticker da empresa</label>
        <input
          id="ticker"
          type="text"
          maxLength={6}
          placeholder="Ex: WEGE3"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().trim())}
          onKeyDown={(e) => { if (e.key === 'Enter' && podeAnalisar) aoAnalisar() }}
          disabled={rodando}
        />
        <span className="dica">Código da ação na B3 (ex.: WEGE3, B3SA3)</span>
      </div>

      <div className="campo">
        <label>Tipo de relatório</label>
        <div className="segmentado" role="radiogroup">
          {['ITR', 'DFP'].map((t) => (
            <button
              key={t}
              type="button"
              role="radio"
              aria-checked={tipo === t}
              className={tipo === t ? 'ativo' : ''}
              onClick={() => setTipo(t)}
              disabled={rodando}
            >
              {t}
            </button>
          ))}
        </div>
        <span className="dica">ITR = trimestral · DFP = anual</span>
      </div>

      <label className="checkbox">
        <input
          type="checkbox"
          checked={forcar}
          onChange={(e) => setForcar(e.target.checked)}
          disabled={rodando}
        />
        <span>Forçar novo download</span>
      </label>

      <div className={`badge-api ${apiOk === true ? 'ok' : apiOk === false ? 'falha' : ''}`}>
        {apiOk === null && <><LoaderCircle size={14} className="girando" /> Verificando API...</>}
        {apiOk === true && <><KeyRound size={14} /> GEMINI_API_KEY configurada</>}
        {apiOk === false && <><TriangleAlert size={14} /> API indisponível ou sem chave</>}
      </div>

      <button className="botao-analisar" onClick={aoAnalisar} disabled={!podeAnalisar}>
        {rodando
          ? <><LoaderCircle size={17} className="girando" /> Analisando…</>
          : <><Search size={17} /> Analisar</>}
      </button>

      <footer>
        <p><strong>Dados:</strong> CVM Open Data</p>
        <p><strong>LLM:</strong> Gemini 2.5 Flash</p>
        <p><strong>Embeddings:</strong> mpnet multilingual</p>
        <p><strong>Vetores:</strong> ChromaDB</p>
      </footer>
    </aside>
  )
}

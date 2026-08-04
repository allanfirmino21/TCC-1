// api.js — comunicação com o backend FastAPI (proxy /api → localhost:8000)

/** Consulta se a GEMINI_API_KEY está configurada no servidor. */
export async function consultarStatus() {
  const resp = await fetch('/api/status')
  if (!resp.ok) throw new Error(`API respondeu ${resp.status}`)
  return resp.json()
}

/**
 * Roda o pipeline de análise via Server-Sent Events.
 * Retorna a EventSource (para permitir cancelamento).
 *
 * callbacks: { aoProgresso(etapa, msg), aoResultado(dict), aoErro(msg) }
 */
export function analisar(ticker, tipo, forcar, { aoProgresso, aoResultado, aoErro }) {
  const params = new URLSearchParams({ ticker, tipo, forcar: String(forcar) })
  const es = new EventSource(`/api/analisar?${params}`)
  let terminou = false

  es.addEventListener('progresso', (e) => {
    const { etapa, msg } = JSON.parse(e.data)
    aoProgresso(etapa, msg)
  })

  es.addEventListener('resultado', (e) => {
    terminou = true
    es.close()
    aoResultado(JSON.parse(e.data))
  })

  es.addEventListener('erro', (e) => {
    terminou = true
    es.close()
    aoErro(JSON.parse(e.data).erro)
  })

  // Queda de conexão (o SSE fecha naturalmente após o fim do stream;
  // só é erro se ainda não recebemos resultado nem erro do pipeline)
  es.onerror = () => {
    if (!terminou) {
      terminou = true
      es.close()
      aoErro('Conexão com o servidor perdida. Verifique se a API está rodando (porta 8000).')
    }
  }

  return es
}

/** Baixa o PDF da análise gerado pelo backend. */
export async function baixarPdf({ empresa, ticker, periodo, tipoDoc, secoes }) {
  const resp = await fetch('/api/pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ empresa, ticker, periodo, tipo_doc: tipoDoc, secoes }),
  })
  if (!resp.ok) throw new Error(`Falha ao gerar PDF (${resp.status})`)
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `fundia_${ticker}_${periodo}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

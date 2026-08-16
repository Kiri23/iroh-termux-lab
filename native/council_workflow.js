/**
 * council_workflow.js — el council NATIVO (sin iroh).
 *
 * Equivalente 1:1 de `python/council_aggregator.py` usando el tool `Workflow` de
 * Claude Code: mismo fan-out Self-MoA, mismo prompt de síntesis, misma tolerancia
 * a fallo. Se corre desde una sesión de Claude Code, no desde la terminal:
 *
 *     Workflow({ scriptPath: "native/council_workflow.js" })
 *
 * NATIVO = los workers son subagentes in-process de la misma sesión. NO hay
 * transporte: desaparecen el ticket, la clave pública, el ALPN
 * `pi-agents/mailbox/0` y el `asyncio.sleep(1)` de `council_worker.py:48`. Todo
 * ese trabajo existía para llegar al otro proceso; acá no hay otro proceso.
 *
 * QUÉ SE PIERDE contra la versión iroh (por eso esto NO reemplaza el lab):
 *   - cross-device — no hay worker en el Mac ni en el VPS; es intra-sesión.
 *   - brain intercambiable — el seam de `brains.py` desaparece. Nativo solo corre
 *     Claude; `opts.model` cambia de tier, no de harness. PiBrain no entra acá.
 *   - sandbox real — `--disallowedTools` no está expuesto por invocación; lo de
 *     abajo es una aproximación por prompt (pedirle que no llame tools).
 *   - event-stream JSONL — hay `log()` y `/workflows`, pero no el JSONL que
 *     consume la UI de local-tools por SSE.
 *
 * QUÉ SE GANA: ~40 líneas contra 137, y cero proceso ocupando RAM esperando.
 *
 * Corrida de referencia (2026-08-16, Pixel): 4 agentes, 0 errores, 3/3 workers
 * respondieron, 20.8s. Hallazgo: los 3 candidatos convergieron casi al mismo
 * texto — Self-MoA con un solo harness tiene poca varianza que fundir, y la
 * síntesis termina siendo unión y no corrección. Es evidencia A FAVOR del seam
 * de `brains.py`: el patrón rinde cuando los brains difieren de verdad.
 */

export const meta = {
  name: 'council-native',
  description: 'Self-MoA nativo: fan-out a N workers + sintesis — equivalente de council_aggregator.py sin iroh',
  phases: [
    { title: 'Fan-out', detail: 'N workers responden el MISMO prompt, en paralelo' },
    { title: 'Sintesis', detail: 'un brain funde los candidatos en el veredicto' },
  ],
}

// Inline, NO via `args` — args serializa a string y revienta (.map is not a function).
const PROMPT = '¿Cuál es la diferencia real entre concurrencia y paralelismo? Respondé en menos de 120 palabras.'
const N_WORKERS = 3   // el aggregator validó 2 en Termux por RAM; nativo no tiene ese techo

// Espejo de brains.py ClaudeCliBrain(pure=True): texto in / texto out, sin tools.
// Approximación por prompt — nativo no expone --disallowedTools por invocación.
const workerPrompt = (p) =>
  `Respondé la siguiente pregunta del usuario. No llames ninguna tool. ` +
  `Tu texto final ES la respuesta, sin preámbulo.\n\n${p}`

// Verbatim de council_aggregator.py:65-76
const buildSynthPrompt = (p, cands) => {
  const blocks = cands.map((t, i) => `[Respuesta ${i + 1}]\n${t}`).join('\n\n')
  return (
    'Has recibido las respuestas de varios modelos al MISMO prompt del usuario. ' +
    'Sintetiza UNA sola respuesta final de la mejor calidad: corrige errores, ' +
    'combina lo más fuerte de cada una, y descarta lo flojo. No menciones que ' +
    'hubo varios modelos ni el proceso.\n\n' +
    `=== PROMPT ORIGINAL ===\n${p}\n\n` +
    `=== RESPUESTAS A SINTETIZAR ===\n${blocks}\n\n` +
    '=== RESPUESTA FINAL ==='
  )
}

phase('Fan-out')
log(`council: ${N_WORKERS} workers · prompt: ${JSON.stringify(PROMPT)}`)

// BARRIER justificado: la sintesis necesita TODOS los candidatos a la vez.
// parallel() resuelve a null el thunk que muere == el `ok: False` del aggregator.
const raw = await parallel(
  Array.from({ length: N_WORKERS }, (_, i) => () =>
    agent(workerPrompt(PROMPT), { label: `w${i + 1}`, phase: 'Fan-out' }))
)

const candidates = raw.filter(Boolean).map(t => String(t).trim()).filter(t => t.length)
// Contá el artefacto, no el plan: dispatched != respondidos.
log(`candidatos: ${candidates.length}/${N_WORKERS} respondieron`)
if (candidates.length < N_WORKERS) {
  log(`⚠️  ${N_WORKERS - candidates.length} worker(s) murieron y fueron dropeados`)
}

if (!candidates.length) {
  return { n_dispatched: N_WORKERS, n_candidates: 0, verdict: '', error: 'ningún worker respondió' }
}

phase('Sintesis')
log(`sintetizando veredicto de ${candidates.length} candidatos…`)
const verdict = await agent(buildSynthPrompt(PROMPT, candidates), { label: 'synth', phase: 'Sintesis' })

return { n_dispatched: N_WORKERS, n_candidates: candidates.length, candidates, verdict }

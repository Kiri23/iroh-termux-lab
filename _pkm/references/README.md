# references/ — artefactos visuales del council

HTML self-contained (un archivo cada uno, sin deps) generados por Claude para
entender este repo. Abrilos con `termux-open --content-type text/html <file>`.
Son **referencias**, no atomic notes — el rationale atómico vive en `../atomic/`.

- `iroh-council-codebase-map.html` — **mapa del codebase**. Qué ES el repo y cómo
  funciona, para alguien que NO lo escribió (fue vibe-codeado por una sesión de AI).
  Puentea de lo conocido → lo desconocido (Tailscale→iroh, engine/transport→brain/iroh,
  "pregunto a varios"→Self-MoA), mapa de archivos (quién llama a quién), el flujo de
  eventos JSONL paso a paso, las dos topologías (star/chain), diccionario de términos,
  y cómo correrlo. **Empezá por acá si no conocés el repo.**

- `iroh-council-blindspots.html` — **blindspot pass**. 12 unknown-unknowns del PoC
  (supuestos silenciosos, no bugs del happy-path): brain default sin sandbox expuesto a
  red, `claude -p` nietos huérfanos → OOM, cero timeouts, `~/tmp` hardcodeado rompe la
  portabilidad prometida, `--brain` global sin heterogeneidad, relay público como egress,
  degradación silenciosa en chain, cobertura de tests, etc. Ordenados por lo que más
  costaría descubrir solo. Incluye cómo prompteármelo mejor.

Generados 2026-07-05 · branch council-poc.

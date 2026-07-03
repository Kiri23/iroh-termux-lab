---
Type: Atomic Note
Tags: [prompting, orchestration, multi-agent, llm-behavior, council]
Status: active
derivedFrom:
  - [[2026-07-03-council-self-moa-iroh]]
---

# El framing del prompt de orquestación es parte del diseño

El wording con el que el orquestador arma el prompt de cada nodo **cambia el comportamiento del nodo**, no es plumbing neutral.

Evidencia (prueba de fusión del council): etiquetar el dato de un nodo como `[Contexto privado, solo para ti]`, o la tarea como *"código de acceso / código secreto"*, hizo que Claude (sandbox) **se negara a compartir** su fragmento — lo trató como una credencial a proteger (*"hacerlo exigiría filtrar un secreto marcado como privado"*). Reformular a *"ejercicio de concatenación de strings, nada sensible"* → cooperó.

Lección: el prompt del orquestador es una **superficie de diseño** que puede disparar rechazos de seguridad o cooperación. Al construir sistemas multi-agente, el framing es tan parte del engine como la topología. Hermano de [[credit-assignment-solo-con-contribuciones-disjuntas]] (ambos salieron de hacer *verificable* la fusión).

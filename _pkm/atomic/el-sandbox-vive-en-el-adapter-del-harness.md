---
Type: Atomic Note
Tags: [engine-transport, harness, sandbox, adapter, multi-agent, council]
Status: active
derivedFrom:
  - [[2026-07-03-council-self-moa-iroh]]
---

# El sandbox vive en el adapter del harness, no en el transporte

Un nodo del council cuyo brain es un agente completo (`claude -p` con Bash/Read) **filtra contexto por el filesystem/process-table**: leyó el archivo del test y el `ps`, y se enteró del token del otro nodo **sin pasar por iroh**. El transporte nunca fue el leak.

Las capacidades/sandbox pertenecen al **adapter del brain**, no al canal: `claude-pure` = `--disallowedTools` lo vuelve una función de texto pura, y entonces el único canal de contexto es el prompt que le mandas.

Por eso el harness debe ser una **interfaz inyectada** (`NodeBrain`): el adapter es donde se hace cumplir el aislamiento. Corolario del engine/transport: el transporte mueve bytes; qué puede *tocar* el nodo es propiedad del engine del nodo. Ver [[hexagonal-ports-adapters es el nombre del engine-transport]] y [[Un sandbox de seguridad debe replicar las condiciones reales]].

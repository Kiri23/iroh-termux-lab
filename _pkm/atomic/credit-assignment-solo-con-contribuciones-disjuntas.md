---
Type: Atomic Note
Tags: [credit-assignment, dag, multi-agent, moa, evaluation, council]
Status: active
derivedFrom:
  - [[2026-07-03-council-self-moa-iroh]]
---

# Credit assignment solo es demostrable con contribuciones disjuntas e infalsificables

Para *saber* que el sintetizador de un council usó info del nodo A **y** del nodo B, no sirve inspeccionar el texto: con contenido solapado (mismo modelo dice casi lo mismo) o flujo transitivo (en `chain`, B ya absorbió a A), la procedencia es **irrecuperable**. El verdicto puede verse 90% de un nodo y no probar nada.

La única prueba: darle a cada nodo un **token único, disjunto e infalsificable**. Si el veredicto contiene ambos, solo quien vio los dos pudo producirlo. Topología `star` (nodos aislados) + brain sandbox aísla el crédito al sintetizador; `chain` prueba comunicación inter-nodo.

Generaliza: **credit assignment sobre cualquier DAG necesita señales separables.** Contenido natural solapado ⇒ procedencia fundamentalmente indemostrable por inspección. Es [[DAG credit assignment como patron computacional unificador]] con su condición de validez explícita.

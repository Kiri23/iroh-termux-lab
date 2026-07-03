"""Council run — orquestador. Un council = DAG(nodos, edges) + brain enchufable.

Spawnea N nodos (cada uno `council_worker.py` = transporte iroh + brain), los
recorre según la TOPOLOGÍA, sintetiza el veredicto y limpia. Emite todo como
JSONL — el contrato que la UI (iroh.localhost) consume por SSE, y que
`council_test.py` assertea.

    python council_run.py --workers 2 "prompt"
    python council_run.py --topology chain --roles "sabe A" "sabe B" "prompt"
    python council_run.py --brain echo --dry-run "prompt"     # gratis (tests)

Topologías (opt-in, mismo engine, distinto set de edges):
  · star  (default): nodos independientes en paralelo → synth ve todos.  (Hermes)
  · chain           : nodo1 → nodo2 → … cada uno ve la salida del anterior. (DAG)

Eventos: start · worker_up · flow · dial · candidate · synth_start · verdict · worker_down · error
"""
import argparse
import asyncio
import json
import os
import re
import sys
import tempfile

import iroh

import council_aggregator as agg
from brains import get_brain

WORKDIR = os.path.dirname(os.path.abspath(__file__))
TICKET_RE = re.compile(r"^TICKET:\s*(\S+)", re.M)


def emit(ev: dict):
    print(json.dumps(ev, ensure_ascii=False), flush=True)


# ── Construcción del prompt de un nodo (base + su rol privado + contexto upstream) ──
def node_prompt(base: str, role: str, upstream: list) -> str:
    parts = [base]
    if role:
        parts.append(f"[Tu contexto asignado]: {role}")
    if upstream:
        prev = "\n".join(f"- {u['worker']}: {u['text']}" for u in upstream)
        parts.append(f"[Salidas de nodos previos — construye sobre ellas]:\n{prev}")
    return "\n\n".join(parts)


def role_of(roles: list, i: int) -> str:
    return roles[i].strip() if i < len(roles) and roles[i].strip() else ""


# ── Levantar un nodo ────────────────────────────────────────────────
async def spawn_worker(idx: int, brain: str):
    """Lanza council_worker.py con su brain, espera su TICKET (vía logfile)."""
    label = f"w{idx}"
    fd, logpath = tempfile.mkstemp(suffix=f"-{label}.log", dir=os.path.expanduser("~/tmp"))
    fout = os.fdopen(fd, "w")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "council_worker.py", "--brain", brain,
        stdout=fout, stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL, cwd=WORKDIR,
    )
    fout.close()  # el hijo tiene su propio fd dup

    ticket = None
    for _ in range(40):
        if proc.returncode is not None:
            break
        m = TICKET_RE.search(open(logpath).read())
        if m:
            ticket = m.group(1)
            break
        await asyncio.sleep(1)

    if not ticket:
        emit({"type": "error", "worker": label, "msg": "worker no dio ticket en 40s"})
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        return None

    pubkey = str(iroh.EndpointTicket.from_string(ticket).endpoint_addr().id())
    emit({"type": "worker_up", "worker": label, "pubkey": pubkey})
    return {"label": label, "ticket": ticket, "pubkey": pubkey, "proc": proc, "log": logpath}


# ── Recorridos del DAG (una función por topología) ──────────────────
async def fan_star(ep, workers, base, roles):
    """Nodos independientes, en paralelo. Ningún nodo ve a otro."""
    return await asyncio.gather(*(
        agg.ask_worker(ep, i + 1, w["ticket"], node_prompt(base, role_of(roles, i), []))
        for i, w in enumerate(workers)
    ))


async def fan_chain(ep, workers, base, roles):
    """Cadena: cada nodo recibe (por iroh) las salidas de los nodos previos."""
    results, upstream = [], []
    for i, w in enumerate(workers):
        if upstream:
            emit({"type": "flow", "frm": upstream[-1]["worker"], "to": w["label"]})
        prompt = node_prompt(base, role_of(roles, i), upstream)
        c = await agg.ask_worker(ep, i + 1, w["ticket"], prompt)
        results.append(c)
        if c["ok"] and c["text"]:
            upstream.append(c)
    return results


TOPOLOGIES = {"star": fan_star, "chain": fan_chain}


async def main():
    ap = argparse.ArgumentParser(description="Council run — DAG de nodos + brain enchufable")
    ap.add_argument("prompt")
    ap.add_argument("--workers", type=int, default=2, help="N nodos (2 seguro en Termux)")
    ap.add_argument("--topology", choices=list(TOPOLOGIES), default="star")
    ap.add_argument("--brain", default="claude", help="claude | claude-pure | echo")
    ap.add_argument("--roles", nargs="*", default=[], help="contexto privado por nodo (roles[i]→nodo i)")
    ap.add_argument("--dry-run", action="store_true", help="atajo de --brain echo (gratis, tests)")
    ap.add_argument("--json", action="store_true", help="(siempre emite JSONL)")
    args = ap.parse_args()

    brain_name = "echo" if args.dry_run else args.brain
    agg.JSON_MODE = True  # que ask_worker también emita JSONL al mismo stdout
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    emit({"type": "start", "prompt": args.prompt, "n_workers": args.workers,
          "topology": args.topology, "brain": brain_name})

    workers = []
    for i in range(1, args.workers + 1):
        w = await spawn_worker(i, brain_name)
        if w:
            workers.append(w)
    if not workers:
        emit({"type": "verdict", "text": "", "error": "ningún nodo levantó"})
        return

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    try:
        candidates = await TOPOLOGIES[args.topology](ep, workers, args.prompt, args.roles)
        good = [c for c in candidates if c["ok"] and c["text"]]
        if not good:
            emit({"type": "verdict", "text": "", "error": "ningún nodo respondió"})
        else:
            emit({"type": "synth_start", "n_candidates": len(good)})
            verdict = await agg.synthesize(args.prompt, good, get_brain(brain_name))
            emit({"type": "verdict", "text": verdict})
    finally:
        await ep.close()
        for w in workers:
            try:
                w["proc"].terminate()
            except ProcessLookupError:
                pass
            try:
                os.unlink(w["log"])
            except OSError:
                pass
            emit({"type": "worker_down", "worker": w["label"]})


if __name__ == "__main__":
    asyncio.run(main())

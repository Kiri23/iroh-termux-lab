"""Council run — orquestador all-in-one para la UI.

Un solo comando que: (1) spawnea N `council_worker.py`, captura sus tickets y
emite `worker_up` por cada uno; (2) hace fan-out del prompt a todos (reusa
`council_aggregator.ask_worker`); (3) sintetiza el veredicto; (4) mata los
workers al final. Emite TODO como JSONL por stdout — el contrato que la UI de
local-tools (iroh.localhost) consume por SSE.

    python council_run.py --workers 2 "tu prompt"

Eventos: start · worker_up · dial · candidate · synth_start · verdict · worker_down · error

Este es el ENGINE (vive en el repo iroh). La UI es puro transporte: shell-out a
este script + stream de sus líneas. En el futuro los workers pueden vivir en el
Mac/VPS (mismo código, otro ticket) sin tocar ni la UI ni este orquestador.
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

WORKDIR = os.path.dirname(os.path.abspath(__file__))
TICKET_RE = re.compile(r"^TICKET:\s*(\S+)", re.M)


def emit(ev: dict):
    print(json.dumps(ev, ensure_ascii=False), flush=True)


async def spawn_worker(idx: int):
    """Lanza un council_worker.py, espera su TICKET (vía logfile, sin deadlock de pipe)."""
    label = f"w{idx}"
    fd, logpath = tempfile.mkstemp(suffix=f"-{label}.log",
                                   dir=os.path.expanduser("~/tmp"))
    fout = os.fdopen(fd, "w")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "council_worker.py",
        stdout=fout, stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL, cwd=WORKDIR,
    )
    fout.close()  # el hijo tiene su propio fd dup; sigue escribiendo

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
    return {"label": label, "ticket": ticket, "pubkey": pubkey,
            "proc": proc, "log": logpath}


async def main():
    ap = argparse.ArgumentParser(description="Council run (orquestador para la UI)")
    ap.add_argument("prompt")
    ap.add_argument("--workers", type=int, default=2,
                    help="cuántos workers (default 2; 3+ arriesga OOM en Termux)")
    ap.add_argument("--json", action="store_true", help="(siempre emite JSONL)")
    args = ap.parse_args()

    agg.JSON_MODE = True  # que ask_worker también emita JSONL al mismo stdout
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    emit({"type": "start", "prompt": args.prompt, "n_workers": args.workers})

    workers = []
    for i in range(1, args.workers + 1):
        w = await spawn_worker(i)
        if w:
            workers.append(w)

    if not workers:
        emit({"type": "verdict", "text": "", "error": "ningún worker levantó"})
        return

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    try:
        candidates = await asyncio.gather(
            *(agg.ask_worker(ep, i + 1, w["ticket"], args.prompt)
              for i, w in enumerate(workers))
        )
        good = [c for c in candidates if c["ok"] and c["text"]]
        if not good:
            emit({"type": "verdict", "text": "", "error": "ningún worker respondió"})
        else:
            emit({"type": "synth_start", "n_candidates": len(good)})
            verdict = await agg.synthesize(args.prompt, good)
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

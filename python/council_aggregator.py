"""Council aggregator — Self-MoA sobre iroh.

Fan-out de un prompt a N workers (cada uno un `claude -p` detrás de una clave
pública, `council_worker.py`), junta los candidatos en paralelo, y corre un
`claude -p` final que SINTETIZA el veredicto (patrón Mixture-of-Agents).

    python council_aggregator.py --tickets tickets.txt "tu prompt"
    python council_aggregator.py --json  --tickets tickets.txt "tu prompt"

`--json` emite un event-stream JSONL por stdout (dial / candidate / synth /
verdict) — el contrato que consume la UI en local-tools (iroh.localhost) por SSE.
Sin --json, imprime legible para humanos.

FULL IROH: los workers pueden estar en este device o en el Mac/VPS; el ticket es
lo único que cambia. Este aggregator no sabe ni le importa dónde viven.
"""
import argparse
import asyncio
import json
import os
import sys

import iroh

from brains import get_brain

ALPN = b"pi-agents/mailbox/0"
MAX = 1 << 20

JSON_MODE = False


def emit(ev: dict, human: str = None):
    """Un evento → JSONL (para la UI) o línea legible (para la terminal)."""
    if JSON_MODE:
        print(json.dumps(ev, ensure_ascii=False), flush=True)
    elif human is not None:
        print(human, flush=True)


async def ask_worker(ep, idx: int, ticket_str: str, prompt: str) -> dict:
    """Marca a un worker por su ticket, manda el prompt, devuelve su candidato."""
    label = f"w{idx}"
    try:
        ticket = iroh.EndpointTicket.from_string(ticket_str.strip())
        addr = ticket.endpoint_addr()
        pubkey = str(addr.id())
        emit({"type": "dial", "worker": label, "pubkey": pubkey},
             f"→ [{label}] marcando a {pubkey[:16]}…")
        conn = await ep.connect(addr, ALPN)
        bi = await conn.open_bi()
        send, recv = bi.send(), bi.recv()
        await send.write_all(prompt.encode("utf8"))
        await send.finish()
        text = (await recv.read_to_end(MAX)).decode("utf8").strip()
        emit({"type": "candidate", "worker": label, "pubkey": pubkey, "text": text},
             f"← [{label}] candidato ({len(text)} chars):\n{text}\n")
        return {"worker": label, "pubkey": pubkey, "text": text, "ok": True}
    except Exception as e:  # un worker caído no tumba el council
        emit({"type": "error", "worker": label, "msg": str(e)},
             f"✗ [{label}] error: {e}")
        return {"worker": label, "text": "", "ok": False}


def build_synth_prompt(prompt: str, candidates: list) -> str:
    blocks = "\n\n".join(f"[Respuesta {i+1}]\n{c['text']}"
                         for i, c in enumerate(candidates))
    return (
        "Has recibido las respuestas de varios modelos al MISMO prompt del "
        "usuario. Sintetiza UNA sola respuesta final de la mejor calidad: "
        "corrige errores, combina lo más fuerte de cada una, y descarta lo "
        "flojo. No menciones que hubo varios modelos ni el proceso.\n\n"
        f"=== PROMPT ORIGINAL ===\n{prompt}\n\n"
        f"=== RESPUESTAS A SINTETIZAR ===\n{blocks}\n\n"
        "=== RESPUESTA FINAL ==="
    )


async def synthesize(prompt: str, candidates: list, brain) -> str:
    """Aggregator layer: el brain funde los candidatos en el veredicto.

    La síntesis es otro `brain.think()` — mismo harness que los nodos, sobre el
    prompt de agregación. No sabe de claude: recibe el brain inyectado.
    """
    return await brain.think(build_synth_prompt(prompt, candidates))


def load_tickets(args) -> list:
    if args.tickets:
        with open(os.path.expanduser(args.tickets)) as f:
            return [ln for ln in (l.strip() for l in f) if ln]
    return args.inline_tickets


async def main():
    global JSON_MODE
    ap = argparse.ArgumentParser(description="Council aggregator (Self-MoA sobre iroh)")
    ap.add_argument("prompt", help="prompt para el council")
    ap.add_argument("--tickets", help="archivo con un ticket por línea")
    ap.add_argument("--inline-tickets", nargs="*", default=[], help="tickets como args")
    ap.add_argument("--json", action="store_true", help="emitir JSONL para la UI")
    ap.add_argument("--brain", default="claude", help="brain de la síntesis")
    args = ap.parse_args()
    JSON_MODE = args.json

    tickets = load_tickets(args)
    if not tickets:
        print("no hay tickets (usa --tickets FILE o --inline-tickets ...)", file=sys.stderr)
        sys.exit(1)

    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())
    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    emit({"type": "start", "prompt": args.prompt, "n_workers": len(tickets),
          "aggregator_pubkey": str(ep.id())},
         f"council: {len(tickets)} workers · prompt: {args.prompt!r}\n")

    # Fan-out en paralelo (2 workers = concurrencia validada en Termux)
    candidates = await asyncio.gather(
        *(ask_worker(ep, i + 1, t, args.prompt) for i, t in enumerate(tickets))
    )
    good = [c for c in candidates if c["ok"] and c["text"]]
    if not good:
        emit({"type": "verdict", "text": "", "error": "ningún worker respondió"},
             "✗ ningún worker respondió")
        await ep.close()
        return

    emit({"type": "synth_start", "n_candidates": len(good)},
         f"⚙️  sintetizando veredicto de {len(good)} candidatos…\n")
    verdict = await synthesize(args.prompt, good, get_brain(args.brain))
    emit({"type": "verdict", "text": verdict},
         f"═══ VEREDICTO ═══\n{verdict}")
    await ep.close()


if __name__ == "__main__":
    asyncio.run(main())

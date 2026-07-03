"""Council worker — UN NODO: transporte iroh + un brain (harness-agnóstico).

Recibe un prompt por clave pública (QUIC), lo pasa al brain y devuelve la
respuesta por la misma bidi stream. El worker NO sabe qué harness corre adentro
— solo llama `brain.think()`. Ese es el seam del harness (engine del nodo);
iroh es el transporte entre nodos. Cambiar claude→PyPy = otro `--brain`, cero
cambios acá.

    python council_worker.py [--brain claude|claude-pure|echo]

FULL IROH: same-device y cross-device usan este mismo código; solo cambia dónde
lo lanzas. Imprime un TICKET que el orquestador captura.
"""
import argparse
import asyncio

import iroh

from brains import get_brain

ALPN = b"pi-agents/mailbox/0"
MAX = 1 << 20  # 1 MB por mensaje


async def serve(brain):
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=[ALPN]))
    print("council worker pubkey:", ep.id(), flush=True)
    print("TICKET:", str(iroh.EndpointTicket.from_addr(ep.addr())), flush=True)
    print(f"brain: {brain.name} · esperando prompts... (Ctrl-C para salir)", flush=True)

    while True:
        incoming = await ep.accept_next()
        if incoming is None:
            break
        conn = await (await incoming.accept()).connect()
        bi = await conn.accept_bi()
        recv, send = bi.recv(), bi.send()

        prompt = (await recv.read_to_end(MAX)).decode("utf8")
        print(f"← prompt ({len(prompt)} chars) → brain {brain.name}", flush=True)

        answer = await brain.think(prompt)

        await send.write_all(answer.encode("utf8"))
        await send.finish()
        await asyncio.sleep(1)  # gotcha iroh: mantener conn viva para que el peer lea


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default="claude",
                    help="claude | claude-pure (sandbox) | echo (canned, tests)")
    args = ap.parse_args()
    asyncio.run(serve(get_brain(args.brain)))


if __name__ == "__main__":
    main()

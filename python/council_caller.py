"""Council caller — marca a un worker-claude por su ticket y le manda un prompt.

    python council_caller.py <TICKET> "tu prompt"

El MISMO código sirve si el worker está en este device o en el Mac: iroh conecta
por clave pública (QUIC directo local, o relay/hole-punch remoto). Este caller es
el stub del AGGREGATOR — el siguiente paso es que él mismo sea un `claude -p` que
haga fan-out a N workers y sintetice el veredicto (Self-MoA).
"""
import asyncio
import sys

import iroh

ALPN = b"pi-agents/mailbox/0"
MAX = 1 << 20


async def main():
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    if len(sys.argv) < 2:
        print('uso: python council_caller.py <TICKET> "prompt"')
        sys.exit(1)
    ticket_str = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Di hola en exactamente 3 palabras."

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    print("caller pubkey:", ep.id(), flush=True)

    ticket = iroh.EndpointTicket.from_string(ticket_str)
    addr = ticket.endpoint_addr()
    print("marcando a", str(addr.id())[:16], "…", flush=True)

    conn = await ep.connect(addr, ALPN)
    bi = await conn.open_bi()
    send, recv = bi.send(), bi.recv()

    await send.write_all(prompt.encode("utf8"))
    await send.finish()
    print("prompt enviado:", repr(prompt[:80]), flush=True)

    reply = (await recv.read_to_end(MAX)).decode("utf8")
    print("\n← respuesta del worker-claude:\n", flush=True)
    print(reply, flush=True)
    await ep.close()


if __name__ == "__main__":
    asyncio.run(main())

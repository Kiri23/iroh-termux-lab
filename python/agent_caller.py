"""Agente PI "caller" — marca al worker por su clave pública (ticket) y le manda una tarea.

    python agent_caller.py <TICKET> "tu tarea"
"""
import asyncio
import sys
import iroh

ALPN = b"pi-agents/mailbox/0"


async def main():
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    if len(sys.argv) < 2:
        print("uso: python agent_caller.py <TICKET> [tarea]")
        sys.exit(1)
    ticket_str = sys.argv[1]
    task = sys.argv[2] if len(sys.argv) > 2 else "hola desde el agente caller"

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    print("caller public key:", ep.id())

    ticket = iroh.EndpointTicket.from_string(ticket_str)
    addr = ticket.endpoint_addr()
    print("marcando a", str(addr.id())[:16], "…")

    conn = await ep.connect(addr, ALPN)
    bi = await conn.open_bi()
    send, recv = bi.send(), bi.recv()

    await send.write_all(task.encode("utf8"))
    await send.finish()
    print("tarea enviada:", repr(task))

    reply = await recv.read_to_end(4096)
    print("← respuesta del worker:", reply.decode("utf8"))
    await ep.close()


if __name__ == "__main__":
    asyncio.run(main())

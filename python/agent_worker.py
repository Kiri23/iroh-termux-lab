"""Agente PI "worker" — escucha por iroh, procesa la tarea y responde.

Dos agentes Python comunicándose P2P por clave pública, NATIVO en Termux.
Levanta este primero:

    python agent_worker.py

Imprime un TICKET (clave pública + addrs + relay). Pásaselo al caller en otra terminal.
"""
import asyncio
import iroh

ALPN = b"pi-agents/mailbox/0"


async def main():
    # uniffi necesita el event loop de asyncio explícito.
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=[ALPN]))
    print("worker public key:", ep.id())
    ticket = iroh.EndpointTicket.from_addr(ep.addr())
    print("TICKET:", str(ticket))
    print("\n→ en otra terminal:\n    python agent_caller.py", str(ticket), '"tu tarea"\n')

    print("esperando agentes... (Ctrl-C para salir)")
    while True:
        incoming = await ep.accept_next()
        if incoming is None:
            break
        accepting = await incoming.accept()
        conn = await accepting.connect()
        peer = str(conn.remote_id())
        print(f"\n← conexión del agente {peer[:16]}…")

        bi = await conn.accept_bi()
        recv, send = bi.recv(), bi.send()

        data = await recv.read_to_end(4096)
        task = data.decode("utf8")
        print("   tarea recibida:", repr(task))

        result = f"[worker {ep.id()!s:.8}] procesé: {task.upper()}"
        await send.write_all(result.encode("utf8"))
        await send.finish()
        print("   respuesta enviada.")


if __name__ == "__main__":
    asyncio.run(main())

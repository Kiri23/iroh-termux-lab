"""Dos agentes PI (dos Endpoints iroh independientes, cada uno su keypair)
comunicándose por CLAVE PÚBLICA, nativo en Termux. Un solo proceso para una
demo determinista; el par worker/caller (agent_worker.py + agent_caller.py)
es la misma lógica en dos terminales separadas.
"""
import asyncio
import iroh

ALPN = b"pi-agents/mailbox/0"


async def run():
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    # Agente A — worker (acepta y procesa)
    a = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=[ALPN]))
    print("Agente A (worker) id:", str(a.id())[:16], flush=True)

    # Agente B — caller (marca por clave)
    b = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=None))
    print("Agente B (caller) id:", str(b.id())[:16], flush=True)

    a_addr = a.addr()  # la "dirección" de A (incluye su clave pública)

    async def worker_side():
        incoming = await a.accept_next()
        accepting = await incoming.accept()
        conn = await accepting.connect()
        print("  [A] conexión entrante de", str(conn.remote_id())[:16], flush=True)
        bi = await conn.accept_bi()
        recv, send = bi.recv(), bi.send()
        task = (await recv.read_to_end(4096)).decode("utf8")
        print("  [A] tarea recibida:", repr(task), flush=True)
        await send.write_all(f"procesé: {task.upper()}".encode("utf8"))
        await send.finish()
        await asyncio.sleep(1)  # mantener la conexión viva hasta que B lea la respuesta

    async def caller_side():
        conn = await b.connect(a_addr, ALPN)
        print("  [B] conectado a A por su clave pública", flush=True)
        bi = await conn.open_bi()
        send, recv = bi.send(), bi.recv()
        await send.write_all(b"investiga iroh")
        await send.finish()
        reply = (await recv.read_to_end(4096)).decode("utf8")
        print("  [B] respuesta de A:", repr(reply), flush=True)

    await asyncio.gather(worker_side(), caller_side())
    print("\n✓ DOS AGENTES SE COMUNICARON POR CLAVE PÚBLICA (iroh nativo en Termux)", flush=True)
    await a.close()
    await b.close()


if __name__ == "__main__":
    asyncio.run(run())

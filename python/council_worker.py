"""Council worker — un endpoint iroh que ENVUELVE `claude -p`.

Recibe un prompt por iroh (dial-by-clave-pública, QUIC), lo corre en un
`claude -p` independiente, y devuelve la respuesta por la misma bidi stream.

    python council_worker.py

Imprime un TICKET. Pásaselo al caller (en este mismo device u otro):
    python council_caller.py <TICKET> "tu prompt"

FULL IROH, SIN ATAJOS: same-device y cross-device usan EXACTAMENTE este mismo
código — `ep.connect(addr, ALPN)` no sabe si el peer está en el Pixel o en el
Mac (QUIC directo local, o hole-punch / relay de n0 si es remoto). Para llevarlo
al Mac: construye iroh-ffi allá (pip normal, sin la gimnasia de Termux) y corre
este archivo TAL CUAL. Lo único que cambia es DÓNDE lo lanzas.
"""
import asyncio
import os

import iroh

ALPN = b"pi-agents/mailbox/0"          # mismo ALPN que agent_caller.py
CLAUDE = os.path.expanduser("~/.local/bin/claude")
MAX = 1 << 20                          # 1 MB por mensaje (prompts/respuestas reales)


def claude_env() -> dict:
    """Env sin las vars de Claude Code → el `claude -p` hijo NO crea una sub-sesión
    anidada si este proceso fue lanzado desde una sesión de Claude Code."""
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("CLAUDE_CODE") or k in ("CLAUDECODE", "CLAUDE_EFFORT"):
            env.pop(k, None)
    return env


async def run_claude(prompt: str) -> str:
    """Corre `claude -p` en un subprocess. Sin TTY (validado en Termux)."""
    proc = await asyncio.create_subprocess_exec(
        CLAUDE, "-p", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
        env=claude_env(),
    )
    out, err = await proc.communicate()
    if proc.returncode != 0:
        return f"[worker error rc={proc.returncode}] {err.decode(errors='replace')[:500]}"
    return out.decode("utf8", errors="replace").strip()


async def main():
    # uniffi necesita el event loop de asyncio explícito.
    iroh.iroh_ffi.uniffi_set_event_loop(asyncio.get_running_loop())

    ep = await iroh.Endpoint.bind(iroh.EndpointOptions(alpns=[ALPN]))
    print("council worker pubkey:", ep.id(), flush=True)
    ticket = iroh.EndpointTicket.from_addr(ep.addr())
    print("TICKET:", str(ticket), flush=True)
    print(f'\n→ en otra terminal (o en el Mac):\n    python council_caller.py {ticket} "tu prompt"\n', flush=True)
    print("esperando prompts... (Ctrl-C para salir)", flush=True)

    while True:
        incoming = await ep.accept_next()
        if incoming is None:
            break
        accepting = await incoming.accept()
        conn = await accepting.connect()
        peer = str(conn.remote_id())
        print(f"\n← prompt de {peer[:16]}…", flush=True)

        bi = await conn.accept_bi()
        recv, send = bi.recv(), bi.send()

        prompt = (await recv.read_to_end(MAX)).decode("utf8")
        print("   prompt:", repr(prompt[:80]), flush=True)
        print("   corriendo claude -p…", flush=True)

        answer = await run_claude(prompt)
        print(f"   respuesta lista ({len(answer)} chars) — enviando", flush=True)

        await send.write_all(answer.encode("utf8"))
        await send.finish()
        await asyncio.sleep(1)  # gotcha iroh: mantener conn viva para que el peer lea


if __name__ == "__main__":
    asyncio.run(main())

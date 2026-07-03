"""brains.py — el 'cerebro' de un nodo, detrás de una interfaz (harness-agnóstico).

Un nodo del council = transporte (iroh) + un brain. El brain es intercambiable:
`claude -p` hoy, PyPy u otro harness mañana. La librería NUNCA importa un harness
directo — depende de esta interfaz e inyecta el adapter (no wrappea).

    brain = get_brain("claude"); text = await brain.think(prompt)

Contrato: `async think(prompt: str) -> str`. Puro texto in / texto out.
El sandbox (qué puede tocar el nodo) vive acá, en el adapter — no en el transporte.
"""
import asyncio
import os

CLAUDE = os.path.expanduser("~/.local/bin/claude")

# Tools que apagamos en el modo 'pure': un nodo-agente con Bash/Read puede leer el
# filesystem/process table y ver contexto que NO le mandaste por iroh. 'pure' lo
# vuelve una función de texto pura → el único canal de contexto es el prompt.
_SANDBOX_OFF = "Bash,Read,Grep,Glob,Edit,Write,WebFetch,WebSearch,Task"


def _claude_env() -> dict:
    """Env sin vars de Claude Code → el `claude -p` hijo no anida sub-sesión."""
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("CLAUDE_CODE") or k in ("CLAUDECODE", "CLAUDE_EFFORT"):
            env.pop(k, None)
    return env


class ClaudeCliBrain:
    """`claude -p`. `pure=True` lo sandboxea (sin tools) → texto puro, sin snooping."""

    def __init__(self, pure: bool = False):
        self.name = "claude-pure" if pure else "claude"
        self.pure = pure

    async def think(self, prompt: str) -> str:
        args = [CLAUDE, "-p", prompt]
        if self.pure:
            args += ["--disallowedTools", _SANDBOX_OFF]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            env=_claude_env(),
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return f"[brain error rc={proc.returncode}] {err.decode(errors='replace')[:400]}"
        return out.decode("utf8", "replace").strip()


class EchoBrain:
    """Canned, sin gastar tokens — para regresión (ejercita transporte, no el modelo)."""

    name = "echo"

    async def think(self, prompt: str) -> str:
        await asyncio.sleep(0.05)
        return f"[echo] {prompt[:80]!r}"


_REGISTRY = {
    "claude": lambda: ClaudeCliBrain(pure=False),
    "claude-pure": lambda: ClaudeCliBrain(pure=True),
    "echo": lambda: EchoBrain(),
    # "pypy": lambda: PyPyBrain(),   ← el próximo harness entra acá, sin tocar el council
}


def get_brain(name: str):
    if name not in _REGISTRY:
        raise ValueError(f"brain desconocido: {name!r} (usa {'|'.join(_REGISTRY)})")
    return _REGISTRY[name]()

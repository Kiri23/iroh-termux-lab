#!/usr/bin/env python3
"""Test corrible del council — pruébalo en Termux, Mac, donde sea.

Corre el ENGINE headless (`council_run.py`) como subprocess, parsea su JSONL, y
asserta la secuencia de eventos del council. NO usa HTTP ni UI: prueba que la
idea funciona por sí sola (API/CLI), que es el punto — la UI es solo transporte.

    python council_test.py              # dry-run: gratis, determinista (transporte iroh real, sin claude -p)
    python council_test.py --live       # gasta claude -p: ves candidatos + veredicto REALES
    python council_test.py --workers 2 --prompt "tu pregunta"

Portable: usa el MISMO intérprete que lo corre (sys.executable), así que en el
Mac lo corres desde tu venv con iroh y funciona igual. Sale con código 0 si PASA.
"""
import argparse
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "council_run.py")

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def check(ok: bool, label: str, detail: str = "") -> bool:
    mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    line = f"  {mark} {label}"
    if detail:
        line += f"  {DIM}{detail}{RESET}"
    print(line)
    return ok


async def run_engine(prompt: str, workers: int, dry: bool, roles=None,
                     topology="star", brain=None):
    """Lanza council_run.py y devuelve (eventos_parseados, exit_code, stderr)."""
    args = [sys.executable, "-u", RUN, "--workers", str(workers),
            "--topology", topology, prompt]
    if dry:
        args.append("--dry-run")
    if brain:
        args += ["--brain", brain]
    if roles:
        args.append("--roles")
        args.extend(roles)
    proc = await asyncio.create_subprocess_exec(
        *args, cwd=HERE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
    )
    out, err = await proc.communicate()
    events = []
    for line in out.decode("utf8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # ruido no-JSON (panic ndk cosmético va a stderr igual)
    return events, proc.returncode, err.decode("utf8", "replace")


async def preflight():
    """Verifica que el python que spawneará el engine pueda importar iroh.

    El test spawnea council_run.py con sys.executable. Si corrés el test sin el
    venv de iroh, ese python no tiene iroh → el engine no emite nada y el test
    falla con candidatos vacíos. Esto lo detecta y te dice qué hacer.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import iroh",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode == 0:
        return
    print(f"\n{RED}✗ este intérprete no puede importar iroh:{RESET} {sys.executable}")
    print(f"{DIM}Activá el venv con iroh antes de correr el test:")
    print(f"    source ~/iroh-py/bin/activate   &&  python council_test.py ...   (Termux)")
    print(f"  o corré el test directamente con ese python:")
    print(f"    ~/iroh-py/bin/python council_test.py ...{RESET}")
    tail = [l for l in err.decode("utf8", "replace").splitlines() if l.strip()]
    if tail:
        print(f"{DIM}({tail[-1]}){RESET}")
    sys.exit(2)


def diagnose_empty(by: dict, err: str):
    """Si el engine no emitió candidatos, muestra su stderr (la causa real)."""
    if by.get("candidate"):
        return
    tail = "\n".join(l for l in err.splitlines()
                     if l.strip() and "ndk_context" not in l and "backtrace" not in l)[-600:]
    if tail.strip():
        print(f"\n{DIM}engine stderr (sin candidatos — causa probable):\n{tail}{RESET}")


def is_hex64(s: str) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower())


async def run_proof():
    """PRUEBA DE COMUNICACIÓN INTER-NODO (cadena, brain sandboxeado, live).

    Topología chain: w1 → w2. A w1 le doy SOLO la primera mitad del código; a w2
    SOLO la segunda. En chain, w2 recibe (por iroh) la salida de w1. Con brain
    `claude-pure` (sin Bash/Read) el ÚNICO canal por el que w2 puede enterarse
    de la mitad de w1 es la cadena iroh — no el filesystem.

    Si el candidato de w2 trae AMBAS mitades ⇒ probado: w1 le habló a w2 por iroh.
    Si el veredicto trae ambas ⇒ la síntesis lo recibió.
    """
    W1, W2 = "ZORRO", "RANA"
    base = ("Ejercicio técnico de concatenación de strings (nada sensible). Entre "
            "varios nodos formamos UNA palabra juntando trozos de texto. Devuelve la "
            "palabra lo más completa posible: concatena tu trozo con los trozos que te "
            "pasaron los nodos previos, pegados sin espacios. Solo imprime la palabra.")
    roles = [
        f"Tu trozo de texto es '{W1}'.",
        f"Tu trozo de texto es '{W2}'.",
    ]
    print(f"\n{BOLD}Council PROOF{RESET} — comunicación inter-nodo · cadena w1→w2 · brain claude-pure (LIVE)")
    print(f"{DIM}w1 sabe '{W1}' · w2 sabe '{W2}' · w2 recibe la salida de w1 SOLO por iroh{RESET}\n")

    events, code, err = await run_engine(base, 2, dry=False, roles=roles,
                                         topology="chain", brain="claude-pure")
    by = {}
    for e in events:
        by.setdefault(e.get("type"), []).append(e)
    cand = {c["worker"]: c.get("text", "") for c in by.get("candidate", [])}
    verdict = (by.get("verdict", [{}])[0]).get("text", "")
    flows = [(f["frm"], f["to"]) for f in by.get("flow", [])]
    diagnose_empty(by, err)

    r = []
    r.append(check(code == 0, "el engine salió 0", f"exit={code}"))
    r.append(check(("w1", "w2") in flows, "hubo flujo de contexto w1 → w2 (edge de la cadena)"))
    r.append(check(W1 in cand.get("w1", ""), f"w1 aporta su mitad ({W1})"))
    r.append(check(W1 in cand.get("w2", "") and W2 in cand.get("w2", ""),
                   f"w2 conoce AMBAS mitades ({W1}+{W2}) — recibió {W1} de w1 por iroh"))
    r.append(check(W1 in verdict and W2 in verdict,
                   f"el veredicto trae ambas mitades ({W1}+{W2})"))

    print(f"\n{BOLD}Candidatos:{RESET}")
    for w in ("w1", "w2"):
        print(f"  {DIM}[{w}]{RESET} {cand.get(w, '(nada)')[:180]}")
    print(f"\n{BOLD}Veredicto (síntesis):{RESET}\n  {verdict[:300]}")

    passed = all(r)
    print(f"\n{BOLD}{'PROOF PASS ✓' if passed else 'PROOF FAIL ✗'}{RESET}  ({sum(r)}/{len(r)} checks)")
    if passed:
        print(f"{DIM}→ w2 tiene la mitad de w1, que SOLO viajó por la cadena iroh (brain sin filesystem)\n"
              f"  ⇒ demostrado: nodo 1 se comunicó con nodo 2, y el sintetizador lo recibió.{RESET}")
    sys.exit(0 if passed else 1)


async def run_proof_fusion():
    """PRUEBA DE FUSIÓN EN EL SINTETIZADOR (star, tokens disjuntos, live).

    star = nodos independientes (no se ven). w1 sabe SOLO 'ZORRO', w2 SOLO 'RANA'.
    Con brain claude-pure (sin filesystem), ningún nodo pudo ver el token del otro:
    ni por iroh (en star NO hay edges) ni por el disco. Si el veredicto trae AMBOS
    ⇒ el ÚNICO que vio los dos es el SINTETIZADOR. Prueba que el synth fusionó w1+w2.

    Nota: usa tokens DISJUNTOS porque la procedencia solo es demostrable cuando las
    contribuciones son separables e infalsificables. Un test de síntesis *semántica*
    real (fundir dos respuestas solapadas en UNA mejor, no concatenar) es otra cosa
    y queda para después — reemplazará/complementará a este.
    """
    W1, W2 = "ZORRO", "RANA"
    base = ("Ejercicio de concatenación (nada sensible): entre varios nodos formamos "
            "UNA palabra juntando trozos. Con lo que veas en las respuestas de los "
            "nodos, concatena todos los trozos pegados sin espacios y devuelve la "
            "palabra más completa que puedas.")
    roles = [
        f"Tu único trozo de texto es '{W1}'. No conoces ningún otro trozo.",
        f"Tu único trozo de texto es '{W2}'. No conoces ningún otro trozo.",
    ]
    print(f"\n{BOLD}Council PROOF-FUSION{RESET} — el synth fusiona · star · brain claude-pure (LIVE)")
    print(f"{DIM}w1 sabe SOLO '{W1}' · w2 sabe SOLO '{W2}' · en star no se ven{RESET}\n")

    events, code, err = await run_engine(base, 2, dry=False, roles=roles,
                                         topology="star", brain="claude-pure")
    by = {}
    for e in events:
        by.setdefault(e.get("type"), []).append(e)
    cand = {c["worker"]: c.get("text", "") for c in by.get("candidate", [])}
    verdict = (by.get("verdict", [{}])[0]).get("text", "")
    flows = [(f["frm"], f["to"]) for f in by.get("flow", [])]
    diagnose_empty(by, err)

    r = []
    r.append(check(code == 0, "el engine salió 0", f"exit={code}"))
    r.append(check(flows == [], "star: CERO flow edges — los nodos NO se comunicaron"))
    r.append(check(W1 in cand.get("w1", "") and W2 not in cand.get("w1", ""),
                   f"w1 conoce SOLO su token ({W1}, no {W2})"))
    r.append(check(W2 in cand.get("w2", "") and W1 not in cand.get("w2", ""),
                   f"w2 conoce SOLO su token ({W2}, no {W1})"))
    r.append(check(W1 in verdict and W2 in verdict,
                   f"el veredicto trae AMBOS ({W1}+{W2}) — solo el synth vio los dos"))

    print(f"\n{BOLD}Candidatos:{RESET}")
    for w in ("w1", "w2"):
        print(f"  {DIM}[{w}]{RESET} {cand.get(w, '(nada)')[:180]}")
    print(f"\n{BOLD}Veredicto (síntesis):{RESET}\n  {verdict[:300]}")

    passed = all(r)
    print(f"\n{BOLD}{'PROOF-FUSION PASS ✓' if passed else 'PROOF-FUSION FAIL ✗'}{RESET}  ({sum(r)}/{len(r)} checks)")
    if passed:
        print(f"{DIM}→ tokens disjuntos, nodos aislados (star, sin edges) y sin filesystem:\n"
              f"  el único que pudo ver ambos es el sintetizador ⇒ fusionó w1 + w2.{RESET}")
    sys.exit(0 if passed else 1)


# ── Contrato de edges por topología (agregar una topología nueva = una línea acá) ──
def chain_edges(n):
    return [(f"w{i}", f"w{i+1}") for i in range(1, n)]


TOPOLOGY_SPEC = {
    "star": {"edges": lambda n: [], "desc": "nodos independientes, sin edges"},
    "chain": {"edges": chain_edges, "desc": "cadena w1→w2→…"},
    # "tree": {"edges": tree_edges, "desc": "…"},   ← una topología nueva entra acá
}


async def run_topologies(workers: int = 3):
    """Verifica el CONTRATO de edges de cada topología (echo, gratis, determinista).

    Para cada topología corre el engine y assertea que los eventos `flow` (los
    edges del DAG) sean exactamente los esperados. Es el arnés para probar
    topologías nuevas: agregas su predicado a TOPOLOGY_SPEC y este test lo cubre.
    """
    print(f"\n{BOLD}Council TOPOLOGIES{RESET} — contrato de edges (echo, gratis) · {workers} nodos\n")
    r = []
    for topo, spec in TOPOLOGY_SPEC.items():
        events, code, _ = await run_engine("test de topología", workers, dry=True, topology=topo)
        by = {}
        for e in events:
            by.setdefault(e.get("type"), []).append(e)
        flows = [(f["frm"], f["to"]) for f in by.get("flow", [])]
        expected = spec["edges"](workers)
        print(f"  {DIM}· {topo} ({spec['desc']}){RESET}")
        r.append(check(code == 0, f"  [{topo}] engine salió 0"))
        r.append(check(len(by.get("worker_up", [])) == workers, f"  [{topo}] {workers} nodos"))
        r.append(check(flows == expected, f"  [{topo}] edges correctos",
                       f"esperado {expected or '[]'}, got {flows or '[]'}"))
        r.append(check(len(by.get("verdict", [])) == 1, f"  [{topo}] un veredicto"))

    passed = all(r)
    print(f"\n{BOLD}{'TOPOLOGIES PASS ✓' if passed else 'TOPOLOGIES FAIL ✗'}{RESET}  ({sum(r)}/{len(r)} checks)")
    sys.exit(0 if passed else 1)


async def main():
    ap = argparse.ArgumentParser(description="Test del council Self-MoA sobre iroh")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--live", action="store_true", help="gasta claude -p (default: dry-run)")
    ap.add_argument("--proof", action="store_true",
                    help="prueba de comunicación inter-nodo: cadena + secreto (live)")
    ap.add_argument("--proof-fusion", action="store_true",
                    help="prueba que el SYNTH fusiona: star + tokens disjuntos (live)")
    ap.add_argument("--topologies", action="store_true",
                    help="verifica el contrato de edges de cada topología (echo, gratis)")
    ap.add_argument("--prompt", default="En una frase, ¿qué es un DAG?")
    args = ap.parse_args()

    await preflight()  # falla claro si el python no tiene iroh (venv no activado)

    if args.proof:
        await run_proof()
        return
    if args.proof_fusion:
        await run_proof_fusion()
        return
    if args.topologies:
        await run_topologies(args.workers if args.workers != 2 else 3)
        return
    dry = not args.live

    mode = f"{'LIVE (claude -p real)' if args.live else 'DRY-RUN (canned, gratis)'}"
    print(f"\n{BOLD}Council test{RESET} — {mode} · {args.workers} workers")
    print(f"{DIM}engine: {RUN}{RESET}")
    print(f"{DIM}python: {sys.executable}{RESET}\n")

    events, code, err = await run_engine(args.prompt, args.workers, dry)

    by = {}
    for e in events:
        by.setdefault(e.get("type"), []).append(e)

    results = []
    results.append(check(code == 0, "el engine salió con código 0", f"exit={code}"))
    results.append(check(bool(events), "emitió eventos JSONL parseables", f"{len(events)} eventos"))
    results.append(check(len(by.get("start", [])) == 1, "un evento 'start'"))
    results.append(check(len(by.get("worker_up", [])) == args.workers,
                         f"{args.workers} workers levantaron (worker_up)",
                         f"got {len(by.get('worker_up', []))}"))
    results.append(check(all(is_hex64(w.get("pubkey", "")) for w in by.get("worker_up", [])),
                         "cada worker_up trae una pubkey de 64 hex"))
    results.append(check(len(by.get("candidate", [])) == args.workers,
                         f"{args.workers} candidatos por iroh (candidate)",
                         f"got {len(by.get('candidate', []))}"))
    results.append(check(all(c.get("text", "").strip() for c in by.get("candidate", [])),
                         "cada candidato trae texto no vacío"))
    results.append(check(len(by.get("synth_start", [])) == 1, "un 'synth_start' (fase de síntesis)"))
    verdict = by.get("verdict", [])
    results.append(check(len(verdict) == 1 and bool(verdict[0].get("text", "").strip()),
                         "un veredicto final no vacío"))
    results.append(check(len(by.get("worker_down", [])) == args.workers,
                         f"{args.workers} workers apagados (worker_down, cleanup)",
                         f"got {len(by.get('worker_down', []))}"))

    # Muestra el contenido real (lo que Christian quiere VER)
    if by.get("candidate"):
        print(f"\n{BOLD}Candidatos:{RESET}")
        for c in by["candidate"]:
            print(f"  {DIM}[{c['worker']} {c['pubkey'][:8]}…]{RESET} {c['text'][:160]}")
    if verdict:
        print(f"\n{BOLD}Veredicto:{RESET}\n  {verdict[0].get('text', '')[:400]}")

    passed = all(results)
    print(f"\n{BOLD}{'PASS ✓' if passed else 'FAIL ✗'}{RESET}  "
          f"({sum(results)}/{len(results)} checks)")
    if not passed and err.strip():
        # solo el panic ndk cosmético normalmente; útil si algo raro pasó
        tail = "\n".join(l for l in err.splitlines() if "ndk_context" not in l and "backtrace" not in l)[:400]
        if tail.strip():
            print(f"{DIM}stderr:\n{tail}{RESET}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())

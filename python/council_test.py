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


async def run_engine(prompt: str, workers: int, dry: bool):
    """Lanza council_run.py y devuelve (eventos_parseados, exit_code, stderr)."""
    args = [sys.executable, "-u", RUN, "--workers", str(workers), prompt]
    if dry:
        args.append("--dry-run")
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


def is_hex64(s: str) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s.lower())


async def main():
    ap = argparse.ArgumentParser(description="Test del council Self-MoA sobre iroh")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--live", action="store_true", help="gasta claude -p (default: dry-run)")
    ap.add_argument("--prompt", default="En una frase, ¿qué es un DAG?")
    args = ap.parse_args()
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

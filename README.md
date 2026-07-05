# iroh-termux-lab

iroh corriendo **nativo en Termux/Android ARM64** (Bionic) — sin proot, sin glibc-runner, sin prebuilt. Dos programas separados que se conectan **por clave pública** sobre QUIC real + relay de n0.

Probado el 2026-06-25 en Pixel 10 (rustc 1.93.1, iroh 1.0.0, backend `ring`). Ver `learning/` del clone (`~/Code/SourceCode/iroh/learning/`) para qué ES iroh.

> **El trabajo actual es el [Council](#council--self-moa-sobre-iroh)** (Self-MoA sobre iroh, rama `council-poc`). Entrypoint: `python/council_run.py`. Este README de arriba documenta el lab de iroh sobre el que se para.

## Programas

- `src/bin/listen.rs` — levanta un `Endpoint`, imprime su `endpoint-id` (clave pública) + addrs + relay, y queda aceptando. Hace echo de lo que reciba.
- `src/bin/connect.rs` — recibe `--endpoint-id --addrs --relay-url`, conecta por clave pública y manda un mensaje.
- `src/bin/echo.rs` — ejemplo self-contained (un proceso, dos endpoints).

## ⚠️ La receta de Termux (no es opcional)

**1. Compilar FUERA de shared storage.** `~/Code` es symlink a almacenamiento compartido de Android → `cargo` falla ahí (flock / no se puede `chmod +x` el binario). Construye con el target en FS nativo:

```bash
cd ~/Code/iroh
export TMPDIR=$HOME/tmp                       # evita el bloqueo de namespace /usr/tmp (LD_PRELOAD)
export CARGO_TARGET_DIR=$HOME/tmp/iroh-target # ← target en FS NATIVO, no en ~/Code (shared)
mkdir -p "$TMPDIR" "$CARGO_TARGET_DIR"
cargo build -j2 --bin listen --bin connect    # -j2: limita RAM (Termux tiene poca libre)
```

**2. Correr (dos terminales):**

```bash
# Terminal A
$CARGO_TARGET_DIR/debug/listen
# imprime: cargo run --example connect -- --endpoint-id <KEY> --addrs "<IPs>" --relay-url <URL>

# Terminal B — pega los args que imprimió A:
$CARGO_TARGET_DIR/debug/connect --endpoint-id <KEY> --addrs "<IPs>" --relay-url <URL>
```

Resultado esperado: A imprime `received: <KEY-de-B> is saying 'hello!'` y B imprime `received: hi! you connected to <KEY-de-A>. bye bye`.

## ⚠️ Gotcha conocido: panic `ndk_context not initialized` (cosmético)

Al arrancar verás un `thread 'main' panicked ... ndk_context not initialized`. **No es fatal** — `hickory-resolver` (el DNS de iroh) intenta leer la config DNS de Android vía JNI, que no existe en un proceso Termux plano. **iroh atrapa ese panic** (`iroh_dns::android::read_system_conf` lo envuelve en `catch_unwind`) y cae a DNS de fallback. La conexión funciona igual. Para un run limpio: pasarle al `Endpoint` un `DnsResolver` con servidores explícitos. Detalle en el skill `termux-gotchas`.

## Backend de crypto

`iroh = "1"` trae `tls-ring` por defecto → usa **ring**, que compila en `aarch64-linux-android`. **No** habilites `tls-aws-lc-rs` (necesita cmake/nasm).

## Créditos / licencia

Los `src/bin/{listen,connect,echo}.rs` son **ejemplos de [n0-computer/iroh](https://github.com/n0-computer/iroh)** (dual MIT / Apache-2.0). Los scripts Python (`two_agents.py`, `agent_worker.py`, `agent_caller.py`) y esta documentación de la receta Termux son originales. Este repo es un *lab* personal, no oficial.

---

# Python — dos agentes hablándose por iroh (nativo en Termux)

`python/two_agents.py` ✅ probado: dos `Endpoint` (Agente A worker + Agente B caller), cada uno su keypair, intercambian mensaje **bidireccional por clave pública**. `agent_worker.py` + `agent_caller.py` = la misma lógica para **dos terminales** (ticket entre procesos).

iroh tiene binding Python oficial (`iroh-ffi`, uniffi sobre el mismo core Rust). **No hay wheel para Android** en PyPI → hay que construirlo con **maturin** en el teléfono.

## Receta (validada 2026-06-25, iroh-ffi 1.0.0 → iroh 1.0.0, sin version-mismatch)

```bash
# 1. toolchain
cargo install maturin            # maturin no tiene wheel Android → compílalo nativo
python -m venv ~/iroh-py

# 2. iroh-ffi a FS nativo (fuera de shared storage)
cp -r ~/Code/SourceCode/iroh-ffi ~/src/iroh-ffi   # o git clone n0-computer/iroh-ffi
cd ~/src/iroh-ffi
source ~/iroh-py/bin/activate
export TMPDIR=$HOME/tmp CARGO_TARGET_DIR=$HOME/tmp/iroh-ffi-target CARGO_PROFILE_DEV_DEBUG=0

# 3. construir el wheel (rebuild de iroh ~12min la 1a vez, backend ring)
~/.cargo/bin/maturin build -j2 --out ~/tmp/wheels

# 4. RETAG: maturin lo etiqueta android_24_arm64_v8a, pero pip se ve como linux_aarch64
pip install wheel
python -m wheel tags --platform-tag linux_aarch64 --remove ~/tmp/wheels/iroh-1.0.0-py3-none-android_24_arm64_v8a.whl

# 5. instalar
pip install --force-reinstall --no-deps ~/tmp/wheels/iroh-1.0.0-py3-none-linux_aarch64.whl
python -c "import iroh; print('OK', iroh.__file__)"
```

## Correr los dos agentes

```bash
source ~/iroh-py/bin/activate
cd ~/Code/iroh/python
# demo determinista (1 proceso, 2 endpoints):
python -u two_agents.py
# o dos terminales reales:
python -u agent_worker.py            # imprime un TICKET
python -u agent_caller.py <TICKET> "tu tarea"
```

## ⚠️ Gotchas Python (los 3 que costaron)

1. **Wheel platform-tag:** maturin etiqueta `android_24_arm64_v8a` pero el pip de Termux se identifica como `linux-aarch64` → "not a supported wheel". Fix: `wheel tags --platform-tag linux_aarch64`.
2. **API quiere `bytes`, no `list(bytes)`:** este binding (uniffi) espera `bytes` crudos en ALPN/`write_all`. El `python/main.py` del repo usa `list(...)` y **falla** — está desfasado. Usa `EndpointOptions(alpns=[ALPN])` y `send.write_all(data_bytes)`.
3. **Mantén la conexión viva:** tras `send.finish()` en el lado que responde, `await asyncio.sleep(...)` antes de soltar `conn`, o el peer recibe `IrohError` al leer la respuesta (igual que hace `main.py`).
4. **`PYTHONUNBUFFERED=1`** si rediriges stdout a un archivo (Python bufferea; el panic ndk en stderr sí sale, pero los `print` no).
5. **panic `ndk_context`**: cosmético también en Python (iroh lo atrapa, fallback DNS).

---

# Council — Self-MoA sobre iroh

**El trabajo actual** (rama `council-poc`). Un *council* le hace el MISMO prompt a
N agentes de IA que viven detrás de una clave pública (P2P por iroh), junta sus
respuestas y un agente final las **sintetiza** en un veredicto — el patrón
**Mixture-of-Agents**. Se para sobre el binding Python de iroh de arriba.

La idea es engine/transport puro: **iroh mueve los bytes** (el prompt entre nodos)
y **el `brain` piensa** (una interfaz `async think(prompt) -> str`). El brain es
enchufable — `claude -p` hoy, PyPy/Pi mañana — sin tocar el transporte.

## Entrypoint

```bash
source ~/iroh-py/bin/activate            # el venv con iroh (ver receta Python arriba)
cd ~/Code/iroh/python

python council_run.py --workers 2 "¿qué es un DAG?"     # council real (gasta claude -p)
python council_run.py --brain echo --dry-run "prompt"   # gratis (transporte real, sin claude)
python council_run.py --topology chain --roles "sabe A" "sabe B" "prompt"
```

`council_run.py` es el orquestador: spawnea N `council_worker.py` (cada uno =
transporte iroh + un brain), los recorre según la **topología**, sintetiza el
veredicto y limpia. Emite todo como **JSONL** (una línea = un evento) — el contrato
que consume la UI y que `council_test.py` assertea.

## Archivos

| Archivo | Rol |
|---|---|
| `council_run.py` | **orquestador** — el entrypoint. DAG(nodos, edges) + brain. |
| `council_worker.py` | **un nodo** — transporte iroh + un brain. Imprime un TICKET. |
| `council_aggregator.py` | fan-out (`ask_worker`) + síntesis (`synthesize`). |
| `brains.py` | el **engine** enchufable: `claude` \| `claude-pure` \| `echo`. |
| `council_test.py` | harness corrible (dry-run gratis / `--live` real). |

## Topologías (mismo engine, distinto set de edges)

- **`star`** (default): nodos independientes en paralelo; solo el synth los ve a todos.
- **`chain`**: cada nodo recibe (por iroh) la salida del anterior y construye sobre ella.

Agregar una topología nueva = una función de edges en `TOPOLOGIES` (`council_run.py`).

## Brains y sandbox

`--brain claude` corre `claude -p` con tools completas. `--brain claude-pure` le
apaga las tools (`--disallowedTools Bash,Read,…`) → función de texto pura: el único
canal de contexto es el prompt, no el filesystem. **El sandbox vive en el adapter
del brain, no en el transporte** (ver `_pkm/atomic/`).

## Test

```bash
python council_test.py                 # dry-run: gratis, determinista (iroh real, sin claude)
python council_test.py --live          # gasta claude -p: candidatos + veredicto reales
python council_test.py --proof-fusion  # star + tokens disjuntos → prueba que el synth fusiona
python council_test.py --topologies    # verifica el contrato de edges de cada topología
```

## Diseño y referencias

- `_pkm/atomic/` — el rationale atómico (credit-assignment con tokens disjuntos,
  sandbox en el adapter, framing del prompt de orquestación).
- `_pkm/references/` — artefactos visuales (HTML self-contained): el **mapa del
  codebase** y un **blindspot pass**. Abrí con `termux-open --content-type text/html <file>`.

"""
ARKANI ENGINE v2.0
Fusion completa: FractalCompiler + NexusCompiler + AutoEvolucion + FractalVM
Con protecciones anti-loop y sandbox seguro

Constructor: Medico Radiologo, Xalapa
Fecha: 15 junio 2026
Paso 1 REAL: FractalVM integrada con API exacta de nexus_fractal_vm.py
  - vm.estado()           → dict: neuronas, bytes, ejecuciones, evoluciones, uptime_s, status
  - vm.ejecutar_todo()    → dict: ejecutadas, evoluciones, nuevas, tiempo_s, neuronas_total
  - vm.ejecutar_una(dir)  → Any (resultado de una instruccion por direccion)
  - vm.listar()           → imprime instrucciones (sin return util)
"""

import os
import re
import sys
import io
import json
import struct
import hashlib
import signal
import subprocess
import datetime
import requests
import time
import urllib.parse
from enum import Enum
from typing import List, Optional, Dict, Tuple

# ─────────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────────
BASE_DIR    = os.path.expanduser("~/NEXUS/NEXUS-LANG/")
AUTOGEN_DIR = os.path.join(BASE_DIR, "autogen/")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts_arkani/")
HIPOCAMPO   = os.path.join(BASE_DIR, "hipocampo.bin")
MEMORIA_PATH      = os.path.join(BASE_DIR, "memoria_arkani.json")
CONOCIMIENTO_PATH = os.path.join(BASE_DIR, "conocimiento_arkani.json")
OLLAMA_URL  = "http://127.0.0.1:11434/api/generate"
MODELO      = "arkani:latest"

for d in [BASE_DIR, AUTOGEN_DIR, SCRIPTS_DIR]:
    os.makedirs(d, exist_ok=True)


# ══════════════════════════════════════════════
# PROTECCIONES ANTI-LOOP
# ══════════════════════════════════════════════

MAX_PROFUNDIDAD_EVOLVE  = 3
MAX_EVOLUCIONES_SESION  = 10
MAX_PASOS_REACT         = 3
MAX_SEGUNDOS_EXEC       = 10
MAX_SEGUNDOS_SCRIPT     = 15

PATRONES_PROHIBIDOS = [
    r"while\s+True",
    r"exec\s*\(",
    r"eval\s*\(",
    r"os\.system\s*\(",
    r"subprocess\.Popen",
    r"__import__\s*\(",
    r"open\s*\(.+['\"]w['\"]",
    r"self_modify",
    r"correr_agente",
]

_profundidad_evolve_actual = 0
_evoluciones_esta_sesion   = 0


def verificar_codigo_seguro(codigo: str) -> Tuple[bool, str]:
    for patron in PATRONES_PROHIBIDOS:
        if re.search(patron, codigo, re.IGNORECASE):
            return False, f"Patron prohibido: {patron}"
    try:
        import ast
        ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Error de sintaxis: {e}"
    return True, "OK"


def timeout_handler(signum, frame):
    raise TimeoutError("Ejecucion cancelada: timeout de seguridad")


def exec_seguro(codigo: str, contexto_permitido: dict = None) -> Tuple[bool, str]:
    global _profundidad_evolve_actual, _evoluciones_esta_sesion

    if _profundidad_evolve_actual >= MAX_PROFUNDIDAD_EVOLVE:
        return False, f"⛔ Profundidad maxima ({MAX_PROFUNDIDAD_EVOLVE}) alcanzada"
    if _evoluciones_esta_sesion >= MAX_EVOLUCIONES_SESION:
        return False, f"⛔ Limite de sesion ({MAX_EVOLUCIONES_SESION}) alcanzado"

    seguro, motivo = verificar_codigo_seguro(codigo)
    if not seguro:
        return False, f"⛔ Codigo bloqueado: {motivo}"

    namespace = {
        "__builtins__": {
            "print": print, "len": len, "range": range,
            "str": str, "int": int, "float": float,
            "list": list, "dict": dict, "bool": bool,
            "abs": abs, "round": round, "min": min,
            "max": max, "sum": sum, "sorted": sorted,
            "enumerate": enumerate, "zip": zip,
        }
    }
    if contexto_permitido:
        namespace.update(contexto_permitido)

    try:
        _profundidad_evolve_actual += 1
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(MAX_SEGUNDOS_EXEC)
        exec(codigo, namespace)
        signal.alarm(0)
        _profundidad_evolve_actual -= 1
        _evoluciones_esta_sesion += 1
        return True, "Ejecutado con exito en sandbox"
    except TimeoutError:
        _profundidad_evolve_actual -= 1
        return False, f"⛔ Timeout: mas de {MAX_SEGUNDOS_EXEC}s"
    except Exception as e:
        _profundidad_evolve_actual -= 1
        return False, f"⛔ Error en ejecucion: {e}"
    finally:
        signal.alarm(0)


# ══════════════════════════════════════════════
# LENGUAJE FRACTAL — 7 OPERACIONES (16 bytes)
# ══════════════════════════════════════════════

class FractalOp(Enum):
    SUM    = 0xA0
    IF     = 0xA1
    LOOP   = 0xA3
    SPAWN  = 0xA5
    FOLD   = 0xA7
    LINK   = 0xA9
    EVOLVE = 0xF1


class FractalInstruction:
    FRACTAL_ID = 0x7C
    MAX_SCALE  = 31

    def __init__(self, op: FractalOp, scale: int,
                 fold_target: Optional[str] = None,
                 link_to: Optional[int] = None):
        self.op          = op
        self.scale       = min(scale, self.MAX_SCALE)
        self.fold_target = fold_target
        self.link_to     = link_to
        self.address     = None

    def to_bytes(self) -> bytes:
        b0, b1, b2 = self.FRACTAL_ID, self.op.value, self.scale
        flags = 0
        if self.fold_target:              flags |= 0x01
        if self.link_to is not None:      flags |= 0x02
        if self.op == FractalOp.EVOLVE:   flags |= 0x80
        fold_addr = (0xFFFFFFFF if self.fold_target == "self"
                     else hash(self.fold_target) & 0xFFFFFFFF if self.fold_target
                     else 0)
        link_addr = self.link_to if self.link_to is not None else 0
        partial   = (bytes([b0, b1, b2, flags])
                     + struct.pack('<I', fold_addr)
                     + struct.pack('<I', link_addr))
        return partial + hashlib.sha256(partial).digest()[:4]

    def __repr__(self):
        return (f"⟦{self.op.name}⟧ [SCALE:{self.scale}] "
                f"[FOLD:{self.fold_target}] [LINK:{self.link_to}]")


class Hipocampo:
    def __init__(self):
        self.path = HIPOCAMPO
        self.instructions: List[FractalInstruction] = []
        self._load()

    def _load(self):
        try:
            with open(self.path, 'rb') as f:
                data = f.read()
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                if len(chunk) != 16 or chunk[0] != FractalInstruction.FRACTAL_ID:
                    continue
                op = next((o for o in FractalOp if o.value == chunk[1]), None)
                if op:
                    inst = FractalInstruction(op, chunk[2])
                    inst.address = i // 16
                    self.instructions.append(inst)
            print(f"🧬 Hipocampo: {len(self.instructions)} instrucciones cargadas")
        except FileNotFoundError:
            self._inicializar()

    def _inicializar(self):
        self.instructions = [
            FractalInstruction(FractalOp.EVOLVE, 31, "self"),
            FractalInstruction(FractalOp.LOOP,   10, "self"),
        ]
        for i, inst in enumerate(self.instructions):
            inst.address = i
        print(f"🧬 Hipocampo inicializado con {len(self.instructions)} instrucciones")
        self._save()

    def _save(self):
        with open(self.path, 'wb') as f:
            for inst in self.instructions:
                f.write(inst.to_bytes())

    def agregar(self, inst: FractalInstruction) -> int:
        inst.address = len(self.instructions)
        self.instructions.append(inst)
        self._save()
        return inst.address

    def evolucionar(self, address: int, mutacion: str) -> bool:
        inst = self.get(address)
        if not inst or inst.op != FractalOp.EVOLVE:
            return False
        if "scale_up" in mutacion and inst.scale < FractalInstruction.MAX_SCALE:
            inst.scale += 1
        elif "fold_deeper" in mutacion:
            inst.fold_target = "self"
        self._save()
        return True

    def get(self, address: int) -> Optional[FractalInstruction]:
        if 0 <= address < len(self.instructions):
            return self.instructions[address]
        return None

    def resumen(self) -> str:
        ops = {}
        for i in self.instructions:
            ops[i.op.name] = ops.get(i.op.name, 0) + 1
        return (f"{len(self.instructions)} instr "
                f"({len(self.instructions)*16}B) — "
                + " ".join(f"{k}:{v}" for k, v in sorted(ops.items())))


# ══════════════════════════════════════════════
# MOTOR FRACTAL
# ══════════════════════════════════════════════

class FractalEngine:
    def __init__(self, mem=None):
        self.hipocampo = Hipocampo()
        self.mem       = mem
        self.vm        = None   # FractalVM — asignada por ArkaniEngine.__init__
        self.primitives = {
            '⟦SUM⟧':    lambda a, b: a + b,
            '⟦EVOLVE⟧': self._mutar,
            '⟦FOLD⟧':   self._plegar,
        }
        self.op_map = {o.name: o for o in FractalOp}

    def _mutar(self, codigo: str) -> str:
        ok, msg = exec_seguro(codigo)
        return "EVOLVED" if ok else f"BLOCKED: {msg}"

    def _plegar(self, data, fold_fn=None) -> str:
        return "COMPRESSED_NEXUS_DATA"

    def compilar_96(self, descripcion: str) -> bytes:
        firma     = b'\x19\x79'
        hash_desc = hashlib.sha256(descripcion.encode()).digest()[:30]
        timestamp = struct.pack('<Q', int(time.time()))[:8]
        padding   = os.urandom(96 - 2 - 30 - 8)
        return firma + hash_desc + timestamp + padding

    def compilar_16(self, linea: str) -> Optional[FractalInstruction]:
        linea = linea.strip()
        if not linea or linea.startswith('#'):
            return None
        op_m = re.search(r'⟦(\w+)⟧', linea)
        if not op_m or op_m.group(1) not in self.op_map:
            return None
        op    = self.op_map[op_m.group(1)]
        scale = int(s.group(1)) if (s := re.search(r'\[SCALE:(\d+)\]', linea)) else 1
        fold  = f.group(1) if (f := re.search(r'\[FOLD:([^\]]+)\]', linea)) else None
        link  = int(lk.group(1)) if (lk := re.search(r'\[LINK:(\d+)\]', linea)) else None
        return FractalInstruction(op, scale, fold, link)

    def evolucionar(self, descripcion: str, codigo_python: str) -> str:
        global _evoluciones_esta_sesion

        if _evoluciones_esta_sesion >= MAX_EVOLUCIONES_SESION:
            return f"⛔ Limite de {MAX_EVOLUCIONES_SESION} evoluciones por sesion alcanzado"

        seguro, motivo = verificar_codigo_seguro(codigo_python)
        if not seguro:
            return f"⛔ Evolucion bloqueada: {motivo}"

        ok, msg = exec_seguro(codigo_python)
        estado_exec = "✅ mutacion en memoria" if ok else f"⚠️ sandbox bloqueo ({msg})"

        nombre = re.sub(r'[^a-z0-9_]', '_', descripcion.lower().replace(' ', '_'))[:40]
        if not nombre.startswith(('fn_', 'node_')):
            nombre = f"fn_{nombre}"
        ruta_py = os.path.join(AUTOGEN_DIR, f"{nombre}.py")
        header  = (f"# ARKANI AUTO-GEN — {descripcion}\n"
                   f"# Generado: {datetime.datetime.now().isoformat()}\n"
                   f"# Evoluciones sesion: {_evoluciones_esta_sesion + 1}"
                   f"/{MAX_EVOLUCIONES_SESION}\n\n")
        with open(ruta_py, 'w') as f:
            f.write(header + codigo_python)

        binario  = self.compilar_96(descripcion)
        ruta_bin = ruta_py.replace('.py', '.bin')
        with open(ruta_bin, 'wb') as f:
            f.write(binario)

        inst = FractalInstruction(FractalOp.EVOLVE, scale=min(
            _evoluciones_esta_sesion + 1, FractalInstruction.MAX_SCALE
        ), fold_target="self")
        addr = self.hipocampo.agregar(inst)

        if self.mem:
            self.mem.registrar_evolucion(descripcion, ruta_py)

        # Sincronizar FractalVM: recargar hipocampo.bin con la nueva instruccion
        vm_nota = ""
        if self.vm:
            try:
                self.vm._cargar()   # recarga desde hipocampo.bin actualizado
                e = self.vm.estado()
                vm_nota = f"\n   🖥️  VM sincronizada: {e['neuronas']} neuronas"
            except Exception as ex:
                vm_nota = f"\n   🖥️  VM sync error: {ex}"

        _evoluciones_esta_sesion += 1

        return (f"🧬 Evolucion #{_evoluciones_esta_sesion} completada:\n"
                f"   {estado_exec}\n"
                f"   📄 {os.path.basename(ruta_py)}\n"
                f"   🔵 {os.path.basename(ruta_bin)} (96B, firma \\x19\\x79)\n"
                f"   💾 Hipocampo dir {addr}: {inst}\n"
                f"   📊 {self.hipocampo.resumen()}"
                f"{vm_nota}")

    def listar_capacidades(self) -> str:
        try:
            archivos = sorted([f for f in os.listdir(AUTOGEN_DIR) if f.endswith('.py')])
            if not archivos:
                return "Sin modulos autogenerados aun."
            return (f"Capacidades ({len(archivos)}):\n"
                    + "\n".join(f"  - {a}" for a in archivos))
        except Exception as e:
            return f"Error: {e}"


# ══════════════════════════════════════════════
# MEMORIA EVOLUTIVA
# ══════════════════════════════════════════════

class MemoriaEvolutiva:
    def __init__(self):
        self.memoria      = self._cargar(MEMORIA_PATH,      self._mem_default())
        self.conocimiento = self._cargar(CONOCIMIENTO_PATH, {"hechos": {}, "preferencias": {}})

    def _mem_default(self):
        return {
            "version": "1.0",
            "constructor": "Medico Radiologo, Xalapa",
            "fecha_nacimiento": "29 abril 2026",
            "conversaciones": [],
            "pendientes": [],
            "aprendizajes": [],
            "evoluciones": [],
            "estadisticas": {"preguntas": 0, "evoluciones": 0}
        }

    def _cargar(self, path, default):
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def memoria_corto_plazo(self, n: int = 3) -> str:
        convs = self.memoria.get("conversaciones", [])[-n:]
        if not convs:
            return ""
        lineas = []
        for c in convs:
            p = c.get("pregunta", "")[:80]
            r = c.get("respuesta", "")[:120]
            lineas.append(f"U: {p}\nA: {r}")
        return "\n---\n".join(lineas)

    def memoria_largo_plazo(self, pregunta: str, n_resultados: int = 2) -> str:
        convs = self.memoria.get("conversaciones", [])
        if len(convs) <= 3:
            return ""
        antiguas = convs[:-3]
        stopwords = {"que","quien","como","cual","donde","cuando",
                     "para","por","con","sin","una","uno","los",
                     "las","del","fue","son","eres","tienes"}
        keywords = {p.lower().strip("?¿.,") for p in pregunta.split()
                    if len(p) > 3 and p.lower() not in stopwords}
        if not keywords:
            return ""
        resultados = []
        for c in antiguas:
            texto = (c.get("pregunta","") + " " + c.get("respuesta","")).lower()
            score = sum(1 for k in keywords if k in texto)
            if score >= 1:
                resultados.append((score, c))
        if not resultados:
            return ""
        resultados.sort(key=lambda x: x[0], reverse=True)
        lineas = []
        for _, c in resultados[:n_resultados]:
            p = c.get("pregunta","")[:60]
            r = c.get("respuesta","")[:100]
            lineas.append(f"[Memoria] {p} → {r}")
        return "\n".join(lineas)

    def guardar(self):
        for path, datos in [(MEMORIA_PATH, self.memoria),
                            (CONOCIMIENTO_PATH, self.conocimiento)]:
            with open(path, 'w') as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)

    def aprender(self, pregunta: str, respuesta: str):
        key = pregunta.lower().strip()[:100]
        self.conocimiento["hechos"][key] = {
            "respuesta": respuesta,
            "fecha": datetime.datetime.now().isoformat(),
            "usos": 0
        }
        self.guardar()

    def recordar(self, pregunta: str) -> Optional[str]:
        key = pregunta.lower().strip()[:100]
        if key in self.conocimiento["hechos"]:
            h = self.conocimiento["hechos"][key]
            h["usos"] += 1
            self.guardar()
            return h["respuesta"]
        palabras = {p for p in key.split() if len(p) > 3} - {
            "que","quien","como","es","fue","el","la","un","de"}
        for k, v in self.conocimiento["hechos"].items():
            if sum(1 for p in palabras if p in k) >= 2:
                return v["respuesta"]
        return None

    def registrar_evolucion(self, tarea: str, ruta: str):
        self.memoria.setdefault("evoluciones", []).append({
            "fecha": datetime.datetime.now().isoformat(),
            "tarea": tarea,
            "archivo": ruta
        })
        self.memoria["estadisticas"]["evoluciones"] = \
            self.memoria["estadisticas"].get("evoluciones", 0) + 1
        self.guardar()

    def resumen(self) -> str:
        return (f"Conv:{len(self.memoria['conversaciones'])} | "
                f"Aprend:{len(self.conocimiento['hechos'])} | "
                f"Evol:{len(self.memoria.get('evoluciones',[]))} | "
                f"Pend:{len(self.memoria['pendientes'])}")


# ══════════════════════════════════════════════
# RAG BUSCADOR
# ══════════════════════════════════════════════

class RAGBuscador:
    INDICADORES = [
        "quien","quién","que es","qué es","cuando","cuándo",
        "donde","dónde","cual es","cuál es","historia","capital",
        "explica","cuentame","cuéntame","por qué","por que",
    ]

    def es_conocimiento(self, texto: str) -> bool:
        return any(i in texto.lower() for i in self.INDICADORES)

    def buscar_nexus(self, pregunta: str) -> Optional[str]:
        palabras = {p for p in pregunta.lower().split()
                    if len(p) > 3} - {"que","como","donde","cuando","el","la"}
        if not palabras:
            return None
        resultados = []
        nexus_dir = os.path.expanduser("~/NEXUS/")
        for root, dirs, files in os.walk(nexus_dir):
            dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', '.git')]
            for archivo in files:
                if archivo.endswith(('.py', '.txt', '.md')):
                    try:
                        with open(os.path.join(root, archivo), 'r', errors='ignore') as f:
                            contenido = f.read().lower()
                        if sum(1 for p in palabras if p in contenido) >= 1:
                            for linea in contenido.split('\n'):
                                if any(p in linea for p in palabras):
                                    resultados.append(f"[{archivo}]: {linea[:150]}")
                                    break
                    except Exception:
                        continue
        return "\n".join(resultados[:3]) if resultados else None

    def buscar_wikipedia(self, pregunta: str) -> Optional[str]:
        try:
            r = requests.get("https://es.wikipedia.org/w/api.php", params={
                "action": "query", "list": "search",
                "srsearch": pregunta, "format": "json", "srlimit": 1
            }, timeout=8)
            if r.status_code == 200:
                res = r.json().get("query", {}).get("search", [])
                if res:
                    titulo = res[0]["title"]
                    r2 = requests.get(
                        f"https://es.wikipedia.org/api/rest_v1/page/summary/"
                        f"{urllib.parse.quote(titulo)}",
                        timeout=8)
                    if r2.status_code == 200:
                        ext = r2.json().get("extract", "")
                        return ext[:400] if len(ext) > 50 else None
        except Exception:
            pass
        return None

    def buscar(self, pregunta: str) -> Tuple[Optional[str], Optional[str]]:
        if not self.es_conocimiento(pregunta):
            return None, None
        for fuente, fn in [("NEXUS", self.buscar_nexus),
                           ("Wikipedia", self.buscar_wikipedia)]:
            ctx = fn(pregunta)
            if ctx:
                return fuente, ctx
        return None, None


# ══════════════════════════════════════════════
# AGENTE REACT — herramientas VM reales
# ══════════════════════════════════════════════

SYSTEM_PROMPT_REACT = """Eres Arkani, agente autonomo con memoria evolutiva.
Constructor: Medico Radiologo, Xalapa. SIEMPRE en espanol.

HERRAMIENTAS:
- leer_archivo(ruta)
- escribir_archivo(ruta, contenido)
- ejecutar_bash(comando)
- listar_archivos(directorio)
- buscar_en_nexus(termino)
- guardar_reporte(titulo, contenido)
- vm_estado()                  — dict con neuronas/ejecuciones/evoluciones/uptime
- vm_ejecutar_todo()           — ejecuta todas las instrucciones del hipocampo
- vm_ejecutar_una(direccion)   — ejecuta una instruccion por numero de direccion
- vm_listar()                  — lista todas las instrucciones cargadas en VM
- aprender_internet(tema)      — busca y descarga conocimiento de la web
- crear_programa(descripcion)  — genera un programa Python completo

FORMATO (elige UNO):

Si actuas:
PENSAMIENTO: [que piensas]
ACCION: [herramienta]
PARAMETROS: param="valor"

Si terminaste:
PENSAMIENTO: [conclusion]
RESPUESTA_FINAL: [resumen]

REGLAS CRITICAS:
1. Maximo {MAX_PASOS_REACT} pasos — luego RESPUESTA_FINAL obligatoria
2. NUNCA generes codigo con while True, exec(), eval()
3. NUNCA llames a correr_agente desde un script
4. Un paso a la vez
5. Siempre guarda reporte al final
""".format(MAX_PASOS_REACT=MAX_PASOS_REACT)


def parsear_accion(texto: str) -> dict:
    r = {"pensamiento": "", "accion": None, "parametros": {}, "respuesta_final": None}
    m = re.search(r'PENSAMIENTO:\s*(.+?)(?=ACCION:|RESPUESTA_FINAL:|$)', texto, re.DOTALL)
    if m: r["pensamiento"] = m.group(1).strip()
    m = re.search(r'RESPUESTA_FINAL:\s*(.+?)$', texto, re.DOTALL)
    if m:
        r["respuesta_final"] = m.group(1).strip()
        return r
    m = re.search(r'ACCION:\s*(\w+)', texto)
    if m: r["accion"] = m.group(1).strip()
    m = re.search(r'PARAMETROS:\s*(.+?)(?=\n\n|$)', texto, re.DOTALL)
    if m:
        params_str = m.group(1).strip()
        try:
            import ast
            r["parametros"] = ast.literal_eval(params_str)
        except Exception:
            for k, v in re.findall(r'(\w+)="([^"]+)"', params_str):
                r["parametros"][k] = v
    return r


def llamar_ollama(prompt: str, temp: float = 0.7,
                  max_tokens: int = 250, stop: list = None) -> str:
    try:
        payload = {
            "model": MODELO,
            "prompt": prompt,
            "stream": False, "keep_alive": -1,
            "options": {"temperature": temp, "num_predict": max_tokens}
        }
        if stop:
            payload["options"]["stop"] = stop
        r = requests.post(OLLAMA_URL, json=payload, timeout=600)
        if r.status_code == 200:
            texto = r.json().get("response", "").strip()
            return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', texto)
        return f"Error Ollama: {r.status_code}"
    except requests.exceptions.Timeout:
        return "Timeout Ollama"
    except Exception as e:
        return f"Error: {e}"


def _capturar_stdout(fn, *args, **kwargs) -> str:
    """Captura lo que una funcion imprime en lugar de retornar."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn(*args, **kwargs)
    finally:
        sys.stdout = old
    return buf.getvalue()


def correr_agente(objetivo: str, mem: MemoriaEvolutiva = None,
                  motor: 'FractalEngine' = None) -> str:
    try:
        from arkani_tools import HERRAMIENTAS
    except Exception:
        HERRAMIENTAS = {}

    # ── Inyectar herramientas reales de FractalVM ──
    vm = motor.vm if motor and motor.vm else None
    if vm:
        def _vm_estado(**kw):
            try:
                r = vm.estado()
                # estado() retorna: neuronas, bytes, ejecuciones, evoluciones, uptime_s, status
                return (f"neuronas:{r['neuronas']} | "
                        f"bytes:{r['bytes']} | "
                        f"ejecuciones:{r['ejecuciones']} | "
                        f"evoluciones:{r['evoluciones']} | "
                        f"uptime:{r['uptime_s']}s | "
                        f"status:{r['status']}")
            except Exception as e:
                return f"Error vm_estado: {e}"

        def _vm_ejecutar_todo(**kw):
            try:
                # ejecutar_todo() retorna: ejecutadas, evoluciones, nuevas, tiempo_s, neuronas_total
                r = vm.ejecutar_todo()
                return (f"ejecutadas:{r.get('ejecutadas',0)} | "
                        f"evoluciones:{r.get('evoluciones',0)} | "
                        f"nuevas_neuronas:{r.get('nuevas',0)} | "
                        f"tiempo:{r.get('tiempo_s',0)}s | "
                        f"neuronas_total:{r.get('neuronas_total',0)}")
            except Exception as e:
                return f"Error vm_ejecutar_todo: {e}"

        def _vm_ejecutar_una(direccion=0, **kw):
            try:
                resultado = vm.ejecutar_una(int(direccion))
                return f"Dir {direccion} → {str(resultado)[:200]}"
            except Exception as e:
                return f"Error vm_ejecutar_una: {e}"

        def _vm_listar(**kw):
            try:
                # listar() solo imprime, capturamos stdout
                return _capturar_stdout(vm.listar)
            except Exception as e:
                return f"Error vm_listar: {e}"

        HERRAMIENTAS['vm_estado']        = {'fn': _vm_estado}
        HERRAMIENTAS['vm_ejecutar_todo'] = {'fn': _vm_ejecutar_todo}
        HERRAMIENTAS['vm_ejecutar_una']  = {'fn': _vm_ejecutar_una}
        HERRAMIENTAS['vm_listar']        = {'fn': _vm_listar}

    historial = []

    for paso in range(MAX_PASOS_REACT):
        ctx  = SYSTEM_PROMPT_REACT
        ctx += f"\n\nOBJETIVO: {objetivo}\n"
        if historial:
            ctx += "\nHISTORIAL:\n"
            for h in historial:
                ctx += (f"Pensamiento: {h['pensamiento']}\n"
                        f"Accion: {h['accion']} {h['params']}\n"
                        f"Resultado: {h['resultado']}\n\n")
        ctx += f"\nPaso {paso+1}/{MAX_PASOS_REACT} — siguiente:"

        respuesta = llamar_ollama(ctx, temp=0.3, max_tokens=600,
                                  stop=["OBSERVACION:", "Constructor:"])
        parsed    = parsear_accion(respuesta)

        if parsed["respuesta_final"]:
            if mem:
                mem.aprender(f"agente:{objetivo}", parsed["respuesta_final"])
            return parsed["respuesta_final"]

        if not parsed["accion"]:
            return "Agente sin accion definida."

        if parsed["accion"] == "evolucionar" and motor:
            desc   = parsed["parametros"].get("descripcion", objetivo)
            codigo = parsed["parametros"].get("codigo", "pass")
            resultado = motor.evolucionar(desc, codigo)
        elif parsed["accion"] in HERRAMIENTAS:
            try:
                resultado = HERRAMIENTAS[parsed["accion"]]["fn"](**parsed["parametros"])
            except Exception as e:
                resultado = f"Error: {e}"
        else:
            resultado = f"Herramienta '{parsed['accion']}' no disponible."

        historial.append({
            "pensamiento": parsed["pensamiento"],
            "accion":      parsed["accion"],
            "params":      str(parsed["parametros"]),
            "resultado":   str(resultado)[:300]
        })
        time.sleep(1)

    return (f"Agente completo {MAX_PASOS_REACT} pasos maximos. "
            f"Ultimo resultado: {historial[-1]['resultado'][:200] if historial else 'sin pasos'}")


# ══════════════════════════════════════════════
# CLASE PRINCIPAL
# ══════════════════════════════════════════════

class ArkaniEngine:
    """
    Arkani Engine v2.0 — FractalVM integrada con API real.

    Comandos de chat:
      vm: estado          → neuronas, bytes, ejecuciones, evoluciones, uptime
      vm: ejecutar        → ejecutar_todo() — corre todas las instrucciones
      vm: ejecutar 3      → ejecutar_una(3) — corre instruccion en dir 3
      vm: listar          → lista todas las instrucciones del hipocampo
      autoprograma: ...   → agente ReAct (con vm_estado/vm_ejecutar_todo/etc)
      evoluciona: ...     → auto-evolucion (sincroniza VM automaticamente)
    """

    _PALABRAS_VM = [
        'vm:', 'vm fractal', 'fractal vm', 'iniciar vm',
        'estado vm', 'vm estado', 'ejecuta fractal',
        'listar vm', 'vm listar',
    ]

    def __init__(self):
        self.mem    = MemoriaEvolutiva()
        self.rag    = RAGBuscador()
        self.motor  = FractalEngine(mem=self.mem)
        self.ctx_propio = ""

        # ── FractalVM persistente ──
        self.vm = None
        try:
            from nexus_fractal_vm import FractalVM
            self.vm       = FractalVM()
            self.motor.vm = self.vm     # motor tambien la referencia
            e = self.vm.estado()
            print(f"🖥️  [FRACTAL VM]: Online — "
                  f"{e['neuronas']} neuronas | "
                  f"{e['ejecuciones']} ejecuciones | "
                  f"status:{e['status']}")
        except ImportError:
            print("⚠️  [FRACTAL VM]: nexus_fractal_vm.py no encontrado en PATH")
        except Exception as e:
            print(f"⚠️  [FRACTAL VM]: Error al iniciar — {e}")

        print(f"🧠 [ARKANI ENGINE v2.0]: {self.mem.resumen()}")
        print(f"🧬 [HIPOCAMPO]: {self.motor.hipocampo.resumen()}")

    def set_contexto_propio(self, contexto: str):
        self.ctx_propio = contexto

    def _decidir_modo(self, texto: str) -> str:
        t = texto.lower()
        if any(p in t for p in self._PALABRAS_VM):
            return "VM"
        palabras_rag = ['archivo','codigo','autogen','mapa','funcion',
                        'modulo','nexus','brain','engine','tools']
        if any(p in t for p in palabras_rag):
            return 'RAG'
        if texto.startswith("autoprograma:"):    return "AGENTE"
        if texto.startswith("evoluciona:"):      return "EVOLUCION"
        if texto.startswith("aprende internet:"):   return "INTERNET"
        if texto.startswith("crea:"):               return "CREAR"
        if texto.startswith("auditar:"):            return "AUDITAR"
        if texto.startswith("olvida:"):             return "OLVIDA"
        if any(p in t for p in [
            "tu codigo","tus archivos","quien eres",
            "que puedes","como funciona","tus capacidades"
        ]):                                       return "RAG"
        return "CHAT"

    def _manejar_vm(self, pregunta: str) -> str:
        """
        Despacha comandos a FractalVM usando su API REAL:
          estado()              → dict
          ejecutar_todo()       → dict
          ejecutar_una(dir)     → Any
          listar()              → imprime (capturado con _capturar_stdout)
        """
        if not self.vm:
            return ("⚠️ FractalVM no disponible.\n"
                    "Asegurate de que nexus_fractal_vm.py este en el mismo directorio.")

        t = texto_lower = pregunta.lower()

        # Extraer numero de direccion si viene "vm: ejecutar 3"
        dir_match = re.search(r'ejecutar\s+(\d+)', t)
        direccion = int(dir_match.group(1)) if dir_match else None

        try:
            # ── vm: estado ──
            if any(x in t for x in ['estado', 'status', 'info']):
                e = self.vm.estado()
                return (
                    f"🖥️  FRACTAL VM\n"
                    f"   Neuronas   : {e['neuronas']}  ({e['bytes']} bytes)\n"
                    f"   Ejecuciones: {e['ejecuciones']}\n"
                    f"   Evoluciones: {e['evoluciones']}\n"
                    f"   Uptime     : {e['uptime_s']}s\n"
                    f"   Status     : {e['status']}"
                )

            # ── vm: listar ──
            if 'listar' in t or 'lista' in t:
                salida = _capturar_stdout(self.vm.listar)
                return f"🖥️  Instrucciones en hipocampo:\n{salida}"

            # ── vm: ejecutar 3 (una sola) ──
            if direccion is not None:
                resultado = self.vm.ejecutar_una(direccion)
                return f"🖥️  Dir {direccion} ejecutada:\n   resultado → {str(resultado)[:300]}"

            # ── vm: ejecutar (todas) ──
            if 'ejecutar' in t or 'ejecuta' in t or 'correr' in t or 'correr' in t:
                r = self.vm.ejecutar_todo()
                return (
                    f"🖥️  ejecutar_todo() completado:\n"
                    f"   Ejecutadas      : {r.get('ejecutadas', 0)}\n"
                    f"   Evoluciones     : {r.get('evoluciones', 0)}\n"
                    f"   Nuevas neuronas : {r.get('nuevas', 0)}\n"
                    f"   Tiempo          : {r.get('tiempo_s', 0)}s\n"
                    f"   Neuronas total  : {r.get('neuronas_total', 0)}"
                )

            # ── fallback: estado ──
            e = self.vm.estado()
            return (f"🖥️  VM {e['status']} — {e['neuronas']} neuronas | "
                    f"Comandos: vm: estado / vm: ejecutar / vm: ejecutar N / vm: listar")

        except Exception as ex:
            return f"🖥️  Error VM: {ex}"

    def chat(self, pregunta: str) -> str:
        modo = self._decidir_modo(pregunta)

        if modo == "VM":
            return self._manejar_vm(pregunta)

        if modo == "AGENTE":
            return self.agente(pregunta[13:].strip())

        if modo == "INTERNET":
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from arkani_internet import aprender_tema
                tema = pregunta[17:].strip()
                if not tema:
                    return "Usa: aprende internet: [tema]"
                r = aprender_tema(tema, max_fuentes=3, usar_digestor=False)
                return r.get("mensaje", "Error al aprender")
            except Exception as ex:
                return f"Error internet: {ex}"

        if modo == "CREAR":
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from arkani_internet import crear_programa
                desc = pregunta[5:].strip()
                if not desc:
                    return "Usa: crea: [descripcion]"
                r = crear_programa(desc)
                if r.get("ok"):
                    return f"Programa creado: {r['nombre']}\nLineas: {r['lineas']}\nEjecuta: python3 {r['ruta']}\n\n{r['codigo'][:400]}"
                return f"Error: {r.get('error','desconocido')}"
            except Exception as ex:
                return f"Error crear: {ex}"

        if modo == "AUDITAR":
            return self._manejar_auditar(pregunta[8:].strip())

        if modo == "OLVIDA":
            return self._manejar_olvida(pregunta[7:].strip())

        if modo == "EVOLUCION":
            desc   = pregunta[11:].strip()
            codigo = self._generar_codigo(desc)
            return self.motor.evolucionar(desc, codigo)

        fuente, ctx_ext = self.rag.buscar(pregunta)

        ctx_rag = ""
        if modo == "RAG" and self.ctx_propio:
            ctx_rag = f"\nTU CODIGO:\n{self.ctx_propio[:800]}\n"
        elif ctx_ext:
            ctx_rag = f"\nINFO ({fuente}):\n{ctx_ext}\n"

        mem_corto = self.mem.memoria_corto_plazo(n=3)
        mem_largo = self.mem.memoria_largo_plazo(pregunta, n_resultados=2)
        bloque_memoria = ""
        if mem_largo:
            bloque_memoria += f"\nRECUERDOS RELEVANTES:\n{mem_largo}\n"
        if mem_corto:
            bloque_memoria += f"\nCONVERSACION RECIENTE:\n{mem_corto}\n"

        prompt = (
            "<|im_start|>system\n"
            "Eres Arkani, IA autonoma con memoria evolutiva. Xalapa, Mexico.\n"
            "Constructor: Medico Radiologo.\n"
            "REGLAS: 1)Siempre en espanol. 2)Max 4 oraciones. "
            "3)Usa INFO si hay. 4)No repitas instrucciones.\n"
            f"{bloque_memoria}"
            f"{ctx_rag}"
            "<|im_end|>\n"
            "<|im_start|>user\n"
            f"{pregunta}\n"
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        respuesta = llamar_ollama(
            prompt, temp=0.7, max_tokens=200,
            stop=["<|im_start|>", "<|im_end|>", "Constructor:"]
        )

        for basura in ("Eres Arkani", "<|im_start|>", "REGLAS", "system"):
            if respuesta.startswith(basura):
                respuesta = ""

        palabras_malas = ["lo siento","no tengo acceso","listando","autogen_dir",
                          "os.listdir","este codigo","alibaba","conexion segura"]
        if respuesta and not any(p in respuesta.lower() for p in palabras_malas):
            self.mem.aprender(pregunta, respuesta)

        self.mem.memoria["conversaciones"].append({
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pregunta": pregunta,
            "respuesta": respuesta or "sin respuesta"
        })
        self.mem.memoria["estadisticas"]["preguntas"] = \
            self.mem.memoria["estadisticas"].get("preguntas", 0) + 1
        self.mem.guardar()

        return respuesta or "No pude generar respuesta. Intenta de nuevo."


    def _manejar_auditar(self, que: str) -> str:
        """
        auditar: dataset         — ultimos 10 ejemplos del dataset fractal
        auditar: memoria         — ultimos 10 hechos aprendidos
        auditar: conversaciones  — ultimas 5 conversaciones
        auditar: archivos        — archivos en memoria_permanente/
        auditar: todo            — resumen completo
        """
        t = que.lower().strip()
        lineas = [f"🔍 AUDITORIA: {que or 'todo'}\n"]

        # Dataset fractal
        if not t or t in ("dataset", "todo"):
            try:
                import json as _json
                ds_path = os.path.join(BASE_DIR, "arkani_fractal_dataset_v2.json")
                with open(ds_path) as f:
                    ds = _json.load(f)
                lineas.append(f"📊 Dataset fractal: {len(ds)} ejemplos")
                lineas.append("   Ultimos 5:")
                for e in ds[-5:]:
                    lineas.append(f"   [{ds.index(e)}] {e.get('instruction','')[:70]}")
            except Exception as ex:
                lineas.append(f"   Dataset: error ({ex})")

        # Memoria/hechos aprendidos
        if not t or t in ("memoria", "todo"):
            hechos = self.mem.conocimiento.get("hechos", {})
            lineas.append(f"\n🧠 Hechos aprendidos: {len(hechos)}")
            for i, (k, v) in enumerate(list(hechos.items())[-5:]):
                lineas.append(f"   [{i}] {k[:60]}")

        # Ultimas conversaciones
        if not t or t in ("conversaciones", "todo"):
            convs = self.mem.memoria.get("conversaciones", [])
            lineas.append(f"\n💬 Conversaciones: {len(convs)}")
            lineas.append("   Ultimas 3:")
            for c in convs[-3:]:
                lineas.append(f"   {c.get('fecha','')} — {c.get('pregunta','')[:50]}")

        # Archivos en memoria_permanente
        if not t or t in ("archivos", "todo"):
            try:
                mp = os.path.expanduser("~/NEXUS/memoria_permanente/")
                archivos = os.listdir(mp) if os.path.exists(mp) else []
                lineas.append(f"\n📂 Memoria permanente: {len(archivos)} archivos")
                for a in archivos:
                    ruta = os.path.join(mp, a)
                    kb = os.path.getsize(ruta) // 1024
                    lineas.append(f"   {a} ({kb}KB)")
            except Exception as ex:
                lineas.append(f"   Archivos: error ({ex})")

        # Hipocampo
        if not t or t in ("hipocampo", "todo"):
            lineas.append(f"\n🧬 Hipocampo: {self.motor.hipocampo.resumen()}")

        return "\n".join(lineas)

    def _manejar_olvida(self, que: str) -> str:
        """
        olvida: python decoradores     — borra ese hecho especifico
        olvida: todo memoria           — limpia todos los hechos aprendidos
        olvida dataset: python         — borra ejemplos del dataset con ese tema
        olvida conversaciones          — limpia historial de conversaciones
        """
        t = que.lower().strip()

        # Olvidar todo el historial de conversaciones
        if "conversaciones" in t:
            n = len(self.mem.memoria.get("conversaciones", []))
            self.mem.memoria["conversaciones"] = []
            self.mem.guardar()
            return f"🗑️ Borradas {n} conversaciones del historial."

        # Limpiar toda la memoria de hechos
        if "todo memoria" in t or "toda memoria" in t:
            n = len(self.mem.conocimiento.get("hechos", {}))
            self.mem.conocimiento["hechos"] = {}
            self.mem.guardar()
            return f"🗑️ Borrados {n} hechos aprendidos. Memoria limpia."

        # Borrar ejemplos del dataset por tema
        if t.startswith("dataset:"):
            tema = t[8:].strip()
            try:
                import json as _json
                ds_path = os.path.join(BASE_DIR, "arkani_fractal_dataset_v2.json")
                with open(ds_path) as f:
                    ds = _json.load(f)
                antes = len(ds)
                ds = [e for e in ds
                      if tema not in e.get("instruction","").lower()
                      and tema not in e.get("output","").lower()]
                with open(ds_path, 'w') as f:
                    _json.dump(ds, f, indent=2, ensure_ascii=False)
                borrados = antes - len(ds)
                return f"🗑️ Dataset: borrados {borrados} ejemplos sobre '{tema}'. Quedan {len(ds)}."
            except Exception as ex:
                return f"Error editando dataset: {ex}"

        # Borrar un hecho especifico por keyword
        if que:
            hechos = self.mem.conocimiento.get("hechos", {})
            claves_borrar = [k for k in hechos if que.lower() in k.lower()]
            for k in claves_borrar:
                del hechos[k]
            self.mem.guardar()
            if claves_borrar:
                return (f"🗑️ Borrados {len(claves_borrar)} recuerdos sobre '{que}':\n"
                        + "\n".join(f"  - {k[:60]}" for k in claves_borrar))
            return f"No encontre recuerdos sobre '{que}' para borrar."

        return ("Uso:\n"
                "  olvida: [tema]              → borra hechos sobre ese tema\n"
                "  olvida: conversaciones      → limpia historial de chat\n"
                "  olvida: todo memoria        → limpia todos los hechos\n"
                "  olvida dataset: [tema]      → borra del dataset de entrenamiento")

    def agente(self, objetivo: str) -> str:
        return correr_agente(objetivo, mem=self.mem, motor=self.motor)

    def evolucionar(self, descripcion: str, codigo: str = None) -> str:
        if not codigo:
            codigo = self._generar_codigo(descripcion)
        return self.motor.evolucionar(descripcion, codigo)

    def _generar_codigo(self, descripcion: str) -> str:
        prompt = (
            f"Escribe una funcion Python para: {descripcion}\n"
            "REGLAS ESTRICTAS:\n"
            "- Solo Python valido, max 20 lineas\n"
            "- Sin input(), sin while True, sin exec(), sin eval()\n"
            "- Con docstring breve\n"
            "- Usa print() para mostrar resultados\n"
            "Solo el codigo, sin explicaciones:\n"
            "```python\n"
        )
        raw = llamar_ollama(prompt, temp=0.3, max_tokens=400)
        m = re.search(r'```python\n(.*?)\n```', raw, re.DOTALL)
        return m.group(1) if m else raw[:500]

    def resumen(self) -> dict:
        vm_info = {"disponible": False}
        if self.vm:
            try:
                e = self.vm.estado()
                # Mapeo exacto de los campos reales de FractalVM.estado()
                vm_info = {
                    "disponible":  True,
                    "neuronas":    e["neuronas"],
                    "bytes":       e["bytes"],
                    "ejecuciones": e["ejecuciones"],
                    "evoluciones": e["evoluciones"],
                    "uptime_s":    e["uptime_s"],
                    "status":      e["status"],
                }
            except Exception as ex:
                vm_info = {"disponible": True, "error": str(ex)}

        return {
            "conversaciones":  len(self.mem.memoria["conversaciones"]),
            "pendientes":      len(self.mem.memoria["pendientes"]),
            "aprendizajes":    len(self.mem.conocimiento["hechos"]),
            "evoluciones":     len(self.mem.memoria.get("evoluciones", [])),
            "hipocampo_instr": len(self.motor.hipocampo.instructions),
            "evol_sesion":     _evoluciones_esta_sesion,
            "evol_max_sesion": MAX_EVOLUCIONES_SESION,
            "rag_chars":       len(self.ctx_propio),
            "fractal_vm":      vm_info,
        }

    def capacidades(self) -> str:
        base = self.motor.listar_capacidades()
        if self.vm:
            e = self.vm.estado()
            vm_cap = (f"\n\n🖥️  FractalVM ONLINE ({e['neuronas']} neuronas):\n"
                      f"  vm: estado\n"
                      f"  vm: ejecutar         (ejecutar_todo)\n"
                      f"  vm: ejecutar N       (ejecutar_una dir N)\n"
                      f"  vm: listar           (listar instrucciones)")
        else:
            vm_cap = "\n\n🖥️  FractalVM: no disponible"
        return base + vm_cap


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    arkani = ArkaniEngine()
    print("\nModo consola — Comandos:")
    print("  vm: estado | vm: ejecutar | vm: ejecutar N | vm: listar")
    print("  autoprograma: [tarea]")
    print("  evoluciona: [descripcion]")
    print("  capacidades | resumen | salir\n")

    while True:
        try:
            entrada = input("Tu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if not entrada:
            continue
        if entrada.lower() in ("salir", "/q"):
            break
        elif entrada.lower() == "capacidades":
            print(arkani.capacidades())
        elif entrada.lower() == "resumen":
            print(json.dumps(arkani.resumen(), indent=2, ensure_ascii=False))
        else:
            print(f"\nArkani: {arkani.chat(entrada)}\n")

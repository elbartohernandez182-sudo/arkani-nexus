"""
ARKANI ENGINE v1.0
Fusion completa: FractalCompiler + NexusCompiler + AutoEvolucion
Con protecciones anti-loop y sandbox seguro

Constructor: Medico Radiologo, Xalapa
Fecha: 27 mayo 2026
Clave: Arkani1979
"""

import os
import re
import sys
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
MODELO      = "qwen2.5:7b"

for d in [BASE_DIR, AUTOGEN_DIR, SCRIPTS_DIR]:
    os.makedirs(d, exist_ok=True)


# ══════════════════════════════════════════════
# PROTECCIONES ANTI-LOOP (lo más importante)
# ══════════════════════════════════════════════

MAX_PROFUNDIDAD_EVOLVE  = 3    # máximo 3 niveles de auto-modificación anidada
MAX_EVOLUCIONES_SESION  = 10   # máximo 10 evoluciones por sesión
MAX_PASOS_REACT         = 3    # máximo 3 pasos del agente ReAct
MAX_SEGUNDOS_EXEC       = 10   # timeout para exec() de código mutado
MAX_SEGUNDOS_SCRIPT     = 15   # timeout para subprocess de scripts generados

# Patrones prohibidos en código autogenerado
PATRONES_PROHIBIDOS = [
    r"while\s+True",           # loop infinito
    r"exec\s*\(",              # exec anidado
    r"eval\s*\(",              # eval anidado
    r"os\.system\s*\(",        # shell directo
    r"subprocess\.Popen",      # proceso sin timeout
    r"__import__\s*\(",        # importación dinámica
    r"open\s*\(.+['\"]w['\"]", # escritura fuera de autogen
    r"self_modify",            # recursión de mutación
    r"correr_agente",          # agente llamándose a sí mismo
]

_profundidad_evolve_actual = 0
_evoluciones_esta_sesion   = 0


def verificar_codigo_seguro(codigo: str) -> Tuple[bool, str]:
    """
    Verifica que el código no tenga patrones peligrosos.
    Retorna (es_seguro, motivo).
    """
    for patron in PATRONES_PROHIBIDOS:
        if re.search(patron, codigo, re.IGNORECASE):
            return False, f"Patrón prohibido detectado: {patron}"

    # Verificar sintaxis Python
    try:
        import ast
        ast.parse(codigo)
    except SyntaxError as e:
        return False, f"Error de sintaxis: {e}"

    return True, "OK"


def timeout_handler(signum, frame):
    raise TimeoutError("Ejecución cancelada: timeout de seguridad")


def exec_seguro(codigo: str, contexto_permitido: dict = None) -> Tuple[bool, str]:
    """
    Ejecuta código en un namespace AISLADO con timeout.
    NO usa globals() — protección contra acceso al sistema.
    """
    global _profundidad_evolve_actual

    # 1. Verificar profundidad de recursión
    if _profundidad_evolve_actual >= MAX_PROFUNDIDAD_EVOLVE:
        return False, f"⛔ Profundidad máxima de evolución ({MAX_PROFUNDIDAD_EVOLVE}) alcanzada"

    # 2. Verificar límite de sesión
    global _evoluciones_esta_sesion
    if _evoluciones_esta_sesion >= MAX_EVOLUCIONES_SESION:
        return False, f"⛔ Límite de evoluciones por sesión ({MAX_EVOLUCIONES_SESION}) alcanzado"

    # 3. Verificar patrones peligrosos
    seguro, motivo = verificar_codigo_seguro(codigo)
    if not seguro:
        return False, f"⛔ Código bloqueado: {motivo}"

    # 4. Namespace aislado — solo lo que explícitamente permitimos
    namespace = {
        "__builtins__": {
            "print": print,
            "len": len,
            "range": range,
            "str": str,
            "int": int,
            "float": float,
            "list": list,
            "dict": dict,
            "bool": bool,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "zip": zip,
        }
    }
    if contexto_permitido:
        namespace.update(contexto_permitido)

    # 5. Ejecutar con timeout
    try:
        _profundidad_evolve_actual += 1
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(MAX_SEGUNDOS_EXEC)
        exec(codigo, namespace)
        signal.alarm(0)
        _profundidad_evolve_actual -= 1
        _evoluciones_esta_sesion += 1
        return True, "Ejecutado con éxito en sandbox"
    except TimeoutError:
        _profundidad_evolve_actual -= 1
        return False, f"⛔ Timeout: el código tardó más de {MAX_SEGUNDOS_EXEC}s"
    except Exception as e:
        _profundidad_evolve_actual -= 1
        return False, f"⛔ Error en ejecución: {e}"
    finally:
        signal.alarm(0)


# ══════════════════════════════════════════════
# LENGUAJE FRACTAL — 7 OPERACIONES (16 bytes)
# ══════════════════════════════════════════════

class FractalOp(Enum):
    SUM    = 0xA0  # Suma multi-escala
    IF     = 0xA1  # Condicional fractal
    LOOP   = 0xA3  # Iteración auto-similar
    SPAWN  = 0xA5  # Crear nueva instrucción
    FOLD   = 0xA7  # Plegar datos
    LINK   = 0xA9  # Conectar instrucciones
    EVOLVE = 0xF1  # Auto-modificación


class FractalInstruction:
    """16 bytes exactos: firma + op + escala + flags + fold + link + hash"""

    FRACTAL_ID = 0x7C
    MAX_SCALE  = 31

    def __init__(self, op: FractalOp, scale: int,
                 fold_target: Optional[str] = None,
                 link_to: Optional[int] = None):
        self.op          = op
        self.scale       = min(scale, self.MAX_SCALE)
        self.fold_target = fold_target
        self.link_to     = link_to  # None ≠ 0 (0 es la primera instrucción)
        self.address     = None

    def to_bytes(self) -> bytes:
        b0, b1, b2 = self.FRACTAL_ID, self.op.value, self.scale
        flags = 0
        if self.fold_target:              flags |= 0x01
        if self.link_to is not None:      flags |= 0x02  # 0 es dirección válida
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
    """Memoria binaria persistente de Arkani."""

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
# MOTOR FRACTAL — une los dos compiladores
# ══════════════════════════════════════════════

class FractalEngine:
    """
    Motor unificado:
    - FractalCompiler (96 bytes, firma 1979, exec seguro)
    - NexusCompiler   (16 bytes, Hipocampo binario)
    Con todas las protecciones anti-loop.
    """

    def __init__(self, mem=None):
        self.hipocampo = Hipocampo()
        self.mem       = mem          # MemoriaEvolutiva (opcional)
        self.primitives = {
            '⟦SUM⟧':    lambda a, b: a + b,
            '⟦EVOLVE⟧': self._mutar,
            '⟦FOLD⟧':   self._plegar,
        }
        self.op_map = {n: o for n, o in
                       [(o.name, o) for o in FractalOp]}

    # ── Mutación segura (reemplaza exec en globals()) ──

    def _mutar(self, codigo: str) -> str:
        print(f"🧬 ⟦EVOLVE⟧: iniciando mutación segura...")
        ok, msg = exec_seguro(codigo)
        if ok:
            print(f"   ✅ {msg}")
            return "EVOLVED"
        print(f"   {msg}")
        return f"BLOCKED: {msg}"

    def _plegar(self, data, fold_fn=None) -> str:
        return "COMPRESSED_NEXUS_DATA"

    # ── Compilar a binario 96 bytes con firma 1979 ──

    def compilar_96(self, descripcion: str) -> bytes:
        """Genera binario de 96 bytes con firma \x19\x79 (1979)."""
        firma    = b'\x19\x79'
        hash_desc = hashlib.sha256(descripcion.encode()).digest()[:30]
        timestamp = struct.pack('<Q', int(time.time()))[:8]
        padding   = os.urandom(96 - 2 - 30 - 8)
        return firma + hash_desc + timestamp + padding

    # ── Compilar a instrucción de 16 bytes para Hipocampo ──

    def compilar_16(self, linea: str) -> Optional[FractalInstruction]:
        """Compila una línea .nl a FractalInstruction de 16 bytes."""
        linea = linea.strip()
        if not linea or linea.startswith('#'):
            return None
        op_m = re.search(r'⟦(\w+)⟧', linea)
        if not op_m or op_m.group(1) not in self.op_map:
            return None
        op      = self.op_map[op_m.group(1)]
        scale   = int(s.group(1)) if (s := re.search(r'\[SCALE:(\d+)\]', linea)) else 1
        fold    = f.group(1) if (f := re.search(r'\[FOLD:([^\]]+)\]', linea)) else None
        link    = int(lk.group(1)) if (lk := re.search(r'\[LINK:(\d+)\]', linea)) else None
        return FractalInstruction(op, scale, fold, link)

    # ── Evolución completa (el proceso principal) ──

    def evolucionar(self, descripcion: str, codigo_python: str) -> str:
        """
        Proceso completo de auto-evolución con todas las protecciones:
        1. Verifica código
        2. Exec en sandbox
        3. Guarda en autogen/ como .py
        4. Genera binario 96 bytes con firma 1979
        5. Registra instrucción en Hipocampo (16 bytes)
        6. Registra en memoria evolutiva
        """
        global _evoluciones_esta_sesion

        # Verificar límites
        if _evoluciones_esta_sesion >= MAX_EVOLUCIONES_SESION:
            return f"⛔ Límite de {MAX_EVOLUCIONES_SESION} evoluciones por sesión alcanzado"

        # 1. Verificar seguridad del código
        seguro, motivo = verificar_codigo_seguro(codigo_python)
        if not seguro:
            return f"⛔ Evolución bloqueada: {motivo}"

        # 2. Exec en sandbox
        ok, msg = exec_seguro(codigo_python)
        estado_exec = "✅ mutación en memoria" if ok else f"⚠️ sandbox bloqueó ({msg})"

        # 3. Guardar en autogen/
        nombre = re.sub(r'[^a-z0-9_]', '_',
                        descripcion.lower().replace(' ', '_'))[:40]
        if not nombre.startswith(('fn_', 'node_')):
            nombre = f"fn_{nombre}"
        ruta_py = os.path.join(AUTOGEN_DIR, f"{nombre}.py")
        header  = (f"# ARKANI AUTO-GEN — {descripcion}\n"
                   f"# Generado: {datetime.datetime.now().isoformat()}\n"
                   f"# Evoluciones sesión: {_evoluciones_esta_sesion + 1}"
                   f"/{MAX_EVOLUCIONES_SESION}\n\n")
        with open(ruta_py, 'w') as f:
            f.write(header + codigo_python)

        # 4. Binario 96 bytes con firma 1979
        binario  = self.compilar_96(descripcion)
        ruta_bin = ruta_py.replace('.py', '.bin')
        with open(ruta_bin, 'wb') as f:
            f.write(binario)

        # 5. Instrucción en Hipocampo
        inst = FractalInstruction(FractalOp.EVOLVE, scale=min(
            _evoluciones_esta_sesion + 1, FractalInstruction.MAX_SCALE
        ), fold_target="self")
        addr = self.hipocampo.agregar(inst)

        # 6. Registrar en memoria evolutiva
        if self.mem:
            self.mem.registrar_evolucion(descripcion, ruta_py)

        _evoluciones_esta_sesion += 1

        return (f"🧬 Evolución #{_evoluciones_esta_sesion} completada:\n"
                f"   {estado_exec}\n"
                f"   📄 {os.path.basename(ruta_py)}\n"
                f"   🔵 {os.path.basename(ruta_bin)} (96B, firma \\x19\\x79)\n"
                f"   💾 Hipocampo dir {addr}: {inst}\n"
                f"   📊 {self.hipocampo.resumen()}")

    def listar_capacidades(self) -> str:
        try:
            archivos = sorted([f for f in os.listdir(AUTOGEN_DIR)
                               if f.endswith('.py')])
            if not archivos:
                return "Sin módulos autogenerados aún."
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
# AGENTE REACT con protecciones
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
            "stream": False,
            "options": {"temperature": temp, "num_predict": max_tokens}
        }
        if stop:
            payload["options"]["stop"] = stop
        r = requests.post(OLLAMA_URL, json=payload, timeout=400)
        if r.status_code == 200:
            texto = r.json().get("response", "").strip()
            return re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', texto)
        return f"Error Ollama: {r.status_code}"
    except requests.exceptions.Timeout:
        return "Timeout Ollama"
    except Exception as e:
        return f"Error: {e}"


def correr_agente(objetivo: str, mem: MemoriaEvolutiva = None,
                  motor: 'FractalEngine' = None) -> str:
    """Bucle ReAct con límite estricto de pasos."""
    try:
        from arkani_tools import HERRAMIENTAS
    except Exception:
        HERRAMIENTAS = {}

    historial = []

    for paso in range(MAX_PASOS_REACT):
        ctx = SYSTEM_PROMPT_REACT
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
            return "Agente sin acción definida."

        # Ejecutar herramienta
        if parsed["accion"] == "evolucionar" and motor:
            desc   = parsed["parametros"].get("descripcion", objetivo)
            codigo = parsed["parametros"].get("codigo", "pass")
            resultado = motor.evolucionar(desc, codigo)
        elif parsed["accion"] in HERRAMIENTAS:
            try:
                resultado = HERRAMIENTAS[parsed["accion"]]["fn"](
                    **parsed["parametros"])
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

    # Forzar cierre al llegar al límite
    return (f"Agente completó {MAX_PASOS_REACT} pasos máximos. "
            f"Último resultado: {historial[-1]['resultado'][:200] if historial else 'sin pasos'}")


# ══════════════════════════════════════════════
# CLASE PRINCIPAL — importada por arkani_web.py
# ══════════════════════════════════════════════

class ArkaniEngine:
    """
    Clase principal unificada.
    arkani_web.py solo necesita importar esta.

    Uso:
        arkani = ArkaniEngine()
        arkani.chat("hola")
        arkani.agente("lista archivos py")
        arkani.evolucionar("calcular volumen nodulo", codigo_python)
    """

    def __init__(self):
        self.mem    = MemoriaEvolutiva()
        self.rag    = RAGBuscador()
        self.motor  = FractalEngine(mem=self.mem)
        self.ctx_propio = ""  # RAG de sus propios archivos
        print(f"🧠 [ARKANI ENGINE]: {self.mem.resumen()}")
        print(f"🧬 [HIPOCAMPO]: {self.motor.hipocampo.resumen()}")

    def set_contexto_propio(self, contexto: str):
        self.ctx_propio = contexto

    # ── Decidir modo según el texto ──────────

    def _decidir_modo(self, texto: str) -> str:
        # Detectar preguntas sobre archivos propios
        palabras_rag = ['archivo','codigo','autogen','mapa','funcion','modulo','nexus','brain','engine','tools']
        if any(p in texto.lower() for p in palabras_rag):
            return 'RAG'
        t = texto.lower()
        if texto.startswith("autoprograma:"):      return "AGENTE"
        if texto.startswith("evoluciona:"):        return "EVOLUCION"
        if any(p in t for p in [
            "tu codigo", "tus archivos", "quien eres",
            "que puedes", "como funciona", "tus capacidades"
        ]):                                         return "RAG"
        return "CHAT"

    # ── Chat normal ──────────────────────────

    def chat(self, pregunta: str) -> str:
        modo = self._decidir_modo(pregunta)

        if modo == "AGENTE":
            return self.agente(pregunta[13:].strip())

        if modo == "EVOLUCION":
            # Sin código explícito — pedir a Ollama que lo genere
            desc   = pregunta[11:].strip()
            codigo = self._generar_codigo(desc)
            return self.motor.evolucionar(desc, codigo)

        # Intentar memoria
        recordado = self.mem.recordar(pregunta)
        if recordado and "Error" not in recordado:
            return f"(Recuerdo) {recordado}"

        # RAG externo
        fuente, ctx_ext = self.rag.buscar(pregunta)

        # Construir prompt según modo
        ctx_rag = ""
        if modo == "RAG" and self.ctx_propio:
            ctx_rag = f"\nTU CODIGO:\n{self.ctx_propio[:800]}\n"
        elif ctx_ext:
            ctx_rag = f"\nINFO ({fuente}):\n{ctx_ext}\n"

        pends = self.mem.memoria.get("pendientes", [])
        pend_str = "\n".join(f"  {i+1}. {p}"
                             for i, p in enumerate(pends)) or "  (ninguno)"

        prompt = (
            "<|im_start|>system\n"
            "Eres Arkani, IA autonoma con memoria evolutiva. Xalapa, Mexico.\n"
            "Constructor: Medico Radiologo.\n"
            "REGLAS: 1)Siempre en espanol. 2)Max 4 oraciones. "
            "3)Usa INFO si hay. 4)No repitas instrucciones.\n"
            f"\nPENDIENTES:\n{pend_str}\n"
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

        # Limpiar basura del modelo
        for basura in ("Eres Arkani", "<|im_start|>", "REGLAS", "system"):
            if respuesta.startswith(basura):
                respuesta = ""

        # Solo aprender respuestas buenas
        palabras_malas = ["lo siento","no tengo acceso","listando","autogen_dir","os.listdir","este codigo","alibaba","conexion segura"]
        if respuesta and not any(p in respuesta.lower() for p in palabras_malas):
            self.mem.aprender(pregunta, respuesta)

        # Guardar conversación
        self.mem.memoria["conversaciones"].append({
            "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "pregunta": pregunta,
            "respuesta": respuesta or "sin respuesta"
        })
        self.mem.memoria["estadisticas"]["preguntas"] = \
            self.mem.memoria["estadisticas"].get("preguntas", 0) + 1
        self.mem.guardar()

        return respuesta or "No pude generar respuesta. Intenta de nuevo."

    # ── Agente ReAct ─────────────────────────

    def agente(self, objetivo: str) -> str:
        return correr_agente(objetivo, mem=self.mem, motor=self.motor)

    # ── Evolución con código explícito ───────

    def evolucionar(self, descripcion: str, codigo: str = None) -> str:
        if not codigo:
            codigo = self._generar_codigo(descripcion)
        return self.motor.evolucionar(descripcion, codigo)

    # ── Generar código con Ollama ─────────────

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

    # ── Estado del sistema ────────────────────

    def resumen(self) -> dict:
        return {
            "conversaciones":  len(self.mem.memoria["conversaciones"]),
            "pendientes":      len(self.mem.memoria["pendientes"]),
            "aprendizajes":    len(self.mem.conocimiento["hechos"]),
            "evoluciones":     len(self.mem.memoria.get("evoluciones", [])),
            "hipocampo_instr": len(self.motor.hipocampo.instructions),
            "evol_sesion":     _evoluciones_esta_sesion,
            "evol_max_sesion": MAX_EVOLUCIONES_SESION,
            "rag_chars":       len(self.ctx_propio)
        }

    def capacidades(self) -> str:
        return self.motor.listar_capacidades()


# ══════════════════════════════════════════════
# MAIN — prueba en consola
# ══════════════════════════════════════════════

if __name__ == "__main__":
    arkani = ArkaniEngine()
    print("\nModo consola. Comandos:")
    print("  'agente: [tarea]'")
    print("  'evoluciona: [descripcion]'")
    print("  'capacidades'")
    print("  'resumen'")
    print("  'salir'\n")

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

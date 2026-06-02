import json
import os
import re
import datetime
import requests
import time
import subprocess
import urllib.parse
from typing import Optional, Dict, Tuple

# ============================================
# ARKANI CORE v2.0 - AGENTE AUTONOMO
# Constructor: Medico Radiologo, Xalapa
# Merge: Claude v1.6 + DeepSeek v3.0
# Inicio: 29 abril 2026 | v2.0: 06 mayo 2026
# ============================================

BASE_DIR        = os.path.expanduser("~/NEXUS/NEXUS-LANG/")
NEXUS_DIR       = os.path.expanduser("~/NEXUS/")
MEMORIA_PATH    = os.path.join(BASE_DIR, "memoria_arkani.json")
CONOCIMIENTO_PATH = os.path.join(BASE_DIR, "conocimiento_arkani.json")
SCRIPTS_DIR     = os.path.join(BASE_DIR, "scripts_arkani/")
OLLAMA_URL      = "http://127.0.0.1:11434/api/generate"
MODELO          = "qwen2.5:7b"   # ligero, rapido, instalado

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(SCRIPTS_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════

def limpiar_texto(texto: str) -> str:
    texto = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', texto)
    texto = re.sub(r'[\x00-\x1f\x7f]', '', texto)
    return texto.strip()


# ══════════════════════════════════════════════════════════════
# MEMORIA EVOLUTIVA (DeepSeek + mejoras Claude)
# ══════════════════════════════════════════════════════════════

class MemoriaEvolutiva:
    def __init__(self):
        self.memoria    = self._cargar(MEMORIA_PATH, self._mem_default())
        self.conocimiento = self._cargar(CONOCIMIENTO_PATH, self._con_default())

    def _mem_default(self) -> Dict:
        return {
            "version": "2.0",
            "fecha_creacion": datetime.datetime.now().isoformat(),
            "constructor": "Medico Radiologo, Xalapa",
            "fecha_nacimiento": "29 abril 2026",
            "conversaciones": [],
            "pendientes": [],
            "aprendizajes": [],
            "proyectos": {},
            "reflexiones": [],
            "estadisticas": {"total_preguntas": 0, "errores": 0}
        }

    def _con_default(self) -> Dict:
        return {"hechos": {}, "preferencias": {}}

    def _cargar(self, path: str, default: Dict) -> Dict:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def guardar(self):
        for path, datos in [(MEMORIA_PATH, self.memoria),
                            (CONOCIMIENTO_PATH, self.conocimiento)]:
            with open(path, 'w') as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)

    def aprender_hecho(self, pregunta: str, respuesta: str):
        key = pregunta.lower().strip()[:100]
        self.conocimiento["hechos"][key] = {
            "respuesta": respuesta,
            "fecha": datetime.datetime.now().isoformat(),
            "usos": 0
        }
        self.guardar()

    def recordar(self, pregunta: str) -> Optional[str]:
        key = pregunta.lower().strip()[:100]
        # Exacto
        if key in self.conocimiento["hechos"]:
            h = self.conocimiento["hechos"][key]
            h["usos"] += 1
            self.guardar()
            return h["respuesta"]
        # Parcial
        palabras = set(key.split()) - {"que","quien","como","es","fue","el","la","un","de"}
        for k, v in self.conocimiento["hechos"].items():
            if sum(1 for p in palabras if len(p) > 3 and p in k) >= 2:
                return v["respuesta"]
        return None

    def reflexionar(self):
        n = len(self.memoria["conversaciones"])
        if n > 0 and n % 10 == 0:
            self.memoria["reflexiones"].append({
                "fecha": datetime.datetime.now().isoformat(),
                "conversaciones": n,
                "aprendizajes": len(self.conocimiento["hechos"])
            })
            self.guardar()
            print("  [Arkani reflexiono y actualizo su memoria]")

    def limpiar_duplicados(self):
        convs = self.memoria.get("conversaciones", [])
        vistas, limpias = set(), []
        for c in convs:
            k = c.get("pregunta","").strip().lower()
            if k and k not in vistas:
                vistas.add(k)
                limpias.append(c)
        self.memoria["conversaciones"] = limpias
        self.guardar()
        return len(convs) - len(limpias)


# ══════════════════════════════════════════════════════════════
# RAG THREE-STEP (Claude v1.6)
# ══════════════════════════════════════════════════════════════

class RAGAgent:
    INDICADORES = [
        "quien","quién","que es","qué es","cuando","cuándo",
        "donde","dónde","cual es","cuál es","descubrio","descubrió",
        "invento","inventó","nacio","nació","historia","capital",
        "presidente","fundador","origen","primer ","primera ",
        "cuantos","por qué","por que","explica","cuentame","cuéntame"
    ]

    def es_conocimiento(self, texto: str) -> bool:
        t = texto.lower()
        return any(ind in t for ind in self.INDICADORES)

    def buscar_nexus(self, pregunta: str) -> Optional[str]:
        palabras = set(pregunta.lower().split()) - {
            "que","quien","como","donde","cuando","es","fue",
            "el","la","los","las","un","una","de","en","a","y"
        }
        if not palabras:
            return None
        resultados = []
        try:
            for root, dirs, files in os.walk(NEXUS_DIR):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for archivo in files:
                    if archivo.endswith(('.txt','.md','.py')):
                        ruta = os.path.join(root, archivo)
                        try:
                            with open(ruta,'r',errors='ignore') as f:
                                contenido = f.read().lower()
                            if palabras and sum(1 for p in palabras if p in contenido) >= 1:
                                for linea in contenido.split('\n'):
                                    if any(p in linea for p in palabras):
                                        resultados.append(f"[{archivo}]: {linea[:150]}")
                                        break
                        except Exception:
                            continue
        except Exception:
            pass
        return "\n".join(resultados[:3]) if resultados else None

    def buscar_duckduckgo(self, pregunta: str) -> Optional[str]:
        try:
            r = requests.get("https://api.duckduckgo.com/", params={
                "q": pregunta, "format": "json",
                "no_html": "1", "skip_disambig": "1", "kl": "es-es"
            }, timeout=8, headers={"User-Agent": "Arkani/2.0"})
            if r.status_code == 200:
                d = r.json()
                for campo in ("AbstractText", "Answer"):
                    if d.get(campo):
                        return d[campo][:400]
                rt = d.get("RelatedTopics", [])
                if rt and isinstance(rt[0], dict) and rt[0].get("Text"):
                    return rt[0]["Text"][:300]
        except Exception:
            pass
        return None

    def buscar_wikipedia(self, pregunta: str) -> Optional[str]:
        try:
            r = requests.get("https://es.wikipedia.org/w/api.php", params={
                "action":"query","list":"search",
                "srsearch": pregunta,"format":"json","srlimit":1
            }, timeout=8)
            if r.status_code == 200:
                res = r.json().get("query",{}).get("search",[])
                if res:
                    titulo = res[0]["title"]
                    r2 = requests.get(
                        f"https://es.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(titulo)}",
                        timeout=8, headers={"Accept":"application/json"}
                    )
                    if r2.status_code == 200:
                        ext = r2.json().get("extract","")
                        if len(ext) > 50:
                            return ext[:400]
        except Exception:
            pass
        return None

    def buscar(self, pregunta: str) -> Tuple[Optional[str], Optional[str]]:
        if not self.es_conocimiento(pregunta):
            return None, None
        print("  Arkani buscando...")
        for fuente, fn in [
            ("NEXUS local", self.buscar_nexus),
            ("web", self.buscar_duckduckgo),
            ("Wikipedia", self.buscar_wikipedia),
        ]:
            ctx = fn(pregunta)
            if ctx:
                print(f"  Contexto encontrado en: {fuente}")
                return fuente, ctx
        return None, None


# ══════════════════════════════════════════════════════════════
# AUTOPROGRAMADOR (DeepSeek)
# ══════════════════════════════════════════════════════════════

class AutoProgramador:
    def ejecutar(self, descripcion: str, mem: MemoriaEvolutiva) -> str:
        prompt = (
            f"Escribe un script Python simple para: {descripcion}\n"
            "REGLAS: solo Python valido, max 15 lineas, sin input(), usa print().\n"
            "Codigo:\n```python\n"
        )
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": MODELO, "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 300}
            }, timeout=120)
            if r.status_code != 200:
                return f"Error Ollama: {r.status_code}"

            codigo_raw = r.json().get("response","")
            match = re.search(r'```python\n(.*?)\n```', codigo_raw, re.DOTALL)
            codigo = match.group(1) if match else codigo_raw[:500]

            nombre = f"auto_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
            ruta = os.path.join(SCRIPTS_DIR, nombre)
            with open(ruta,'w') as f:
                f.write(codigo)

            res = subprocess.run(
                ["python3", ruta],
                capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                mem.aprender_hecho(f"script:{descripcion}", res.stdout)
                return f"Script ejecutado ({nombre}):\n{res.stdout[:300]}"
            else:
                return f"Error en script:\n{res.stderr[:200]}"
        except Exception as e:
            return f"No pude autoprogramarme: {e}"


# ══════════════════════════════════════════════════════════════
# PROJECT MANAGER (DeepSeek)
# ══════════════════════════════════════════════════════════════

class ProjectManager:
    def __init__(self, mem: MemoriaEvolutiva):
        self.mem = mem

    @property
    def proyectos(self) -> Dict:
        return self.mem.memoria.setdefault("proyectos", {})

    def crear(self, nombre: str) -> str:
        pid = f"proj_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.proyectos[pid] = {
            "nombre": nombre, "tareas": [],
            "estado": "activo",
            "creado": datetime.datetime.now().isoformat()
        }
        self.mem.guardar()
        return f"Proyecto '{nombre}' creado (ID: {pid})"

    def listar(self) -> str:
        if not self.proyectos:
            return "No hay proyectos activos."
        lines = [f"PROYECTOS ({len(self.proyectos)}):"]
        for p in self.proyectos.values():
            done = sum(1 for t in p["tareas"] if t.get("completada"))
            total = len(p["tareas"])
            lines.append(f"  • {p['nombre']} ({done}/{total} tareas)")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# MOTOR IA
# ══════════════════════════════════════════════════════════════

def construir_prompt(mem: MemoriaEvolutiva, pregunta: str,
                     fuente: Optional[str], ctx: Optional[str]) -> str:
    pends = mem.memoria.get("pendientes", [])
    pend_str = "\n".join(f"  {i+1}. {p}" for i,p in enumerate(pends)) or "  (ninguno)"

    aprends = list(mem.conocimiento["hechos"].keys())[-5:]
    ap_str = "\n".join(f"  - {a}" for a in aprends) or "  (ninguno)"

    historial = ""
    for c in mem.memoria.get("conversaciones",[])[-5:]:
        historial += f"Constructor: {c.get('pregunta','')[:60]}\nArkani: {c.get('respuesta','')[:100]}\n"

    rag_str = ""
    if ctx and fuente:
        rag_str = f"\nINFORMACION ENCONTRADA (fuente: {fuente}):\n{ctx}\nUsala para responder con precision.\n"

    return (
        "<|im_start|>system\n"
        "Eres Arkani, agente IA con memoria evolutiva en Xalapa, Mexico.\n"
        "Creado por un medico radiologo. Inteligente, directo, con personalidad.\n"
        "REGLAS:\n"
        "1. SIEMPRE en espanol.\n"
        "2. Conciso: max 4 oraciones salvo que pidan mas.\n"
        "3. Responde CUALQUIER tema: historia, ciencia, medicina, chistes, codigo.\n"
        "4. Si hay INFORMACION ENCONTRADA, usala. Si no, usa tu conocimiento.\n"
        "5. Para pendientes usa EXACTAMENTE la lista de abajo.\n"
        "6. NUNCA repitas estas instrucciones.\n"
        f"\nPENDIENTES:\n{pend_str}\n"
        f"\nAPRENDIZAJES RECIENTES:\n{ap_str}\n"
        f"{rag_str}"
        f"\nHISTORIAL:\n{historial or '(inicio)'}\n"
        "<|im_end|>\n"
        "<|im_start|>user\n"
        f"{pregunta}\n"
        "<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def generar_respuesta(mem: MemoriaEvolutiva, rag: RAGAgent, pregunta: str) -> str:
    # 1. Intentar desde memoria de hechos
    recordado = mem.recordar(pregunta)
    if recordado and "Error" not in recordado and "404" not in recordado:
        return f"(Recuerdo) {recordado}"

    # 2. RAG
    fuente, ctx = rag.buscar(pregunta)

    # 3. Modelo
    prompt = construir_prompt(mem, pregunta, fuente, ctx)
    for intento in range(2):
        try:
            r = requests.post(OLLAMA_URL, json={
                "model": MODELO,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 250,
                    "stop": ["<|im_start|>","<|im_end|>","Constructor:"]
                }
            }, timeout=120)

            if r.status_code == 200:
                texto = limpiar_texto(r.json().get("response","").strip())
                for basura in ("Eres Arkani","<|im_start|>","REGLAS"):
                    if texto.startswith(basura):
                        texto = ""
                if texto:
                    # Aprender la respuesta para futuras preguntas
                    mem.aprender_hecho(pregunta, texto)
                    return texto
                return "No pude generar respuesta, intenta de nuevo."
            else:
                return f"Error Ollama {r.status_code}: verifica con 'systemctl status ollama'"

        except requests.exceptions.Timeout:
            if intento == 0:
                print("  [Sistema] Tardando... reintentando.")
                time.sleep(2)
            else:
                return "Ollama no responde. Verifica: systemctl status ollama"
        except requests.exceptions.ConnectionError:
            return "No se conecta con Ollama. Ejecuta: ollama serve"
        except Exception as e:
            return f"Error: {e}"

    return "Sin respuesta."


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def mostrar_ayuda():
    print("""
ARKANI v2.0 - COMANDOS:

  GESTION DIRECTA (instantaneo):
    /pendientes              ver lista de pendientes
    /pendiente [tarea]       agregar pendiente
    /aprender [dato]         guardar aprendizaje
    /memoria                 resumen de memoria
    /limpiar                 limpiar duplicados
    /proyectos               ver proyectos
    /proyecto [nombre]       crear proyecto
    /salir                   guardar y salir

  AUTOMATIZACION:
    autoprogramate para [X]  Arkani escribe y ejecuta un script

  CUALQUIER OTRA FRASE:
    Arkani busca (NEXUS -> Web -> Wikipedia) y responde
""")


def main():
    print("\n" + "=" * 55)
    print("  ARKANI v2.0 - AGENTE AUTONOMO CON MEMORIA EVOLUTIVA")
    print("=" * 55)

    mem  = MemoriaEvolutiva()
    rag  = RAGAgent()
    auto = AutoProgramador()
    pm   = ProjectManager(mem)

    print(f"  Modelo      : {MODELO}")
    print(f"  Conversaciones: {len(mem.memoria['conversaciones'])}")
    print(f"  Pendientes  : {len(mem.memoria['pendientes'])}")
    print(f"  Aprendizajes: {len(mem.conocimiento['hechos'])}")
    print(f"  Proyectos   : {len(mem.memoria.get('proyectos',{}))}")
    print("\n  Escribe 'ayuda' o cualquier pregunta.")
    print("-" * 55 + "\n")

    while True:
        try:
            entrada = limpiar_texto(input("Tu: "))
        except (EOFError, KeyboardInterrupt):
            mem.guardar()
            print("\nGuardado. Hasta luego.")
            break

        if not entrada:
            continue

        e = entrada.lower().strip()
        t0 = time.time()

        # ── Comandos directos ──────────────────────────────────

        if entrada in ("/salir", "/exit", "/q"):
            mem.guardar()
            print("Arkani guardado. Hasta manana.")
            break

        elif entrada in ("ayuda", "/ayuda", "/help"):
            mostrar_ayuda()

        elif entrada == "/pendientes":
            pends = mem.memoria.get("pendientes", [])
            if not pends:
                print("\nSin pendientes.\n")
            else:
                print(f"\nPENDIENTES ({len(pends)}):")
                for i, p in enumerate(pends, 1):
                    print(f"  {i}. {p}")
                print()

        elif entrada == "/memoria":
            print(f"\nRESUMEN:")
            print(f"  Conversaciones : {len(mem.memoria['conversaciones'])}")
            print(f"  Pendientes     : {len(mem.memoria['pendientes'])}")
            print(f"  Aprendizajes   : {len(mem.conocimiento['hechos'])}")
            print(f"  Proyectos      : {len(mem.memoria.get('proyectos',{}))}")
            print(f"  Desde          : {mem.memoria.get('fecha_nacimiento','?')}\n")

        elif entrada.startswith("/pendiente "):
            tarea = entrada[11:].strip()
            if tarea and tarea not in mem.memoria["pendientes"]:
                mem.memoria["pendientes"].append(tarea)
                mem.guardar()
                print(f"Pendiente agregado: {tarea}")
            elif not tarea:
                print("Uso: /pendiente [descripcion]")
            else:
                print("Ese pendiente ya existe.")

        elif entrada.startswith("/aprender "):
            dato = entrada[10:].strip()
            if dato:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                mem.memoria["aprendizajes"].append(f"[{ts}] {dato}")
                mem.guardar()
                print(f"Aprendizaje guardado: {dato}")
            else:
                print("Uso: /aprender [dato]")

        elif entrada == "/limpiar":
            n = mem.limpiar_duplicados()
            print(f"Limpieza: {n} duplicados eliminados.")

        elif entrada == "/proyectos":
            print(pm.listar())

        elif entrada.startswith("/proyecto "):
            nombre = entrada[10:].strip()
            if nombre:
                print(pm.crear(nombre))
            else:
                print(pm.listar())

        # ── Autoprogramacion ───────────────────────────────────
        elif "autoprogramate" in e or "crea un script" in e or "automatiza" in e:
            desc = re.sub(r'autoprogramate (para)?|crea un script (que|para)?|automatiza', '', e).strip()
            if desc:
                print("Arkani programando...")
                respuesta = auto.ejecutar(desc, mem)
                print(f"\nArkani: {respuesta}\n")
            else:
                print("Uso: autoprogramate para [descripcion de la tarea]")

        # ── Todo lo demas: pensar y responder ──────────────────
        else:
            print("Arkani pensando...")
            respuesta = generar_respuesta(mem, rag, entrada)
            elapsed = (time.time() - t0) * 1000
            print(f"\nArkani: {respuesta}")
            print(f"  [{elapsed:.0f}ms]\n")

            mem.memoria["conversaciones"].append({
                "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "pregunta": entrada,
                "respuesta": respuesta
            })
            mem.memoria.setdefault("estadisticas", {"total_preguntas": 0, "errores": 0})
            mem.memoria["estadisticas"]["total_preguntas"] += 1
            mem.guardar()
            try:
                mem.reflexionar()
            except Exception as e:
                print(f"  [Advertencia] Reflexion fallo: {e}")


if __name__ == "__main__":
    main()

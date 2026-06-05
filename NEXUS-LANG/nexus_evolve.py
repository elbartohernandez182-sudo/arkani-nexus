"""
NEXUS EVOLVE v2.0
Auto-programacion real con aprendizaje de errores
Constructor: Medico Radiologo, Xalapa
"""

import os
import sys
import ast
import json
import subprocess
import traceback
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR    = os.path.expanduser("~/NEXUS/NEXUS-LANG")
OLLAMA_URL  = "http://127.0.0.1:11434/api/generate"
MODELO      = "arkani:latest"
LOG_PATH    = os.path.expanduser("~/NEXUS/logs/evolve.log")
MEM_PATH    = os.path.expanduser("~/NEXUS/NEXUS-LANG/evolve_memoria.json")


# ── MEMORIA DE ERRORES ───────────────────────────────────────

class EvolveMemoria:
    """Aprende de errores pasados para no repetir soluciones."""

    def __init__(self):
        self.path = MEM_PATH
        self.datos = self._cargar()

    def _cargar(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except:
            return {"errores": [], "soluciones": {}, "stats": {"resueltos": 0, "fallidos": 0}}

    def _guardar(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.datos, f, indent=2, ensure_ascii=False)

    def recordar_solucion(self, tipo_error: str) -> str | None:
        """Busca si ya resolvimos este tipo de error antes."""
        return self.datos["soluciones"].get(tipo_error)

    def guardar_solucion(self, tipo_error: str, solucion: str, exitosa: bool):
        """Guarda la solución y si funcionó."""
        if exitosa:
            self.datos["soluciones"][tipo_error] = solucion
            self.datos["stats"]["resueltos"] += 1
        else:
            self.datos["stats"]["fallidos"] += 1
        self.datos["errores"].append({
            "tipo": tipo_error,
            "solucion": solucion,
            "exitosa": exitosa,
            "fecha": datetime.now().isoformat()
        })
        # Máximo 100 errores en memoria
        if len(self.datos["errores"]) > 100:
            self.datos["errores"] = self.datos["errores"][-100:]
        self._guardar()

    def stats(self) -> str:
        s = self.datos["stats"]
        total = s["resueltos"] + s["fallidos"]
        pct = (s["resueltos"] / total * 100) if total > 0 else 0
        return f"Resueltos: {s['resueltos']}/{total} ({pct:.0f}%)"


# ── DETECTOR DE ERRORES ──────────────────────────────────────

class DetectorErrores:
    """Detecta y clasifica errores de Python."""

    TIPOS = {
        "FileNotFoundError":  "archivo_no_encontrado",
        "ImportError":        "importacion_fallida",
        "ModuleNotFoundError":"modulo_no_encontrado",
        "SyntaxError":        "sintaxis",
        "IndentationError":   "indentacion",
        "AttributeError":     "atributo_no_existe",
        "KeyError":           "clave_no_existe",
        "TypeError":          "tipo_incorrecto",
        "NameError":          "nombre_no_definido",
        "ConnectionError":    "conexion_fallida",
        "TimeoutError":       "timeout",
        "PermissionError":    "permisos",
        "JSONDecodeError":    "json_invalido",
    }

    @staticmethod
    def clasificar(mensaje: str) -> str:
        for exc, tipo in DetectorErrores.TIPOS.items():
            if exc in mensaje:
                return tipo
        return "error_desconocido"

    @staticmethod
    def extraer_archivo(mensaje: str) -> str | None:
        """Intenta extraer el archivo involucrado en el error."""
        import re
        match = re.search(r'File "([^"]+)"', mensaje)
        if match:
            return match.group(1)
        match = re.search(r"'([^']+\.py)'", mensaje)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def extraer_linea(mensaje: str) -> int | None:
        """Extrae número de línea del error."""
        import re
        match = re.search(r'line (\d+)', mensaje)
        return int(match.group(1)) if match else None


# ── REPARADOR AUTOMÁTICO ─────────────────────────────────────

class ReparadorAutomatico:
    """Repara errores conocidos sin necesitar Ollama."""

    @staticmethod
    def reparar(tipo_error: str, mensaje: str) -> tuple[bool, str]:
        metodo = getattr(ReparadorAutomatico, f"_fix_{tipo_error}", None)
        if metodo:
            return metodo(mensaje)
        return False, "Sin reparación automática disponible"

    @staticmethod
    def _fix_archivo_no_encontrado(mensaje: str) -> tuple[bool, str]:
        import re
        match = re.search(r"'([^']+)'", mensaje)
        if match:
            ruta = match.group(1)
            directorio = os.path.dirname(ruta)
            if directorio:
                os.makedirs(directorio, exist_ok=True)
                return True, f"Directorio creado: {directorio}"
        return False, "No se pudo extraer la ruta"

    @staticmethod
    def _fix_modulo_no_encontrado(mensaje: str) -> tuple[bool, str]:
        import re
        match = re.search(r"No module named '([^']+)'", mensaje)
        if match:
            modulo = match.group(1).split('.')[0]
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", modulo, "-q"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    return True, f"Modulo instalado: {modulo}"
                return False, f"Error instalando {modulo}: {result.stderr}"
            except Exception as e:
                return False, str(e)
        return False, "No se identifico el modulo"

    @staticmethod
    def _fix_permisos(mensaje: str) -> tuple[bool, str]:
        import re
        match = re.search(r"'([^']+)'", mensaje)
        if match:
            ruta = match.group(1)
            try:
                os.chmod(ruta, 0o755)
                return True, f"Permisos corregidos: {ruta}"
            except:
                pass
        return False, "No se pudieron corregir permisos"


# ── GENERADOR DE FIXES CON OLLAMA ────────────────────────────

class GeneradorFixes:
    """Usa Ollama para generar fixes para errores complejos."""

    @staticmethod
    def generar_fix(error: str, codigo: str = "") -> str | None:
        prompt = f"""Eres un experto en Python. Analiza este error y genera SOLO el codigo Python corregido, sin explicaciones:

ERROR:
{error}

{"CODIGO CON ERROR:" if codigo else ""}
{codigo}

Responde SOLO con el codigo Python corregido, listo para ejecutar."""

        try:
            r = requests.post(OLLAMA_URL, json={
                "model": MODELO,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 500}
            }, timeout=120)
            if r.status_code == 200:
                respuesta = r.json().get("response", "").strip()
                # Limpiar markdown si viene con ```python
                if "```python" in respuesta:
                    respuesta = respuesta.split("```python")[1].split("```")[0].strip()
                elif "```" in respuesta:
                    respuesta = respuesta.split("```")[1].split("```")[0].strip()
                return respuesta
        except Exception as e:
            print(f"❌ Ollama no disponible: {e}")
        return None


# ── CLASE PRINCIPAL ──────────────────────────────────────────

class NexusEvolve:
    """
    Auto-programacion v2.0 — detecta, aprende y repara errores reales.
    """

    def __init__(self):
        self.memoria    = EvolveMemoria()
        self.detector   = DetectorErrores()
        self.reparador  = ReparadorAutomatico()
        self.generador  = GeneradorFixes()
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        print(f"🧬 [NEXUS-EVOLVE v2.0] Iniciado — {self.memoria.stats()}")

    def _log(self, mensaje: str):
        """Registra actividad en log."""
        linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}"
        print(linea)
        try:
            with open(LOG_PATH, 'a') as f:
                f.write(linea + "\n")
        except:
            pass

    def analyze_and_fix(self, error_message: str, codigo: str = "") -> bool:
        """
        Analiza un error y lo intenta reparar.
        Retorna True si lo resolvió.
        """
        self._log(f"🔍 Analizando: {error_message[:100]}")

        tipo = self.detector.clasificar(error_message)
        archivo = self.detector.extraer_archivo(error_message)
        linea = self.detector.extraer_linea(error_message)

        self._log(f"📋 Tipo: {tipo} | Archivo: {archivo} | Línea: {linea}")

        # 1. ¿Ya resolvimos esto antes?
        solucion_previa = self.memoria.recordar_solucion(tipo)
        if solucion_previa:
            self._log(f"💾 Solución conocida encontrada para {tipo}")

        # 2. Intentar reparación automática primero (sin Ollama)
        exito, resultado = self.reparador.reparar(tipo, error_message)
        if exito:
            self._log(f"✅ Auto-reparado: {resultado}")
            self.memoria.guardar_solucion(tipo, resultado, True)
            return True

        # 3. Intentar con Ollama para errores complejos
        self._log(f"🤖 Consultando Ollama para fix...")
        fix = self.generador.generar_fix(error_message, codigo)
        if fix:
            self._log(f"💡 Fix generado por Ollama ({len(fix)} chars)")
            # Verificar que el fix es Python válido
            try:
                ast.parse(fix)
                self._log(f"✅ Fix válido — guardando en autogen")
                self._guardar_fix(tipo, fix)
                self.memoria.guardar_solucion(tipo, fix[:200], True)
                return True
            except SyntaxError as e:
                self._log(f"❌ Fix inválido (SyntaxError): {e}")
                self.memoria.guardar_solucion(tipo, fix[:200], False)

        self._log(f"⚠️ No se pudo reparar automáticamente: {tipo}")
        return False

    def _guardar_fix(self, tipo: str, codigo: str):
        """Guarda el fix como módulo en autogen."""
        autogen_dir = os.path.join(BASE_DIR, "autogen")
        os.makedirs(autogen_dir, exist_ok=True)
        nombre = f"fn_fix_{tipo}_{datetime.now().strftime('%m%d_%H%M')}.py"
        ruta = os.path.join(autogen_dir, nombre)
        with open(ruta, 'w') as f:
            f.write(f"# FIX AUTO-GENERADO por NexusEvolve v2.0\n")
            f.write(f"# Tipo error: {tipo}\n")
            f.write(f"# Fecha: {datetime.now().isoformat()}\n\n")
            f.write(codigo)
        self._log(f"💾 Fix guardado: {nombre}")

    def escanear_autogen(self) -> dict:
        """Escanea autogen/ buscando errores de sintaxis."""
        autogen_dir = os.path.join(BASE_DIR, "autogen")
        resultados = {"ok": [], "errores": []}
        try:
            for archivo in sorted(os.listdir(autogen_dir)):
                if not archivo.endswith('.py'):
                    continue
                ruta = os.path.join(autogen_dir, archivo)
                try:
                    with open(ruta) as f:
                        codigo = f.read()
                    ast.parse(codigo)
                    resultados["ok"].append(archivo)
                except SyntaxError as e:
                    resultados["errores"].append({
                        "archivo": archivo,
                        "error": str(e),
                        "linea": e.lineno
                    })
                    self._log(f"⚠️ Error en {archivo}: {e}")
        except Exception as e:
            self._log(f"❌ Error escaneando autogen: {e}")
        return resultados

    def ciclo_autocuracion(self) -> str:
        """
        Ciclo completo: escanea, detecta errores y los repara.
        Llamar periódicamente desde el bridge.
        """
        self._log("🔄 Iniciando ciclo de auto-curación...")
        resultados = self.escanear_autogen()
        reparados = 0
        for err in resultados["errores"]:
            mensaje = f"SyntaxError en {err['archivo']} linea {err['linea']}: {err['error']}"
            ruta = os.path.join(BASE_DIR, "autogen", err['archivo'])
            try:
                with open(ruta) as f:
                    codigo = f.read()
            except:
                codigo = ""
            if self.analyze_and_fix(mensaje, codigo):
                reparados += 1
        resumen = (f"Ciclo completado: {len(resultados['ok'])} OK, "
                   f"{len(resultados['errores'])} errores, "
                   f"{reparados} reparados. {self.memoria.stats()}")
        self._log(resumen)
        return resumen

    def estado(self) -> dict:
        return {
            "version": "2.0",
            "memoria": self.memoria.stats(),
            "soluciones_conocidas": len(self.memoria.datos["soluciones"]),
            "errores_registrados": len(self.memoria.datos["errores"])
        }


# ── INTEGRACIÓN CON BRIDGE ───────────────────────────────────

def integrar_evolve(engine=None):
    """
    Retorna instancia de NexusEvolve lista para usar desde el bridge.
    Uso: evolve = integrar_evolve(engine); evolve.analyze_and_fix(error)
    """
    return NexusEvolve()


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🧬 NEXUS EVOLVE v2.0 — Auto-programacion")
    print("=" * 60)

    evolve = NexusEvolve()

    # Test 1: archivo no encontrado
    print("\n[TEST 1] FileNotFoundError")
    evolve.analyze_and_fix(
        "FileNotFoundError: [Errno 2] No such file or directory: '/home/arkani/NEXUS/test/archivo.json'"
    )

    # Test 2: modulo no encontrado
    print("\n[TEST 2] ModuleNotFoundError")
    evolve.analyze_and_fix(
        "ModuleNotFoundError: No module named 'requests'"
    )

    # Test 3: escanear autogen
    print("\n[TEST 3] Escanear autogen/")
    resultado = evolve.escanear_autogen()
    print(f"OK: {len(resultado['ok'])} | Errores: {len(resultado['errores'])}")

    # Test 4: ciclo completo
    print("\n[TEST 4] Ciclo auto-curación")
    print(evolve.ciclo_autocuracion())

    print("\n" + "=" * 60)
    print(f"📊 Estado: {evolve.estado()}")


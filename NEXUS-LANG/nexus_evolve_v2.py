"""
nexus_evolve_v2.py — Motor de Evolución ARKANI NEXUS
Integrado al ciclo de chat: cada respuesta de Ollama pasa por el analizador fractal.

FLUJO:
  chat_input → Ollama → respuesta_raw → EvolveEngine.analyze() → respuesta_final
  Si hay error detectado → EvolveEngine.fix() → inyecta corrección automática

CAMBIOS v2:
  - Hook post-respuesta en /chat route de arkani_web.py
  - Análisis fractal de 13 tipos de error en código y lógica
  - JSON memory persistente en ~/NEXUS/evolve_memory.json
  - Contador EVOL en status bar ahora refleja evoluciones reales del chat
"""

import re
import json
import os
import time
import requests
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
NEXUS_DIR = Path.home() / "NEXUS"
EVOLVE_MEMORY_PATH = NEXUS_DIR / "evolve_memory.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
EVOLVE_MODEL = "arkani:latest"

# 13 tipos de error fractal
ERROR_PATTERNS = {
    # Errores lógicos
    "logic_error": [
        r"\bsiempre\s+(?:es|será|tiene)\b",
        r"\bnunca\s+(?:es|será|puede)\b",
        r"contradicción|contradiction",
    ],
    "type_error": [
        r"TypeError",
        r"expected\s+\w+,\s+got\s+\w+",
        r"no se puede convertir",
    ],
    "null_reference": [
        r"NoneType|NullPointer|null reference",
        r"'NoneType' object has no attribute",
        r"cannot access.*None",
    ],
    "index_out_of_bounds": [
        r"IndexError|list index out of range",
        r"index\s+\d+\s+is out of bounds",
        r"subscript out of range",
    ],
    # Errores de integración
    "import_error": [
        r"ImportError|ModuleNotFoundError",
        r"No module named",
        r"cannot import name",
    ],
    "dependency_missing": [
        r"pip install|not installed|missing dependency",
        r"command not found",
        r"No such file or directory.*\.py",
    ],
    "version_conflict": [
        r"version\s+\d+\.\d+.*required",
        r"incompatible.*version",
        r"requires.*>=.*found",
    ],
    # Errores de ejecución
    "timeout": [
        r"timeout|Timeout|timed out",
        r"Request took too long",
        r"ReadTimeout|ConnectTimeout",
    ],
    "memory_overflow": [
        r"MemoryError|OutOfMemory",
        r"cannot allocate memory",
        r"killed.*memory",
    ],
    "infinite_loop": [
        r"RecursionError|maximum recursion",
        r"infinite loop detected",
        r"stack overflow",
    ],
    # Errores fractales
    "spawn_collision": [
        r"duplicate.*spawn|spawn.*collision",
        r"neuron.*already exists",
        r"hipocampo.*overflow",
    ],
    "fold_divergence": [
        r"fold.*diverge|divergence.*fold",
        r"reducción.*inconsistente",
        r"FOLD.*error",
    ],
    "link_cycle": [
        r"circular.*reference|cycle.*detected",
        r"LINK.*ciclo|ciclo.*LINK",
        r"recursive.*link",
    ],
}

# Prompts de corrección por tipo
FIX_PROMPTS = {
    "logic_error":       "Detecté una afirmación absoluta que puede ser incorrecta. Reformúlala con matices apropiados.",
    "type_error":        "Hay un error de tipos. Revisa la conversión o el tipo esperado y corrige.",
    "null_reference":    "Se accede a un objeto nulo. Añade verificación de None antes del acceso.",
    "index_out_of_bounds": "El índice está fuera de rango. Verifica los límites de la lista antes de acceder.",
    "import_error":      "Falta un módulo. Sugiere el comando pip install correcto y una alternativa si existe.",
    "dependency_missing":"Dependencia ausente. Lista los pasos para instalarla en Ubuntu y Windows.",
    "version_conflict":  "Conflicto de versiones. Especifica la versión compatible y cómo fijarla en requirements.txt.",
    "timeout":           "Timeout detectado. Sugiere reducir el contexto, dividir la tarea, o aumentar el timeout.",
    "memory_overflow":   "Desbordamiento de memoria. Sugiere procesar en lotes o liberar recursos.",
    "infinite_loop":     "Bucle infinito detectado. Añade condición de salida o límite de iteraciones.",
    "spawn_collision":   "Colisión en SPAWN. Verifica IDs únicos de neuronas en el hipocampo.",
    "fold_divergence":   "Divergencia en FOLD. La reducción no converge — añade caso base o límite.",
    "link_cycle":        "Ciclo en LINK detectado. Implementa detección de ciclos antes de crear el enlace.",
}


# ─────────────────────────────────────────────
# MEMORIA PERSISTENTE
# ─────────────────────────────────────────────
def load_evolve_memory() -> dict:
    """Carga la memoria de evoluciones desde disco."""
    if EVOLVE_MEMORY_PATH.exists():
        try:
            with open(EVOLVE_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "total_evolutions": 0,
        "errors_by_type": {},
        "evolution_log": [],
        "last_updated": None,
    }


def save_evolve_memory(memory: dict):
    """Guarda la memoria de evoluciones a disco."""
    NEXUS_DIR.mkdir(parents=True, exist_ok=True)
    memory["last_updated"] = datetime.now().isoformat()
    with open(EVOLVE_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# MOTOR PRINCIPAL
# ─────────────────────────────────────────────
class EvolveEngine:
    """
    Motor de evolución fractal ARKANI.
    Se conecta al ciclo de chat como post-processor de respuestas Ollama.
    """

    def __init__(self):
        self.memory = load_evolve_memory()
        self._evol_count_this_session = 0

    # ──────────────────────────────────────────
    # ANÁLISIS DE ERRORES
    # ──────────────────────────────────────────
    def analyze(self, text: str) -> list[dict]:
        """
        Analiza el texto buscando los 13 tipos de error fractal.
        Retorna lista de errores detectados [{type, pattern, position}]
        """
        detected = []
        for error_type, patterns in ERROR_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    detected.append({
                        "type": error_type,
                        "matched": match.group(0),
                        "position": match.start(),
                    })
                    break  # un match por tipo es suficiente
        return detected

    # ──────────────────────────────────────────
    # GENERACIÓN DE CORRECCIÓN
    # ──────────────────────────────────────────
    def fix(self, original_text: str, error_type: str, context: str = "") -> str:
        """
        Genera una corrección usando Ollama con prompt especializado.
        Retorna texto de corrección o string vacío si falla.
        """
        fix_instruction = FIX_PROMPTS.get(error_type, "Corrige el error detectado.")

        prompt = f"""EVOLVE({error_type}):
Texto original con error:
---
{original_text[:500]}
---
Contexto adicional: {context or 'ninguno'}

Instrucción: {fix_instruction}
Responde SOLO con el texto corregido, sin explicaciones adicionales. Máximo 200 palabras."""

        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": EVOLVE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 300,
                    }
                },
                timeout=20
            )
            if response.ok:
                data = response.json()
                return data.get("response", "").strip()
        except (requests.RequestException, json.JSONDecodeError):
            pass
        return ""

    # ──────────────────────────────────────────
    # HOOK PRINCIPAL — CONECTADO AL CHAT
    # ──────────────────────────────────────────
    def process_chat_response(
        self,
        user_message: str,
        arkani_response: str,
        auto_fix: bool = False,
    ) -> dict:
        """
        Post-procesador de respuestas del ciclo de chat.

        PARÁMETROS:
          user_message    — mensaje original del usuario
          arkani_response — respuesta cruda de Ollama
          auto_fix        — si True, genera corrección automática vía Ollama

        RETORNA:
          {
            "response": str,        # respuesta final (corregida o original)
            "errors_found": list,   # errores detectados
            "evolved": bool,        # True si se aplicó corrección
            "evol_count": int,      # total evoluciones esta sesión
            "evolution_note": str,  # nota de corrección (si evolved=True)
          }
        """
        errors = self.analyze(arkani_response)
        result = {
            "response": arkani_response,
            "errors_found": errors,
            "evolved": False,
            "evol_count": self._evol_count_this_session,
            "evolution_note": "",
        }

        if not errors:
            return result

        # Registrar en memoria
        primary_error = errors[0]["type"]
        self.memory["total_evolutions"] += 1
        self.memory["errors_by_type"][primary_error] = (
            self.memory["errors_by_type"].get(primary_error, 0) + 1
        )
        self.memory["evolution_log"].append({
            "timestamp": datetime.now().isoformat(),
            "error_type": primary_error,
            "user_message_preview": user_message[:80],
            "auto_fixed": auto_fix,
        })
        # Mantener solo los últimos 100 registros
        if len(self.memory["evolution_log"]) > 100:
            self.memory["evolution_log"] = self.memory["evolution_log"][-100:]

        self._evol_count_this_session += 1
        result["evol_count"] = self._evol_count_this_session

        if auto_fix:
            fixed_text = self.fix(
                original_text=arkani_response,
                error_type=primary_error,
                context=user_message[:200],
            )
            if fixed_text:
                result["response"] = fixed_text
                result["evolved"] = True
                result["evolution_note"] = (
                    f"[EVOLVE:{primary_error}] Corrección automática aplicada."
                )

        save_evolve_memory(self.memory)
        return result

    # ──────────────────────────────────────────
    # ESTADÍSTICAS
    # ──────────────────────────────────────────
    def get_stats(self) -> dict:
        """Retorna estadísticas actuales del motor de evolución."""
        return {
            "total_evolutions": self.memory["total_evolutions"],
            "session_evolutions": self._evol_count_this_session,
            "errors_by_type": self.memory["errors_by_type"],
            "last_updated": self.memory.get("last_updated"),
            "top_error": max(
                self.memory["errors_by_type"],
                key=self.memory["errors_by_type"].get,
                default="none"
            ),
        }


# ─────────────────────────────────────────────
# INSTANCIA GLOBAL (importada por arkani_web.py)
# ─────────────────────────────────────────────
evolve_engine = EvolveEngine()


# ─────────────────────────────────────────────
# PATCH PARA arkani_web.py
# ─────────────────────────────────────────────
"""
INSTRUCCIONES DE INTEGRACIÓN EN arkani_web.py:
════════════════════════════════════════════════

1. Al inicio del archivo, añadir:

    from nexus_evolve_v2 import evolve_engine

2. En la función que maneja /chat (donde obtienes la respuesta de Ollama),
   reemplazar el return directo por este bloque:

    # ── ANTES (original) ──────────────────────
    return jsonify({"response": ollama_response})

    # ── DESPUÉS (con evolve) ──────────────────
    evolve_result = evolve_engine.process_chat_response(
        user_message=user_input,        # el mensaje que envió el usuario
        arkani_response=ollama_response, # lo que respondió Ollama
        auto_fix=False,                  # True = corrección automática (más lento)
    )

    response_data = {
        "response": evolve_result["response"],
        "evolved": evolve_result["evolved"],
        "evol_count": evolve_result["evol_count"],
        "evolution_note": evolve_result["evolution_note"],
        "errors_found": [e["type"] for e in evolve_result["errors_found"]],
    }
    return jsonify(response_data)

3. Para el endpoint de status (que alimenta la barra inferior), añadir:

    @app.route('/evolve_stats')
    def evolve_stats():
        return jsonify(evolve_engine.get_stats())

4. En el frontend (index.html), actualizar el contador EVOL:

    // Dentro de la función que procesa la respuesta del chat:
    if (data.evol_count !== undefined) {
        document.getElementById('evol-count').textContent = data.evol_count;
    }
    if (data.evolution_note) {
        // Mostrar nota de evolución en el chat como mensaje del sistema
        appendSystemMessage(data.evolution_note);
    }

════════════════════════════════════════════════
"""


# ─────────────────────────────────────────────
# TEST RÁPIDO (ejecutar directamente para verificar)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=== TEST nexus_evolve_v2.py ===\n")

    engine = EvolveEngine()

    # Test 1: texto limpio
    clean = "Hola, soy ARKANI. ¿En qué puedo ayudarte hoy?"
    result = engine.process_chat_response("hola", clean)
    print(f"[TEST 1 - Texto limpio]")
    print(f"  Errores: {result['errors_found']}")
    print(f"  Evolucionado: {result['evolved']}\n")

    # Test 2: texto con error
    error_text = "ModuleNotFoundError: No module named 'flask'"
    result = engine.process_chat_response("importa flask", error_text)
    print(f"[TEST 2 - ImportError]")
    print(f"  Errores: {[e['type'] for e in result['errors_found']]}")
    print(f"  Evolucionado: {result['evolved']}")
    print(f"  Contador EVOL: {result['evol_count']}\n")

    # Test 3: error lógico
    logic_text = "Esto siempre es correcto y nunca falla en ningún caso."
    result = engine.process_chat_response("es seguro?", logic_text)
    print(f"[TEST 3 - Logic error]")
    print(f"  Errores: {[e['type'] for e in result['errors_found']]}")
    print(f"  Contador EVOL: {result['evol_count']}\n")

    # Stats finales
    print(f"[STATS]")
    stats = engine.get_stats()
    print(f"  Total evoluciones: {stats['total_evolutions']}")
    print(f"  Por tipo: {stats['errors_by_type']}")
    print(f"\n=== TESTS COMPLETADOS ===")

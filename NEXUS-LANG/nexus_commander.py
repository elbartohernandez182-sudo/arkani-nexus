"""
nexus_commander.py — Interceptor de Comandos del Sistema ARKANI NEXUS
======================================================================
Intercepta intenciones de acción ANTES de enviarlas a Ollama.
Resultado: "abre youtube" ejecuta en <50ms en vez de causar timeout.

FLUJO CON ESTE MÓDULO:
  user_input
    ↓
  Commander.match(input)  ← NUEVO (rápido, sin Ollama)
    ↓ si hay match
  Commander.execute()     ← acción directa del sistema
    ↓ si no hay match
  Ollama (solo texto/conversación)

INTEGRACIÓN EN arkani_web.py:
  from nexus_commander import commander
  # Al inicio del handler de /chat:
  cmd_result = commander.match_and_execute(user_input)
  if cmd_result["executed"]:
      return jsonify({"response": cmd_result["response"], "action": cmd_result["action"]})
  # ... resto del flujo normal con Ollama
"""

import re
import subprocess
import sys
import os
import json
import webbrowser
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────
# CONFIGURACIÓN DE PLATAFORMA
# ─────────────────────────────────────────────
IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"

# Comandos de apertura según plataforma
OPEN_CMD = "xdg-open" if IS_LINUX else "start"

# ─────────────────────────────────────────────
# BASE DE DATOS DE INTENCIONES
# ─────────────────────────────────────────────
# Estructura: (regex_patron, accion_id, parametro_extractor_o_None)
# Los patrones están en español mexicano natural

INTENT_PATTERNS = [

    # ── NAVEGADOR / URLS ──────────────────────────────────────────────
    (r"abre?\s+(?:el\s+)?youtube", "open_url", "https://youtube.com"),
    (r"(?:abre?|ve\s+a|entra\s+a)\s+(?:el\s+|la\s+)?google", "open_url", "https://google.com"),
    (r"abre?\s+(?:el\s+)?gmail", "open_url", "https://gmail.com"),
    (r"abre?\s+(?:el\s+)?github", "open_url", "https://github.com/elbartohernandez182-sudo/arkani-nexus"),
    (r"abre?\s+(?:el\s+)?whatsapp", "open_url", "https://web.whatsapp.com"),
    (r"abre?\s+(?:el\s+)?telegram", "open_url", "https://web.telegram.org"),
    (r"abre?\s+(?:el\s+)?spotify", "open_url", "https://open.spotify.com"),
    (r"abre?\s+(?:el\s+)?netflix", "open_url", "https://netflix.com"),
    (r"abre?\s+(?:el\s+)?chatgpt", "open_url", "https://chat.openai.com"),
    (r"abre?\s+claude", "open_url", "https://claude.ai"),
    # URL directa mencionada
    (r"abre?\s+(https?://\S+)", "open_url_dynamic", None),
    (r"ve\s+a\s+(https?://\S+)", "open_url_dynamic", None),
    # Búsqueda
    (r"busca?\s+(?:en\s+google\s+)?[\"']?(.+)[\"']?\s*$", "search_google", None),
    (r"googlea?\s+(.+)", "search_google", None),
    (r"busca?\s+en\s+youtube\s+(.+)", "search_youtube", None),

    # ── SISTEMA / HORA ────────────────────────────────────────────────
    (r"qu[eé]\s+hora\s+es|dime\s+la\s+hora|hora\s+actual", "get_time", None),
    (r"qu[eé]\s+d[ií]a\s+es|fecha\s+(?:de\s+)?hoy|d[ií]a\s+de\s+hoy", "get_date", None),
    (r"cu[aá]nto\s+tiempo\s+llevas?\s+(?:activ[oa]|corriendo|prendid[oa])", "get_uptime", None),

    # ── ARKANI NEXUS PROPIO ───────────────────────────────────────────
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?(?:tab\s+de\s+)?hipocampo", "nav_tab", "hipocampo"),
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?(?:tab\s+de\s+)?explorador", "nav_tab", "explorador"),
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?(?:tab\s+de\s+)?errores", "nav_tab", "errores"),
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?(?:tab\s+de\s+)?avatar", "nav_tab", "avatar"),
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?m2m", "nav_tab", "compartir_m2m"),
    (r"(?:mu[eé]strame?|abre?|ve\s+a)\s+(?:el\s+)?capacidades", "nav_tab", "capacidades"),

    # ── MÚSICA / MEDIA ────────────────────────────────────────────────
    (r"pon\s+(?:una?\s+)?m[uú]sica|toca\s+(?:algo\s+de\s+)?m[uú]sica", "open_url", "https://open.spotify.com"),
    (r"pon\s+(.+)\s+en\s+(?:youtube|spotify)", "search_youtube", None),

    # ── CLIMA ─────────────────────────────────────────────────────────
    (r"c[oó]mo\s+(?:estar[aá]|est[aá])\s+el\s+clima|clima\s+(?:de\s+)?hoy|va\s+a\s+llover", "open_url", "https://weather.com/es-MX"),
    (r"clima\s+en\s+xalapa|clima\s+xalapa", "open_url", "https://weather.com/es-MX/tiempo/hoy/l/Xalapa+Veracruz+Mexico"),

    # ── CALCULADORA / CONVERSIONES ────────────────────────────────────
    (r"cu[aá]nto\s+es\s+([\d\s\+\-\*\/\.\(\)]+)[\?]?$", "calculate", None),
    (r"calcula?\s+([\d\s\+\-\*\/\.\(\)]+)", "calculate", None),

    # ── APAGAR / REINICIAR ARKANI ─────────────────────────────────────
    (r"apaga(?:te)?|cierra(?:te)?\s+arkani|termina(?:te)?", "shutdown_arkani", None),
    (r"reinicia(?:te)?\s+arkani|restart\s+arkani", "restart_arkani", None),

    # ── NOTAS RÁPIDAS ─────────────────────────────────────────────────
    (r"anota\s+(?:que\s+)?(.+)|recuerda\s+que\s+(.+)", "save_note", None),
    (r"mu[eé]strame?\s+mis?\s+notas|qu[eé]\s+notas\s+tengo", "show_notes", None),
]

# Respuestas confirmación por acción
ACTION_RESPONSES = {
    "open_url":         "Abriendo {param} en el navegador.",
    "open_url_dynamic": "Abriendo {param}.",
    "search_google":    "Buscando '{param}' en Google.",
    "search_youtube":   "Buscando '{param}' en YouTube.",
    "get_time":         "Son las {result}.",
    "get_date":         "Hoy es {result}.",
    "get_uptime":       "Llevo activo desde {result}.",
    "nav_tab":          "Navegando a la pestaña {param}.",
    "calculate":        "{param} = {result}",
    "save_note":        "Nota guardada: '{param}'",
    "show_notes":       "{result}",
    "shutdown_arkani":  "Apagando ARKANI NEXUS. Hasta luego.",
    "restart_arkani":   "Reiniciando ARKANI NEXUS...",
}

# ─────────────────────────────────────────────
# NOTAS RÁPIDAS (en memoria + archivo)
# ─────────────────────────────────────────────
NOTES_PATH = Path.home() / "NEXUS" / "notas_rapidas.json"

def load_notes() -> list:
    if NOTES_PATH.exists():
        try:
            return json.loads(NOTES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def save_note_to_disk(text: str):
    notes = load_notes()
    notes.append({"text": text, "timestamp": datetime.now().isoformat()})
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTES_PATH.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────
# MOTOR DE COMANDOS
# ─────────────────────────────────────────────
class Commander:
    """
    Interceptor de comandos del sistema para ARKANI NEXUS.
    Se ejecuta ANTES de Ollama — respuesta en <50ms.
    """

    def __init__(self):
        self._start_time = datetime.now()
        self._patterns = [(re.compile(p, re.IGNORECASE), a, v) for p, a, v in INTENT_PATTERNS]

    # ──────────────────────────────────────────
    def match_and_execute(self, user_input: str) -> dict:
        """
        Punto de entrada principal.
        Retorna:
          { executed: bool, action: str, response: str, nav_tab: str|None }
        Si executed=False, pasar a Ollama normalmente.
        """
        text = user_input.strip()

        for pattern, action, static_param in self._patterns:
            m = pattern.search(text)
            if not m:
                continue

            # Extraer parámetro dinámico si aplica
            param = static_param
            if action in ("open_url_dynamic", "search_google", "search_youtube", "calculate", "save_note"):
                param = m.group(1).strip() if m.lastindex and m.group(1) else text

            return self._execute(action, param, text)

        return {"executed": False, "action": None, "response": "", "nav_tab": None}

    # ──────────────────────────────────────────
    def _execute(self, action: str, param: Optional[str], raw_input: str) -> dict:
        """Ejecuta la acción y retorna resultado."""
        result = ""
        nav_tab = None
        success = True

        try:
            if action == "open_url":
                self._open_url(param)

            elif action == "open_url_dynamic":
                self._open_url(param)

            elif action == "search_google":
                url = f"https://www.google.com/search?q={param.replace(' ', '+')}"
                self._open_url(url)

            elif action == "search_youtube":
                url = f"https://www.youtube.com/results?search_query={param.replace(' ', '+')}"
                self._open_url(url)

            elif action == "get_time":
                result = datetime.now().strftime("%I:%M %p")

            elif action == "get_date":
                days = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
                months = ["enero","febrero","marzo","abril","mayo","junio",
                          "julio","agosto","septiembre","octubre","noviembre","diciembre"]
                now = datetime.now()
                result = f"{days[now.weekday()]} {now.day} de {months[now.month-1]} de {now.year}"

            elif action == "get_uptime":
                delta = datetime.now() - self._start_time
                h, m = divmod(delta.seconds // 60, 60)
                result = self._start_time.strftime("%I:%M %p")
                if h > 0:
                    result += f" (hace {h}h {m}min)"
                else:
                    result += f" (hace {m} minutos)"

            elif action == "nav_tab":
                nav_tab = param
                result = param

            elif action == "calculate":
                # Evaluación segura de expresiones matemáticas básicas
                safe_expr = re.sub(r"[^0-9\+\-\*\/\.\(\)\s]", "", param)
                if safe_expr.strip():
                    calc_result = eval(safe_expr, {"__builtins__": {}})
                    result = str(round(calc_result, 6))
                else:
                    success = False

            elif action == "save_note":
                save_note_to_disk(param)
                result = param

            elif action == "show_notes":
                notes = load_notes()
                if notes:
                    result = "\n".join([f"• {n['text']}" for n in notes[-5:]])
                else:
                    result = "No tienes notas guardadas aún."

            elif action == "shutdown_arkani":
                # Señal suave — el frontend puede manejar esto
                pass

            elif action == "restart_arkani":
                pass

        except Exception as e:
            success = False
            result = str(e)

        if not success:
            return {"executed": False, "action": None, "response": "", "nav_tab": None}

        # Formatear respuesta
        template = ACTION_RESPONSES.get(action, "Listo.")
        response = template.format(param=param or "", result=result)

        return {
            "executed": True,
            "action": action,
            "response": response,
            "nav_tab": nav_tab,
            "param": param,
        }

    # ──────────────────────────────────────────
    def _open_url(self, url: str):
        """Abre URL en el navegador del sistema."""
        if IS_LINUX:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            os.startfile(url)

    # ──────────────────────────────────────────
    def add_pattern(self, pattern: str, action: str, param: Optional[str] = None):
        """Añade un patrón en caliente sin reiniciar."""
        compiled = re.compile(pattern, re.IGNORECASE)
        self._patterns.insert(0, (compiled, action, param))

    def list_actions(self) -> list:
        """Lista todas las acciones disponibles (para la pestaña CAPACIDADES)."""
        seen = set()
        result = []
        for _, action, param in self._patterns:
            if action not in seen:
                seen.add(action)
                result.append({"action": action, "example_param": param})
        return result


# ─────────────────────────────────────────────
# INSTANCIA GLOBAL
# ─────────────────────────────────────────────
commander = Commander()


# ─────────────────────────────────────────────
# PARCHE PARA arkani_web.py
# ─────────────────────────────────────────────
"""
INSTRUCCIONES DE INTEGRACIÓN EN arkani_web.py:
════════════════════════════════════════════════

1. Al inicio del archivo añadir:

    from nexus_commander import commander

2. En el handler de /chat, ANTES de llamar a Ollama:

    @app.route('/chat', methods=['POST'])
    def chat():
        data = request.get_json()
        user_input = data.get('message', '').strip()

        # ── NUEVO: interceptar comandos del sistema ──────────────
        cmd = commander.match_and_execute(user_input)
        if cmd["executed"]:
            response_data = {
                "response": cmd["response"],
                "action": cmd["action"],
                "nav_tab": cmd.get("nav_tab"),   # el frontend navega al tab
                "evolved": False,
                "evol_count": 0,
            }
            return jsonify(response_data)
        # ── FIN NUEVO ────────────────────────────────────────────

        # ... aquí continúa tu código normal que llama a Ollama ...

3. En el frontend (index.html), en la función que recibe la respuesta del chat:

    // Después de mostrar la respuesta en el chat:
    if (data.nav_tab) {
        // Navegar automáticamente al tab indicado
        const tabEl = document.querySelector(`[data-tab="${data.nav_tab}"]`);
        if (tabEl) tabEl.click();
    }
    if (data.action) {
        console.log('ARKANI Commander:', data.action);
    }

════════════════════════════════════════════════
CÓMO AÑADIR NUEVOS COMANDOS EN CALIENTE:
────────────────────────────────────────────────
    from nexus_commander import commander

    # Añadir al vuelo (sin reiniciar):
    commander.add_pattern(
        r"abre?\s+medcloud",
        "open_url",
        "https://tu-url-medcloud.com"
    )

════════════════════════════════════════════════
"""


# ─────────────────────────────────────────────
# TEST RÁPIDO
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=== TEST nexus_commander.py ===\n")

    tests = [
        "abre youtube",
        "Arkaneavra youtube",          # este fallará → va a Ollama (correcto)
        "abre el gmail",
        "busca en google recetas de tamales",
        "qué hora es",
        "qué día es hoy",
        "cuánto es 145 * 37",
        "anota que mañana es la reunión con el equipo",
        "muéstrame el hipocampo",
        "clima en xalapa",
    ]

    for t in tests:
        result = commander.match_and_execute(t)
        status = "✓ EJECUTADO" if result["executed"] else "→ pasa a Ollama"
        action = f"[{result['action']}]" if result["action"] else ""
        response = result["response"] if result["executed"] else ""
        print(f'  {status} {action}  "{t}"')
        if response:
            print(f'    → {response}')

    print(f"\n=== FIN TEST ===")

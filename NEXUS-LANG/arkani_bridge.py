"""
ARKANI BRIDGE v1.1
Conecta core + agent + brain
"""
try:
    from nexus_brain import NexusBrain
    brain = NexusBrain()
    BRAIN_DISPONIBLE = True
except Exception:
    BRAIN_DISPONIBLE = False

try:
    from nexus_evolve import NexusEvolve
    evolve = NexusEvolve()
    EVOLVE_DISPONIBLE = True
except Exception:
    EVOLVE_DISPONIBLE = False

KEYWORDS_AGENTE = [
    'busca en internet', 'navega', 'descarga', 'ejecuta',
    'crea un archivo', 'lista archivos', 'instala', 'agente'
]

KEYWORDS_BRAIN = [
    'autoprograma', 'evoluciona', 'escribe codigo',
    'crea funcion', 'genera modulo'
]
KEYWORDS_EVOLVE = [
    'autocuracion', 'autocuracion', 'repara errores',
    'escanea errores', 'ciclo autocuracion', 'auto-curacion',
    'ciclo autocuración', 'escaner', 'escanear archivos', 'escanea'
]

def decidir_modo(pregunta):
    p = pregunta.lower()
    if any(k in p for k in KEYWORDS_EVOLVE):
        return "EVOLVE"
    if any(k in p for k in KEYWORDS_BRAIN):
        return "BRAIN"
    if any(k in p for k in KEYWORDS_AGENTE):
        return "AGENTE"
    return "CORE"

def procesar(pregunta, engine=None):
    modo = decidir_modo(pregunta)

    if modo == "BRAIN" and BRAIN_DISPONIBLE:
        try:
            partes = pregunta.split(':', 1)
            if len(partes) > 1:
                tarea = partes[1].strip().split('\n')[0].replace(' ','_')
                logica = partes[1].strip() if '\n' in partes[1] else f"def {tarea}():\n    pass"
            else:
                tarea = pregunta.replace('autoprograma','').replace('evoluciona','').strip().replace(' ','_')
                logica = f"def {tarea}():\n    pass"
            resultado = brain.auto_evolve(tarea, logica)
            return f"✅ Brain: {resultado}"
        except Exception as e:
            return f"Error brain: {e}"

    elif modo == "EVOLVE" and EVOLVE_DISPONIBLE:
        try:
            p = pregunta.lower()
            if 'escanea' in p:
                r = evolve.escanear_autogen()
                return f"Escaneo: {len(r[chr(111)+chr(107)])} OK, {len(r[chr(101)+chr(114)+chr(114)+chr(111)+chr(114)+chr(101)+chr(115)])} errores"
            else:
                return evolve.ciclo_autocuracion()
        except Exception as e:
            return f"Error evolve: {e}"
    elif modo == "AGENTE":
        try:
            from arkani_agent import correr_agente
            return correr_agente(pregunta)
        except Exception as e:
            return f"Error agente: {e}"

    else:
        try:
            if engine:
                return engine.chat(pregunta)
            return "Engine no disponible"
        except Exception as e:
            return f"Error core: {e}"

def estado_bridge():
    try:
        from arkani_agent import correr_agente
        agente_ok = True
    except:
        agente_ok = False
    return {
        "bridge": "ONLINE",
        "brain": BRAIN_DISPONIBLE,
        "agente": agente_ok,
        "version": "1.1"
    }

if __name__ == "__main__":
    print("Bridge v1.1", estado_bridge())

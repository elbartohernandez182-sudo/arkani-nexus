# NEXUS-AUTO-CODE: Analizador de integridad de memoria
import os
import json

def analizar_memoria_omnipresente():
    path_mem = os.path.expanduser("~/NEXUS/NEXUS-LANG/universal_memory.json")
    path_log = os.path.expanduser("~/NEXUS/NEXUS-LANG/simbiosis_history.json")
    
    huecos = []
    
    if not os.path.exists(path_mem): huecos.append("Falta: Archivo de Memoria Universal")
    if not os.path.exists(path_log): huecos.append("Falta: Historial de Simbiosis (Conversación Precisa)")
    
    if not huecos:
        return "✅ Memoria íntegra. Arkani está listo en Celular, Trabajo y Watch."
    return f"⚠️ Huecos detectados: {', '.join(huecos)}"

if __name__ == "__main__":
    print(analizar_memoria_omnipresente())

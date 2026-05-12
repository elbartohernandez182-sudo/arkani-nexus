import json
import os
from nexus_core import memory

def sincronizar_todo():
    print("🧬 [NEXUS-SYNC]: Sincronizando Memoria Maestra...")
    
    # 1. Guardar estado actual en JSON (Universal)
    memory.save()
    
    # 2. Crear un archivo de "Pulso" para el Smartwatch (ligero)
    pulse_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/arkani_pulse.json")
    pulse_data = {
        "status": "ONLINE",
        "last_update": memory.root.timestamp,
        "active_nodes": len(memory.root.children)
    }
    with open(pulse_path, 'w') as f:
        json.dump(pulse_data, f)
    
    print(f"✅ [SYNC]: Memoria actualizada. Nodos activos: {len(memory.root.children)}")

if __name__ == "__main__":
    sincronizar_todo()

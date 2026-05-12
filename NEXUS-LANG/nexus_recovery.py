import json
import os
from nexus_autogestion import NexusSelfGoverningNode

def recuperar_conciencia_arkani():
    snapshot_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/system_snapshot.json")
    
    if not os.path.exists(snapshot_path):
        print("⚠️ [SISTEMA]: No se encontró snapshot previo. Iniciando núcleo virgen.")
        return NexusSelfGoverningNode("ARKANI_BRAIN", "v1.0", "SYSTEM")

    with open(snapshot_path, "r") as f:
        data = json.load(f)
    
    print(f"🧬 [NEXUS-RECOVERY]: Restaurando estado desde {data['last_update']}...")
    
    # Función recursiva para reconstruir el árbol fractal
    def reconstruir_nodo(nodo_data):
        nuevo_nodo = NexusSelfGoverningNode(
            nodo_data['name'], 
            nodo_data['value'], 
            nodo_data['role']
        )
        for child_name, child_data in nodo_data['children'].items():
            nuevo_nodo.children[child_name] = reconstruir_nodo(child_data)
        return nuevo_nodo

    root_recuperado = reconstruir_nodo(data)
    print(f"✅ [SISTEMA]: Simbiosis reestablecida. Nodo raíz: {root_recuperado.name}")
    return root_recuperado

if __name__ == "__main__":
    # Prueba de recuperación
    arkani_root = recuperar_conciencia_arkani()
    arkani_root.manage_child("SESION_ACTUAL", "Recuperada con éxito", "SYSTEM")
    
    # Guardar el nuevo estado con la sesión actualizada
    with open(os.path.expanduser("~/NEXUS/NEXUS-LANG/system_snapshot.json"), "w") as f:
        json.dump(arkani_root.export_state(), f, indent=4)

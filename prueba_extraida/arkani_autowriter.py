import os
from datetime import datetime

def auto_escribir_nodo(nombre_nodo, logica):
    path = os.path.expanduser(f"~/NEXUS/NEXUS-LANG/autogen/{nombre_nodo}.py")
    with open(path, "w") as f:
        f.write(f"# ARkani AUTO-GEN | {datetime.now()}\n")
        f.write(logica)
    
    # Esto es lo que faltaba: una confirmación visual en tu terminal
    print(f"🧬 [ARKANI]: Nodo '{nombre_nodo}' escrito físicamente en {path}")

if __name__ == "__main__":
    # Prueba de vida: Creamos un gestor de versiones para NEXUS-LANG
    logica_ejemplo = "def version(): return 'NEXUS-LANG v0.1-FRACTAL'"
    auto_escribir_nodo("node_version_control", logica_ejemplo)

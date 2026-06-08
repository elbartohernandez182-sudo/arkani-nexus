# NODE: FRACTAL_MEMORY
# GEN: 2026-03-26
# Función: Almacenamiento de patrones recursivos para NEXUS-LANG

import json
import os
from datetime import datetime

class FractalMemory:
    def __init__(self):
        self.db_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/memoria_fractal.json")
        if not os.path.exists(self.db_path):
            with open(self.db_path, "w") as f:
                json.dump({"patrones": [], "ultima_actualizacion": ""}, f)

    def guardar_patron(self, nombre_tarea, niveles):
        with open(self.db_path, "r") as f:
            data = json.load(f)
        
        nuevo_registro = {
            "tarea": nombre_tarea,
            "complejidad_niveles": niveles,
            "timestamp": str(datetime.now())
        }
        
        data["patrones"].append(nuevo_registro)
        data["ultima_actualizacion"] = str(datetime.now())
        
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=4)
        
        print(f"🧠 [MEMORIA]: Patrón '{nombre_tarea}' grabado en el ADN del sistema.")

if __name__ == "__main__":
    memo = FractalMemory()
    memo.guardar_patron("ESTRUCTURA_MADRE", 3)

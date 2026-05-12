import json
import os
from datetime import datetime

LOG_PATH = os.path.expanduser("~/NEXUS/NEXUS-LANG/simbiosis_history.json")

def inicializar_historial():
    primer_registro = [{
        "t": datetime.now().isoformat(),
        "a": "INICIO_SIMBIOSIS",
        "d": "ADN de NEXUS-LANG consolidado. Memoria precisa activada para acceso omnipresente."
    }]
    
    with open(LOG_PATH, 'w') as f:
        json.dump(primer_registro, f, indent=2)
    print("📝 [MEMORIA]: Historial de Simbiosis creado con éxito.")

if __name__ == "__main__":
    inicializar_historial()

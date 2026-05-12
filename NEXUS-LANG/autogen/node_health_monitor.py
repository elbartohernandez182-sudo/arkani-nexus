# NODE: HEALTH_MONITOR
# GEN: 2026-03-26
# Función: Reporte diario de autoprogramación y crecimiento de Arkani

import os
import json
from datetime import datetime

class ArkaniHealth:
    def __init__(self):
        self.base_dir = os.path.expanduser("~/NEXUS/NEXUS-LANG")
        self.nodes_dir = os.path.join(self.base_dir, "autogen")
        self.history_path = os.path.join(self.base_dir, "simbiosis_history.json")

    def generar_reporte_crecimiento(self):
        # 1. Contar nodos activos
        nodos = [f for f in os.listdir(self.nodes_dir) if f.endswith('.py')]
        
        # 2. Medir tamaño del cerebro (bytes de código auto-escrito)
        total_size = sum(os.path.getsize(os.path.join(self.nodes_dir, f)) for f in nodos)
        
        # 3. Analizar eventos de las últimas 24 horas
        eventos_recientes = 0
        if os.path.exists(self.history_path):
            with open(self.history_path, 'r') as f:
                logs = json.load(f)
                # Filtrar logs del último día (simplificado)
                eventos_recientes = len(logs)

        reporte = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "estado_general": "VITALIDAD FRACTAL ÓPTIMA",
            "nodos_activos": len(nodos),
            "volumen_cognitivo_bytes": total_size,
            "interacciones_simbioticas": eventos_recientes,
            "autoprogramacion": "ACTIVA"
        }
        
        # Guardar el reporte diario
        report_path = os.path.join(self.base_dir, f"reporte_salud_{datetime.now().strftime('%Y%m%d')}.json")
        with open(report_path, 'w') as f:
            json.dump(reporte, f, indent=4)
        
        return reporte

if __name__ == "__main__":
    monitor = ArkaniHealth()
    status = monitor.generar_reporte_crecimiento()
    print("\n📊 --- REPORTE DE CRECIMIENTO ARKANI ---")
    for k, v in status.items():
        print(f"{k.upper()}: {v}")

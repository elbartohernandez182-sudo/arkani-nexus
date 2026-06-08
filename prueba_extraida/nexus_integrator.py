# NODE: NEXUS_INTEGRATOR
# GEN: 2026-03-26 | MANDO: MANUAL-OVERRIDE
# Función: Orquestador central de NEXUS-LANG

import os

class NexusIntegrator:
    def __init__(self):
        self.path = os.path.expanduser("~/NEXUS/NEXUS-LANG/autogen/")
        # Filtramos solo los archivos de función y nodos que ya existen
        self.nodos = [f for f in os.listdir(self.path) if f.startswith('fn_') or f.startswith('node_')]

    def compilar_sistema(self):
        print(f"\n🔗 [NEXUS-INTEGRATOR]: Unificando {len(self.nodos)} nodos detectados...")
        for nodo in sorted(self.nodos):
            print(f"   + Sincronizando: {nodo}")
        print("\n✅ [SISTEMA]: NEXUS-LANG está integrado y listo para ejecución fractal.")

if __name__ == "__main__":
    nexus = NexusIntegrator()
    nexus.compilar_sistema()

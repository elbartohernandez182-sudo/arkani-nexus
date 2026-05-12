import os
import json
from datetime import datetime

class NexusSelfGoverningNode:
    def __init__(self, name, value="", role="DATA"):
        self.name = name
        self.value = value
        self.role = role  # DATA, LOG, SYSTEM, CLINICAL
        self.children = {}
        self.last_update = datetime.now().isoformat()
        self.integrity_hash = self._generate_id()

    def _generate_id(self):
        # Identificador único simplificado para trazabilidad fractal
        return f"{self.name}_{hash(self.value + self.last_update)}"

    def manage_child(self, name, value="", role="DATA"):
        # Autogestión: Si el nodo ya existe, actualiza; si no, crea.
        if name in self.children:
            self.children[name].value = value
            self.children[name].last_update = datetime.now().isoformat()
            print(f"🔄 [NEXUS-LANG]: Nodo '{name}' actualizado por autogestión.")
        else:
            self.children[name] = NexusSelfGoverningNode(name, value, role)
            print(f"🌱 [NEXUS-LANG]: Nuevo nodo '{name}' ramificado.")
        return self.children[name]

    def health_check(self):
        # Verificación de integridad recursiva
        issues = 0
        for child_name, child_node in self.children.items():
            if not child_node.name:
                print(f"⚠️ [ALERTA]: Error de integridad en rama {child_name}")
                issues += 1
            issues += child_node.health_check()
        return issues

    def export_state(self):
        # Guarda el estado actual para persistencia tras reinicios
        state = {
            "name": self.name,
            "value": self.value,
            "role": self.role,
            "last_update": self.last_update,
            "children": {k: v.export_state() for k, v in self.children.items()}
        }
        return state

# --- EJECUCIÓN DEL MOTOR DE AUTOGESTIÓN ---
print("\n" + "🧬"*15)
print("INICIANDO AUTOGESTIÓN NEXUS-LANG")
print("🧬"*15 + "\n")

# Nodo raíz con rol de Sistema
root = NexusSelfGoverningNode("ARKANI_BRAIN", "v1.0", "SYSTEM")

# Autogestión de módulos críticos
root.manage_child("MEMORIA_CORTA", "Activa", "LOG")
root.manage_child("PROCESADOR_CLINICO", "Esperando Capturas", "CLINICAL")

# Verificación automática
errores = root.health_check()
if errores == 0:
    print("\n✅ [ESTADO]: Integridad Fractal 100% - Sistema Autogestionado.")
    
# Guardar snapshot del sistema
with open(os.path.expanduser("~/NEXUS/NEXUS-LANG/system_snapshot.json"), "w") as f:
    json.dump(root.export_state(), f, indent=4)

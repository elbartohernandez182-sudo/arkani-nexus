import json
import os
from datetime import datetime

class NexusNode:
    def __init__(self, name, value="", role="DATA"):
        self.name = name
        self.value = value
        self.role = role
        self.children = {}
        self.timestamp = datetime.now().isoformat()

    def add(self, name, value="", role="DATA"):
        self.children[name] = NexusNode(name, value, role)
        return self.children[name]

    def to_dict(self):
        return {
            "n": self.name,
            "v": self.value,
            "r": self.role,
            "t": self.timestamp,
            "c": {k: v.to_dict() for k, v in self.children.items()}
        }

class ArkaniMemory:
    def __init__(self):
        self.path = os.path.expanduser("~/NEXUS/NEXUS-LANG/universal_memory.json")
        self.root = self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                data = json.load(f)
                return self._reconstruct(data)
        return NexusNode("ARKANI_BRAIN", "v2.0", "SYSTEM")

    def _reconstruct(self, data):
        node = NexusNode(data['n'], data['v'], data['r'])
        node.timestamp = data['t']
        for k, v in data['c'].items():
            node.children[k] = self._reconstruct(v)
        return node

    def save(self):
        with open(self.path, 'w') as f:
            json.dump(self.root.to_dict(), f, indent=2)
        # Crear copia ligera para Smartwatch
        with open(os.path.expanduser("~/NEXUS/NEXUS-LANG/watch_sync.json"), 'w') as f:
            summary = {"status": self.root.value, "last": self.root.timestamp}
            json.dump(summary, f)

# Inicialización única para todo el sistema
memory = ArkaniMemory()

def registrar_simbiosis(interaccion, detalle):
    log_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/simbiosis_history.json")
    historial = []
    
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            historial = json.load(f)
            
    historial.append({
        "timestamp": datetime.now().isoformat(),
        "accion": interaccion,
        "detalle": detalle
    })
    
    with open(log_path, 'w') as f:
        json.dump(historial, f, indent=2)
    print("📝 [MEMORIA]: Interacción grabada en el historial de simbiosis.")


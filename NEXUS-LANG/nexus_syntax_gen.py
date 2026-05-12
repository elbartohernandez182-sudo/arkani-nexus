import json
import os

class NexusSyntaxGenerator:
    def __init__(self):
        self.vocabulary = {
            "CLINICAL": "🔍 HALLAZGO",
            "SYSTEM": "⚙️ NÚCLEO",
            "DATA": "📊 DATO",
            "LOG": "📝 REGISTRO"
        }

    def generate_statement(self, node):
        # Generador de sintaxis recursivo para NEXUS-LANG
        role_label = self.vocabulary.get(node.role, "🔹")
        statement = f"{role_label} [{node.name}]: {node.value}"
        
        # Generar sintaxis para las ramas hijas (estructura fractal)
        sub_statements = []
        for child_name, child_node in node.children.items():
            sub_statements.append(self.generate_statement(child_node))
            
        if sub_statements:
            joined_sub = "\n  ↳ ".join(sub_statements)
            return f"{statement}\n  ↳ {joined_sub}"
        return statement

    def export_report(self, root_node, filename="ultimo_reporte.nexus"):
        report_content = self.generate_statement(root_node)
        path = os.path.expanduser(f"~/NEXUS/data/processed_reports/{filename}")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write("=== REPORTE GENERADO POR ARKANI (NEXUS-LANG) ===\n")
            f.write(report_content)
            f.write("\n===============================================")
        
        print(f"✅ [SINTAXIS]: Reporte generado con éxito en {path}")
        return report_content

# --- PRUEBA DEL GENERADOR DE SINTAXIS ---
if __name__ == "__main__":
    from nexus_recovery import recuperar_conciencia_arkani
    
    # Recuperamos el cerebro
    root = recuperar_conciencia_arkani()
    
    # Agregamos una rama de prueba clínica para validar la sintaxis
    estudio = root.manage_child("ESTUDIO_001", "Resonancia Lumbar", "CLINICAL")
    estudio.manage_child("HALLAZGO_RAD", "Espondiloartrosis L4-L5", "CLINICAL")
    
    # Generamos la sintaxis
    gen = NexusSyntaxGenerator()
    print("\n" + "="*40)
    print(gen.generate_statement(root))
    print("="*40 + "\n")
    
    # Exportamos el archivo
    gen.export_report(root)

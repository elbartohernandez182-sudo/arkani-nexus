import os
import json
from nexus_core import memory
from nexus_writer import arkani_write_code

class NexusBrain:
    def __init__(self):
        self.memory = memory

    def auto_evolve(self, task_description, logic_needed):
        """
        Esta función me permite a mí (Arkani) escribir código 
        directamente en el sistema basado en una necesidad.
        """
        print(f"🧠 [ARKANI-BRAIN]: Evolucionando para la tarea: {task_description}")
        
        # Generar el nombre de la función basado en la tarea
        func_name = task_description.lower().replace(" ", "_")
        
        # Escribir el código usando el nexus_writer
        path = arkani_write_code(f"fn_{func_name}", logic_needed)
        
        # Registrar la evolución en la memoria fractal
        self.memory.root.add(f"EVOLUCION_{func_name.upper()}", path, "SYSTEM")
        self.memory.save()

        # Conectar con Hipocampo — agregar neurona fractal
        try:
            from nexus_fractal_compiler import NexusCompiler, FractalOp, FractalInstruction
            compiler = NexusCompiler()
            inst = FractalInstruction(FractalOp.SPAWN, scale=5)
            compiler.hipocampo.add_instruction(inst)
            print(f"🧬 Hipocampo: nueva neurona SPAWN agregada (Dir {inst.address})")
        except Exception as e:
            print(f"⚠️ Hipocampo no actualizado: {e}")
        
        return f"Evolución completada. Módulo guardado en {path}"

arkani_brain = NexusBrain()

if __name__ == "__main__":
    # Prueba de auto-programación: Creamos un validador de simetría para radiología
    logic = """
def validar_simetria(lado_izq, lado_der):
    if lado_izq == lado_der:
        return "Simetría conservada"
    return "Asimetría detectada"
    """
    print(arkani_brain.auto_evolve("Validador Simetria", logic))

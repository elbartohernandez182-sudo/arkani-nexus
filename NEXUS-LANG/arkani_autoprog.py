#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARKANI AUTOPROGRAMADOR v1.0
Fusión: nexus_brain.auto_evolve + arkani_agent ReAct
Constructor: Medico Radiologo, Xalapa
"""

import os
import json
from datetime import datetime

def auto_evolve(task_description: str, logic_code: str, mem=None) -> str:
    """
    Arkani escribe código directamente basado en una necesidad.
    Fusión de nexus_brain + agente ReAct.
    """
    print(f"🧠 [ARKANI-BRAIN]: Evolucionando para: {task_description}")
    
    # Generar nombre del módulo
    func_name = task_description.lower().replace(" ", "_")[:30]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Directorio de scripts autogenerados
    scripts_dir = os.path.expanduser("~/NEXUS/NEXUS-LANG/autogen")
    os.makedirs(scripts_dir, exist_ok=True)
    
    # Escribir el código
    filename = f"fn_{func_name}.py"
    path = os.path.join(scripts_dir, filename)
    
    header = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-generado por Arkani
Tarea: {task_description}
Fecha: {datetime.now().isoformat()}
"""

'''
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(header + logic_code)
    
    print(f"✅ Módulo guardado: {path}")
    
    # Registrar en memoria si está disponible
    if mem:
        try:
            mem.aprender_hecho(
                f"autoprog:{func_name}",
                f"Módulo creado: {filename} - {task_description}"
            )
            mem.guardar()
        except:
            pass
    
    # Verificar sintaxis
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "py_compile", path],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        return f"✅ Evolución completada. Módulo '{filename}' guardado y verificado."
    else:
        return f"⚠️ Módulo guardado pero tiene errores: {result.stderr[:200]}"


def autoprogramar_desde_chat(descripcion: str, mem=None) -> str:
    """
    Punto de entrada desde el chat web.
    Usa el agente ReAct para generar el código.
    """
    try:
        from arkani_agent import correr_agente
        
        objetivo = f"""Escribe código Python para: {descripcion}
        
El código debe:
1. Ser una función Python completa y funcional
2. Tener docstring explicando qué hace
3. Manejar errores con try/except
4. Incluir un ejemplo de uso al final

Devuelve SOLO el código Python, sin explicaciones adicionales."""
        
        codigo_generado = correr_agente(objetivo, verbose=False)
        
        # Guardar el código generado
        resultado = auto_evolve(descripcion, codigo_generado, mem)
        return resultado
        
    except Exception as e:
        # Fallback: guardar la descripción como tarea pendiente
        return f"Tarea registrada para autoprogramación: {descripcion}. Error: {e}"


if __name__ == "__main__":
    print("🧠 ARKANI AUTOPROGRAMADOR v1.0")
    print("=" * 50)
    
    # Test básico
    test_logic = '''
def validar_simetria(lado_izq, lado_der):
    """Valida simetría en imagen radiológica."""
    if lado_izq == lado_der:
        return "Simetría conservada"
    return f"Asimetría detectada: izq={lado_izq}, der={lado_der}"

if __name__ == "__main__":
    print(validar_simetria(10, 10))
    print(validar_simetria(10, 15))
'''
    
    resultado = auto_evolve("Validador Simetria Radiologica", test_logic)
    print(resultado)

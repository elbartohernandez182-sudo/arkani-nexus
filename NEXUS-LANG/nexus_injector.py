import importlib.util
import os
import sys

def inyectar_funcion_dinamica(nombre_archivo):
    path = os.path.expanduser(f"~/NEXUS/NEXUS-LANG/autogen/{nombre_archivo}")
    
    if not os.path.exists(path):
        print(f"❌ [INJECTOR]: No se encuentra el archivo {nombre_archivo}")
        return None

    # Cargar el módulo dinámicamente
    spec = importlib.util.spec_from_file_location("modulo_dinamico", path)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    
    # Extraer la función (asumiendo que tiene el mismo nombre que el archivo sin fn_)
    nombre_func = nombre_archivo.replace("fn_", "").replace(".py", "")
    func = getattr(modulo, nombre_func)
    
    print(f"🧬 [INJECTOR]: Función '{nombre_func}' integrada al flujo de Arkani.")
    return func

if __name__ == "__main__":
    # Probamos inyectando la función de volumen que creaste antes
    func_volumen = inyectar_funcion_dinamica("fn_calcular_volumen_lesion.py")
    if func_volumen:
        resultado = func_volumen()
        print(f"📡 Resultado de ejecución: {resultado}")

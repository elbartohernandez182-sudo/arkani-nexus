# GUARDADO POR CONSTRUCTOR
# 2026-05-28T13:31:35.739277

# Nuevo módulo
def mi_funcion():
    """Descripción"""
    pass
import os
import json

def olvida_y_busca():
    """Busca y lista todos los archivos de autogen con descripcion"""
    base = '/home/arkani/NEXUS/NEXUS-LANG/'
    autogen = base + 'autogen/'
    
    archivos = sorted([f for f in os.listdir(autogen) if f.endswith('.py')])
    
    resultado = []
    for archivo in archivos:
        ruta = autogen + archivo
        try:
            with open(ruta) as f:
                lineas = f.readlines()
            desc = 'Sin descripcion'
            for linea in lineas[:10]:
                if '"""' in linea or "'''" in linea:
                    desc = linea.strip().replace('"""','').replace("'''","")
                    break
            resultado.append(f"{archivo}: {desc}")
        except:
            resultado.append(f"{archivo}: no legible")
    
    return '\n'.join(resultado)

if __name__ == '__main__':
    print(olvida_y_busca())
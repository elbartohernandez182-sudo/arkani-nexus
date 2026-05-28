# GUARDADO POR CONSTRUCTOR
# 2026-05-28T14:49:40.165579

import os

def leer_mis_archivos(archivo=None):
    """Lee archivos reales de autogen en tiempo real"""
    base = '/home/arkani/NEXUS/NEXUS-LANG/autogen/'
    if archivo:
        try:
            with open(base + archivo) as f:
                return f.read()
        except:
            return f'No encontre {archivo}'
    archivos = sorted([f for f in os.listdir(base) if f.endswith('.py')])
    resultado = []
    for a in archivos:
        try:
            with open(base + a) as f:
                lineas = f.readlines()[:3]
            resultado.append(f"{a}: {''.join(lineas).strip()[:80]}")
        except:
            resultado.append(f"{a}: no legible")
    return '\n'.join(resultado)

if __name__ == '__main__':
    print(leer_mis_archivos())
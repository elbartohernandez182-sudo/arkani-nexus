# ARKANI AUTO-GEN — calcular indice de masa corporal
# Generado: 2026-05-27T21:06:09.125471
# Evoluciones sesión: 1/10

def indice_masa_corporal(peso: float, altura: float) -> float:
    """
    Calcula el índice de masa corporal.
    """
    return peso / (altura ** 2)

print(indice_masa_corporal(70.5, 1.75))
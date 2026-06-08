def corregir_terminologia(texto):
    
    terminos_incorrectos = ["osteocondrosis", "desgaste", "pico de loro"]
    for t in terminos_incorrectos:
        texto = texto.replace(t, "espondiloartrosis")
    return texto
    
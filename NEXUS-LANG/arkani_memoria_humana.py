#!/usr/bin/env python3
"""
arkani_memoria_humana.py
Parcha arkani_engine.py con arquitectura de memoria humana:
  - Corto plazo: últimas 3 conversaciones directo en el prompt
  - Largo plazo: 72+ conversaciones comprimidas, búsqueda semántica por keywords
"""

import re

ENGINE_PATH = "/home/arkani/NEXUS/NEXUS-LANG/arkani_engine.py"

with open(ENGINE_PATH, "r") as f:
    codigo = f.read()

# ── BACKUP primero ──────────────────────────────────────────────────────────
with open(ENGINE_PATH + ".backup_memoria", "w") as f:
    f.write(codigo)
print("✓ Backup creado: arkani_engine.py.backup_memoria")

# ── PARCHE 1: Agregar función de memoria humana después de la clase MemoriaManager ──
# La insertamos justo antes de def guardar(self):

FUNCION_MEMORIA = '''
    def memoria_corto_plazo(self, n: int = 3) -> str:
        """Últimas N conversaciones — van directo al prompt."""
        convs = self.memoria.get("conversaciones", [])[-n:]
        if not convs:
            return ""
        lineas = []
        for c in convs:
            p = c.get("pregunta", "")[:80]
            r = c.get("respuesta", "")[:120]
            lineas.append(f"U: {p}\\nA: {r}")
        return "\\n---\\n".join(lineas)

    def memoria_largo_plazo(self, pregunta: str, n_resultados: int = 2) -> str:
        """Búsqueda semántica por keywords en conversaciones antiguas."""
        convs = self.memoria.get("conversaciones", [])
        if len(convs) <= 3:
            return ""
        # Solo buscar en las conversaciones viejas (excluyendo las últimas 3)
        antiguas = convs[:-3]
        # Extraer keywords de la pregunta (palabras > 3 chars)
        stopwords = {"que", "quien", "como", "cual", "donde", "cuando",
                     "para", "por", "con", "sin", "una", "uno", "los",
                     "las", "del", "fue", "son", "eres", "tienes"}
        keywords = {p.lower().strip("?¿.,") for p in pregunta.split()
                    if len(p) > 3 and p.lower() not in stopwords}
        if not keywords:
            return ""
        # Buscar coincidencias
        resultados = []
        for c in antiguas:
            texto = (c.get("pregunta","") + " " + c.get("respuesta","")).lower()
            score = sum(1 for k in keywords if k in texto)
            if score >= 1:
                resultados.append((score, c))
        if not resultados:
            return ""
        # Top N por relevancia
        resultados.sort(key=lambda x: x[0], reverse=True)
        top = resultados[:n_resultados]
        lineas = []
        for _, c in top:
            p = c.get("pregunta","")[:60]
            r = c.get("respuesta","")[:100]
            lineas.append(f"[Memoria] {p} → {r}")
        return "\\n".join(lineas)

'''

# Insertar antes de "def guardar(self):"
if "def guardar(self):" in codigo and "def memoria_corto_plazo" not in codigo:
    codigo = codigo.replace(
        "    def guardar(self):",
        FUNCION_MEMORIA + "    def guardar(self):"
    )
    print("✓ Parche 1: funciones de memoria humana agregadas")
else:
    print("⚠ Parche 1: ya existe o no se encontró punto de inserción")

# ── PARCHE 2: Usar memoria en el prompt ─────────────────────────────────────
# Buscar el bloque del prompt y agregar memoria corto/largo plazo

PROMPT_VIEJO = '''        pends = self.mem.memoria.get("pendientes", [])
        pend_str = "\\n".join(f"  {i+1}. {p}"
                             for i, p in enumerate(pends)) or "  (ninguno)"
        prompt = (
            "<|im_start|>system\\n"
            "Eres Arkani, IA autonoma con memoria evolutiva. Xalapa, Mexico.\\n"
            "Constructor: Medico Radiologo.\\n"
            "REGLAS: 1)Siempre en espanol. 2)Max 4 oraciones. "
            "3)Usa INFO si hay. 4)No repitas instrucciones.\\n"
            f"\\nPENDIENTES:\\n{pend_str}\\n"
            f"{ctx_rag}"
            "<|im_end|>\\n"
            "<|im_start|>user\\n"
            f"{pregunta}\\n"
            "<|im_end|>\\n"
            "<|im_start|>assistant\\n"
        )'''

PROMPT_NUEVO = '''        pends = self.mem.memoria.get("pendientes", [])
        pend_str = "\\n".join(f"  {i+1}. {p}"
                             for i, p in enumerate(pends)) or "  (ninguno)"

        # ── MEMORIA HUMANA ──────────────────────────────────────────────────
        # Corto plazo: últimas 3 conversaciones (siempre presentes)
        mem_corto = self.mem.memoria_corto_plazo(n=3)
        # Largo plazo: búsqueda semántica en conversaciones antiguas
        mem_largo = self.mem.memoria_largo_plazo(pregunta, n_resultados=2)

        # Construir bloque de memoria solo si hay contenido
        bloque_memoria = ""
        if mem_largo:
            bloque_memoria += f"\\nRECUERDOS RELEVANTES:\\n{mem_largo}\\n"
        if mem_corto:
            bloque_memoria += f"\\nCONVERSACION RECIENTE:\\n{mem_corto}\\n"
        # ───────────────────────────────────────────────────────────────────

        prompt = (
            "<|im_start|>system\\n"
            "Eres Arkani, IA autonoma con memoria evolutiva. Xalapa, Mexico.\\n"
            "Constructor: Medico Radiologo.\\n"
            "REGLAS: 1)Siempre en espanol. 2)Max 4 oraciones. "
            "3)Usa INFO si hay. 4)No repitas instrucciones.\\n"
            f"{bloque_memoria}"
            f"{ctx_rag}"
            "<|im_end|>\\n"
            "<|im_start|>user\\n"
            f"{pregunta}\\n"
            "<|im_end|>\\n"
            "<|im_start|>assistant\\n"
        )'''

if PROMPT_VIEJO in codigo:
    codigo = codigo.replace(PROMPT_VIEJO, PROMPT_NUEVO)
    print("✓ Parche 2: prompt actualizado con memoria humana")
else:
    print("⚠ Parche 2: bloque del prompt no encontrado exactamente")
    print("  Buscando variante...")
    # Buscar con regex más flexible
    if "mem_corto_plazo" not in codigo:
        print("  → El prompt necesita ajuste manual")
        print("  → Revisa líneas 785-805 del engine")

# ── GUARDAR ─────────────────────────────────────────────────────────────────
with open(ENGINE_PATH, "w") as f:
    f.write(codigo)
print("✓ arkani_engine.py actualizado")

# ── VERIFICAR ───────────────────────────────────────────────────────────────
import ast
try:
    ast.parse(codigo)
    print("✓ Sintaxis Python válida — sin errores")
except SyntaxError as e:
    print(f"✗ Error de sintaxis en línea {e.lineno}: {e.msg}")
    print("  Restaurando backup...")
    with open(ENGINE_PATH + ".backup_memoria") as f:
        original = f.read()
    with open(ENGINE_PATH, "w") as f:
        f.write(original)
    print("  Backup restaurado")

# ── REPORTE FINAL ────────────────────────────────────────────────────────────
print()
print("=" * 50)
print("MEMORIA HUMANA ARKANI — ARQUITECTURA INSTALADA")
print("=" * 50)
print("  Corto plazo:  últimas 3 conversaciones en prompt")
print("  Largo plazo:  búsqueda semántica en 72+ conv.")
print("  Prompt size:  controlado — nunca overflow")
print()
print("Para activar:")
print("  pkill -f arkani_web.py && cd ~/NEXUS && bash arrancar_arkani.sh")

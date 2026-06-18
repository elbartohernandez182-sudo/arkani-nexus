#!/usr/bin/env python3
"""
patch_engine_auditoria.py
Agrega comandos auditar: y olvida: a arkani_engine.py
Ejecutar: python3 patch_engine_auditoria.py
"""

import os
import ast

ENGINE = "/home/arkani/NEXUS/NEXUS-LANG/arkani_engine.py"

with open(ENGINE, 'r') as f:
    code = f.read()

# ── 1. Agregar modos en _decidir_modo ──────────────────────────────────────
OLD_MODO = '''        if texto.startswith("autoprograma:"):       return "AGENTE"
        if texto.startswith("evoluciona:"):         return "EVOLUCION"
        if texto.startswith("aprende internet:"):   return "INTERNET"
        if texto.startswith("crea:"):               return "CREAR" '''

NEW_MODO = '''        if texto.startswith("autoprograma:"):       return "AGENTE"
        if texto.startswith("evoluciona:"):         return "EVOLUCION"
        if texto.startswith("aprende internet:"):   return "INTERNET"
        if texto.startswith("crea:"):               return "CREAR"
        if texto.startswith("auditar:"):            return "AUDITAR"
        if texto.startswith("olvida:"):             return "OLVIDA" '''

code = code.replace(OLD_MODO, NEW_MODO)

# ── 2. Agregar handlers en chat() ──────────────────────────────────────────
OLD_CHAT = '''        if modo == "CREAR":
            try:
                sys.path.insert(0, str(os.path.dirname(os.path.abspath(__file__))))
                from arkani_internet import crear_programa
                desc = pregunta[5:].strip()
                if not desc:
                    return "Usa: crea: [descripcion]  ej: crea: juego de snake en python"
                r = crear_programa(desc)
                if r.get("ok"):
                    return (f"✅ Programa creado: {r['nombre']}\\n"
                            f"   Lineas: {r['lineas']}\\n"
                            f"   Para ejecutar: python3 {r['ruta']}\\n\\n"
                            f"Preview:\\n{r['codigo'][:400]}")
                return f"Error creando programa: {r.get('error','desconocido')}"
            except Exception as ex:
                return f"Error en creacion: {ex}"'''

NEW_CHAT = '''        if modo == "CREAR":
            try:
                sys.path.insert(0, str(os.path.dirname(os.path.abspath(__file__))))
                from arkani_internet import crear_programa
                desc = pregunta[5:].strip()
                if not desc:
                    return "Usa: crea: [descripcion]  ej: crea: juego de snake en python"
                r = crear_programa(desc)
                if r.get("ok"):
                    return (f"✅ Programa creado: {r['nombre']}\\n"
                            f"   Lineas: {r['lineas']}\\n"
                            f"   Para ejecutar: python3 {r['ruta']}\\n\\n"
                            f"Preview:\\n{r['codigo'][:400]}")
                return f"Error creando programa: {r.get('error','desconocido')}"
            except Exception as ex:
                return f"Error en creacion: {ex}"

        if modo == "AUDITAR":
            return self._manejar_auditar(pregunta[8:].strip())

        if modo == "OLVIDA":
            return self._manejar_olvida(pregunta[7:].strip())'''

code = code.replace(OLD_CHAT, NEW_CHAT)

# ── 3. Agregar metodos _manejar_auditar y _manejar_olvida ──────────────────
METODOS_NUEVOS = '''
    def _manejar_auditar(self, que: str) -> str:
        """
        auditar: dataset         — ultimos 10 ejemplos del dataset fractal
        auditar: memoria         — ultimos 10 hechos aprendidos
        auditar: conversaciones  — ultimas 5 conversaciones
        auditar: archivos        — archivos en memoria_permanente/
        auditar: todo            — resumen completo
        """
        t = que.lower().strip()
        lineas = [f"🔍 AUDITORIA: {que or 'todo'}\\n"]

        # Dataset fractal
        if not t or t in ("dataset", "todo"):
            try:
                import json as _json
                ds_path = os.path.join(BASE_DIR, "arkani_fractal_dataset_v2.json")
                with open(ds_path) as f:
                    ds = _json.load(f)
                lineas.append(f"📊 Dataset fractal: {len(ds)} ejemplos")
                lineas.append("   Ultimos 5:")
                for e in ds[-5:]:
                    lineas.append(f"   [{ds.index(e)}] {e.get('instruction','')[:70]}")
            except Exception as ex:
                lineas.append(f"   Dataset: error ({ex})")

        # Memoria/hechos aprendidos
        if not t or t in ("memoria", "todo"):
            hechos = self.mem.conocimiento.get("hechos", {})
            lineas.append(f"\\n🧠 Hechos aprendidos: {len(hechos)}")
            for i, (k, v) in enumerate(list(hechos.items())[-5:]):
                lineas.append(f"   [{i}] {k[:60]}")

        # Ultimas conversaciones
        if not t or t in ("conversaciones", "todo"):
            convs = self.mem.memoria.get("conversaciones", [])
            lineas.append(f"\\n💬 Conversaciones: {len(convs)}")
            lineas.append("   Ultimas 3:")
            for c in convs[-3:]:
                lineas.append(f"   {c.get('fecha','')} — {c.get('pregunta','')[:50]}")

        # Archivos en memoria_permanente
        if not t or t in ("archivos", "todo"):
            try:
                mp = os.path.expanduser("~/NEXUS/memoria_permanente/")
                archivos = os.listdir(mp) if os.path.exists(mp) else []
                lineas.append(f"\\n📂 Memoria permanente: {len(archivos)} archivos")
                for a in archivos:
                    ruta = os.path.join(mp, a)
                    kb = os.path.getsize(ruta) // 1024
                    lineas.append(f"   {a} ({kb}KB)")
            except Exception as ex:
                lineas.append(f"   Archivos: error ({ex})")

        # Hipocampo
        if not t or t in ("hipocampo", "todo"):
            lineas.append(f"\\n🧬 Hipocampo: {self.motor.hipocampo.resumen()}")

        return "\\n".join(lineas)

    def _manejar_olvida(self, que: str) -> str:
        """
        olvida: python decoradores     — borra ese hecho especifico
        olvida: todo memoria           — limpia todos los hechos aprendidos
        olvida dataset: python         — borra ejemplos del dataset con ese tema
        olvida conversaciones          — limpia historial de conversaciones
        """
        t = que.lower().strip()

        # Olvidar todo el historial de conversaciones
        if "conversaciones" in t:
            n = len(self.mem.memoria.get("conversaciones", []))
            self.mem.memoria["conversaciones"] = []
            self.mem.guardar()
            return f"🗑️ Borradas {n} conversaciones del historial."

        # Limpiar toda la memoria de hechos
        if "todo memoria" in t or "toda memoria" in t:
            n = len(self.mem.conocimiento.get("hechos", {}))
            self.mem.conocimiento["hechos"] = {}
            self.mem.guardar()
            return f"🗑️ Borrados {n} hechos aprendidos. Memoria limpia."

        # Borrar ejemplos del dataset por tema
        if t.startswith("dataset:"):
            tema = t[8:].strip()
            try:
                import json as _json
                ds_path = os.path.join(BASE_DIR, "arkani_fractal_dataset_v2.json")
                with open(ds_path) as f:
                    ds = _json.load(f)
                antes = len(ds)
                ds = [e for e in ds
                      if tema not in e.get("instruction","").lower()
                      and tema not in e.get("output","").lower()]
                with open(ds_path, 'w') as f:
                    _json.dump(ds, f, indent=2, ensure_ascii=False)
                borrados = antes - len(ds)
                return f"🗑️ Dataset: borrados {borrados} ejemplos sobre '{tema}'. Quedan {len(ds)}."
            except Exception as ex:
                return f"Error editando dataset: {ex}"

        # Borrar un hecho especifico por keyword
        if que:
            hechos = self.mem.conocimiento.get("hechos", {})
            claves_borrar = [k for k in hechos if que.lower() in k.lower()]
            for k in claves_borrar:
                del hechos[k]
            self.mem.guardar()
            if claves_borrar:
                return (f"🗑️ Borrados {len(claves_borrar)} recuerdos sobre '{que}':\\n"
                        + "\\n".join(f"  - {k[:60]}" for k in claves_borrar))
            return f"No encontre recuerdos sobre '{que}' para borrar."

        return ("Uso:\\n"
                "  olvida: [tema]              → borra hechos sobre ese tema\\n"
                "  olvida: conversaciones      → limpia historial de chat\\n"
                "  olvida: todo memoria        → limpia todos los hechos\\n"
                "  olvida dataset: [tema]      → borra del dataset de entrenamiento")

'''

# Insertar antes de def agente(
OLD_AGENTE = "    def agente(self, objetivo: str) -> str:"
code = code.replace(OLD_AGENTE, METODOS_NUEVOS + "    def agente(self, objetivo: str) -> str:")

# ── Verificar sintaxis ─────────────────────────────────────────────────────
try:
    ast.parse(code)
    with open(ENGINE, 'w') as f:
        f.write(code)
    print("✅ Patch aplicado correctamente")
    print("   Nuevos comandos disponibles:")
    print("   auditar: dataset / memoria / conversaciones / archivos / todo")
    print("   olvida: [tema] / conversaciones / todo memoria / dataset: [tema]")
except SyntaxError as e:
    print(f"❌ Error de sintaxis en linea {e.lineno}: {e.msg}")
    print("   Archivo NO modificado")

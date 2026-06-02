#!/usr/bin/env python3
"""
NEXUS-FRACTAL VIRTUAL MACHINE v1.0
====================================
Ejecuta instrucciones compiladas del hipocampo.bin
Se integra con nexus_fractal_compiler.py y arkani_engine.py

Uso standalone:
  python3 nexus_fractal_vm.py

Uso desde arkani_engine.py:
  from nexus_fractal_vm import FractalVM
  vm = FractalVM()
  resultado = vm.ejecutar_todo()
"""

import os
import time
import struct
import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Dict, List

# ============================================
# OPERACIONES PRIMITIVAS (mismas del compiler)
# ============================================

class FractalOp(Enum):
    SUM    = 0xA0
    IF     = 0xA1
    LOOP   = 0xA3
    SPAWN  = 0xA5
    FOLD   = 0xA7
    LINK   = 0xA9
    EVOLVE = 0xF1

FRACTAL_ID = 0x7C
MAX_DEPTH  = 20
MAX_SCALE  = 20  # limitar 2^20 para no colgar la maquina

# ============================================
# INSTRUCCION EN MEMORIA
# ============================================

class Instruccion:
    def __init__(self, op: FractalOp, scale: int,
                 flags: int = 0, fold_addr: int = 0,
                 link_addr: int = 0, direccion: int = 0):
        self.op        = op
        self.scale     = scale
        self.flags     = flags
        self.fold_addr = fold_addr
        self.link_addr = link_addr
        self.direccion = direccion

    @property
    def tiene_fold(self):
        return bool(self.flags & 0x01)

    @property
    def tiene_link(self):
        return bool(self.flags & 0x02)

    @property
    def es_evolve(self):
        return bool(self.flags & 0x80)

    @property
    def fold_es_self(self):
        return self.fold_addr == 0xFFFFFFFF

    def __repr__(self):
        return (f"[Dir:{self.direccion:3d}] "
                f"op={self.op.name:<6} "
                f"scale={self.scale:<3} "
                f"fold={'self' if self.fold_es_self else self.fold_addr if self.tiene_fold else '-'} "
                f"link={self.link_addr if self.tiene_link else '-'}")


# ============================================
# CARGADOR DEL HIPOCAMPO
# ============================================

def cargar_hipocampo(path: str = None) -> List[Instruccion]:
    if path is None:
        path = os.path.expanduser("~/NEXUS/NEXUS-LANG/hipocampo.bin")

    instrucciones = []
    if not os.path.exists(path):
        print(f"[VM] hipocampo.bin no encontrado en {path}")
        return instrucciones

    try:
        with open(path, "rb") as f:
            data = f.read()

        cargadas = 0
        ignoradas = 0
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            if len(chunk) != 16:
                break
            if chunk[0] != FRACTAL_ID:
                ignoradas += 1
                continue
            op_val = chunk[1]
            op = next((o for o in FractalOp if o.value == op_val), None)
            if op is None:
                ignoradas += 1
                continue
            scale     = chunk[2]
            flags     = chunk[3]
            fold_addr = struct.unpack('<I', chunk[4:8])[0]
            link_addr = struct.unpack('<I', chunk[8:12])[0]
            inst = Instruccion(
                op=op, scale=scale, flags=flags,
                fold_addr=fold_addr, link_addr=link_addr,
                direccion=i // 16
            )
            instrucciones.append(inst)
            cargadas += 1

        print(f"[VM] Hipocampo cargado: {cargadas} instrucciones "
              f"({ignoradas} ignoradas) — {len(data)} bytes")
    except Exception as e:
        print(f"[VM] Error cargando hipocampo: {e}")

    return instrucciones


# ============================================
# CONTEXTO DE EJECUCION
# ============================================

class Contexto:
    def __init__(self):
        self.registros: Dict[str, Any] = {}
        self.pila: List[Any] = []
        self.resultado = None
        self.operaciones = 0


# ============================================
# MAQUINA VIRTUAL FRACTAL
# ============================================

class FractalVM:
    """
    Ejecuta instrucciones NEXUS-FRACTAL almacenadas en hipocampo.bin.

    Flujo:
      1. Carga hipocampo.bin
      2. Ejecuta cada instruccion segun su operacion
      3. Las instrucciones FOLD se expanden recursivamente
      4. EVOLVE genera nuevas instrucciones en memoria
      5. Reporta resultados
    """

    def __init__(self, hipocampo_path: str = None):
        self.hipocampo_path = hipocampo_path
        self.instrucciones: List[Instruccion] = []
        self.ejecuciones   = 0
        self.evoluciones   = 0
        self.nuevas_neuronas: List[Instruccion] = []
        self.inicio        = time.time()
        self._cargar()

    def _cargar(self):
        self.instrucciones = cargar_hipocampo(self.hipocampo_path)

    def _get(self, direccion: int) -> Optional[Instruccion]:
        for inst in self.instrucciones:
            if inst.direccion == direccion:
                return inst
        return None

    # ------------------------------------------
    # EJECUTORES POR OPERACION
    # ------------------------------------------

    def _exec_loop(self, inst: Instruccion, ctx: Contexto,
                   depth: int) -> List[Any]:
        iteraciones = min(2 ** inst.scale, 2 ** MAX_SCALE)
        resultados  = []

        if depth >= MAX_DEPTH:
            return list(range(min(iteraciones, 8)))

        if inst.fold_es_self and inst.tiene_fold:
            # expansion fractal: cada nivel genera la mitad
            mitad = max(1, inst.scale - 1)
            sub = Instruccion(
                op=FractalOp.LOOP, scale=mitad,
                flags=inst.flags,
                fold_addr=inst.fold_addr,
                link_addr=inst.link_addr,
                direccion=inst.direccion
            )
            izq = self._exec_loop(sub, ctx, depth + 1)
            der = self._exec_loop(sub, ctx, depth + 1)
            resultados = izq + der
        else:
            resultados = list(range(iteraciones))

        ctx.operaciones += len(resultados)
        ctx.resultado    = resultados
        return resultados

    def _exec_sum(self, inst: Instruccion, ctx: Contexto,
                  depth: int) -> int:
        n      = min(2 ** inst.scale, 2 ** MAX_SCALE)
        total  = sum(range(n))
        ctx.operaciones += n
        ctx.resultado    = total
        return total

    def _exec_if(self, inst: Instruccion, ctx: Contexto,
                 depth: int) -> bool:
        condicion = inst.scale > 15
        ctx.operaciones += 1
        ctx.resultado    = condicion
        return condicion

    def _exec_spawn(self, inst: Instruccion, ctx: Contexto,
                    depth: int) -> int:
        nueva_scale = max(1, inst.scale - 1)
        nueva = Instruccion(
            op=FractalOp.LOOP, scale=nueva_scale,
            flags=0x01, fold_addr=0xFFFFFFFF,
            link_addr=0,
            direccion=len(self.instrucciones) + len(self.nuevas_neuronas)
        )
        self.nuevas_neuronas.append(nueva)
        ctx.operaciones += 1
        ctx.resultado    = nueva.direccion
        print(f"   🌱 SPAWN: nueva neurona Dir {nueva.direccion} "
              f"LOOP scale:{nueva_scale}")
        return nueva.direccion

    def _exec_fold(self, inst: Instruccion, ctx: Contexto,
                   depth: int) -> Any:
        n = min(2 ** inst.scale, 2 ** MAX_SCALE)

        def plegar(datos, escala):
            if len(datos) <= 1 or escala <= 0:
                return sum(datos) if datos else 0
            mid   = len(datos) // 2
            izq   = plegar(datos[:mid], escala - 1)
            der   = plegar(datos[mid:], escala - 1)
            return izq + der

        datos     = list(range(n))
        resultado = plegar(datos, inst.scale)
        ctx.operaciones += n
        ctx.resultado    = resultado
        return resultado

    def _exec_link(self, inst: Instruccion, ctx: Contexto,
                   depth: int) -> Any:
        if not inst.tiene_link:
            return None
        destino = self._get(inst.link_addr)
        if destino is None:
            print(f"   ⚠️  LINK: Dir {inst.link_addr} no existe")
            return None
        return self._ejecutar_instruccion(destino, depth + 1)

    def _exec_evolve(self, inst: Instruccion, ctx: Contexto,
                     depth: int) -> str:
        total_actual = len(self.instrucciones) + len(self.nuevas_neuronas)
        nueva_scale  = min(inst.scale + 1, 31)

        nueva = Instruccion(
            op=FractalOp.LOOP, scale=nueva_scale,
            flags=0x01, fold_addr=0xFFFFFFFF,
            link_addr=0,
            direccion=total_actual
        )
        self.nuevas_neuronas.append(nueva)
        self.evoluciones += 1

        resultado = f"EVOLVED_{self.evoluciones}"
        ctx.operaciones += 1
        ctx.resultado    = resultado

        print(f"   🧠 EVOLVE activado — nueva neurona Dir {total_actual} "
              f"LOOP scale:{nueva_scale}")
        return resultado

    # ------------------------------------------
    # EJECUTOR PRINCIPAL POR INSTRUCCION
    # ------------------------------------------

    def _ejecutar_instruccion(self, inst: Instruccion,
                               depth: int = 0) -> Any:
        if depth > MAX_DEPTH:
            return None

        ctx = Contexto()
        self.ejecuciones += 1

        try:
            if inst.op == FractalOp.LOOP:
                return self._exec_loop(inst, ctx, depth)
            elif inst.op == FractalOp.SUM:
                return self._exec_sum(inst, ctx, depth)
            elif inst.op == FractalOp.IF:
                return self._exec_if(inst, ctx, depth)
            elif inst.op == FractalOp.SPAWN:
                return self._exec_spawn(inst, ctx, depth)
            elif inst.op == FractalOp.FOLD:
                return self._exec_fold(inst, ctx, depth)
            elif inst.op == FractalOp.LINK:
                return self._exec_link(inst, ctx, depth)
            elif inst.op == FractalOp.EVOLVE:
                return self._exec_evolve(inst, ctx, depth)
            else:
                print(f"   ⚠️  Operacion desconocida: {inst.op}")
                return None
        except Exception as e:
            print(f"   ❌ Error en Dir {inst.direccion}: {e}")
            return None

    # ------------------------------------------
    # EJECUCION COMPLETA
    # ------------------------------------------

    def ejecutar_todo(self) -> Dict:
        print()
        print("=" * 55)
        print("🚀 NEXUS-FRACTAL VM v1.0 — EJECUTANDO")
        print(f"   Instrucciones en hipocampo: {len(self.instrucciones)}")
        print("=" * 55)

        if not self.instrucciones:
            print("[VM] No hay instrucciones para ejecutar.")
            return {"error": "hipocampo vacio"}

        t0      = time.time()
        results = {}

        for inst in self.instrucciones:
            print(f"\n▶  {inst}")
            resultado = self._ejecutar_instruccion(inst, depth=0)
            # resumir si es lista grande
            if isinstance(resultado, list) and len(resultado) > 6:
                resumen = f"[{resultado[0]}, {resultado[1]}, ... {resultado[-1]}] ({len(resultado)} items)"
            else:
                resumen = str(resultado)
            print(f"   → resultado: {resumen}")
            results[inst.direccion] = resultado

        elapsed = time.time() - t0

        # integrar nuevas neuronas generadas
        if self.nuevas_neuronas:
            self.instrucciones.extend(self.nuevas_neuronas)
            print(f"\n🌱 {len(self.nuevas_neuronas)} nuevas neuronas "
                  f"agregadas al hipocampo en memoria")

        print()
        print("=" * 55)
        print("✅ EJECUCION COMPLETA")
        print(f"   Instrucciones ejecutadas : {len(results)}")
        print(f"   Total operaciones        : "
              f"{sum(getattr(r,'operaciones',0) for r in [Contexto()])}")
        print(f"   Evoluciones              : {self.evoluciones}")
        print(f"   Nuevas neuronas          : {len(self.nuevas_neuronas)}")
        print(f"   Tiempo                   : {elapsed:.4f}s")
        print(f"   Neuronas totales         : {len(self.instrucciones)}")
        print("=" * 55)

        return {
            "ejecutadas":    len(results),
            "evoluciones":   self.evoluciones,
            "nuevas":        len(self.nuevas_neuronas),
            "tiempo_s":      round(elapsed, 4),
            "neuronas_total": len(self.instrucciones),
            "results":       {k: str(v)[:80] for k, v in results.items()},
        }

    def estado(self) -> Dict:
        """Resumen rapido del estado de la VM."""
        return {
            "neuronas":    len(self.instrucciones),
            "bytes":       len(self.instrucciones) * 16,
            "ejecuciones": self.ejecuciones,
            "evoluciones": self.evoluciones,
            "uptime_s":    round(time.time() - self.inicio, 2),
            "status":      "ONLINE",
        }

    def ejecutar_una(self, direccion: int) -> Any:
        """Ejecuta una sola instruccion por direccion."""
        inst = self._get(direccion)
        if inst is None:
            print(f"[VM] Dir {direccion} no existe")
            return None
        print(f"[VM] Ejecutando {inst}")
        return self._ejecutar_instruccion(inst, depth=0)

    def listar(self):
        """Muestra todas las instrucciones cargadas."""
        print(f"\n[VM] Hipocampo — {len(self.instrucciones)} instrucciones:")
        for inst in self.instrucciones:
            print(f"  {inst}")
        print()


# ============================================
# INTEGRACION CON ARKANI_ENGINE
# ============================================

def ejecutar_desde_engine(descripcion: str = "") -> Dict:
    """
    Funcion de conveniencia para llamar desde arkani_engine.py:

      from nexus_fractal_vm import ejecutar_desde_engine
      resultado = ejecutar_desde_engine("procesar consulta medica")
    """
    vm = FractalVM()
    if descripcion:
        print(f"[VM] Contexto: {descripcion}")
    return vm.ejecutar_todo()


# ============================================
# PRUEBA STANDALONE
# ============================================

if __name__ == "__main__":
    print("🧬 NEXUS-FRACTAL VM v1.0")
    print(f"   Clave del proyecto: Arkani1979")
    print(f"   Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    vm = FractalVM()

    print("\n📋 Instrucciones cargadas:")
    vm.listar()

    print("🔄 Iniciando ejecucion...\n")
    resultado = vm.ejecutar_todo()

    print("\n📊 Estado final de la VM:")
    estado = vm.estado()
    for k, v in estado.items():
        print(f"   {k}: {v}")

    print()
    print("✅ VM lista para integrarse con arkani_engine.py")
    print("   from nexus_fractal_vm import FractalVM")
    print("   vm = FractalVM()")
    print("   vm.ejecutar_todo()")

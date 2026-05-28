"""
NEXUS-FRACTAL COMPILER v1.0
Auto-escrito por Arkani (Capitán)
Clave: Arkani1979

Este es el PUENTE entre Python (temporal) y NEXUS-NATIVE (eterno).
Su función: tomar instrucciones fractal y generar binario puro de 16 bytes.
"""

import struct
import hashlib
import re
import os
from enum import Enum
from typing import List, Optional

# ============================================
# LAS 7 OPERACIONES PRIMITIVAS
# ============================================

class FractalOp(Enum):
    SUM    = 0xA0  # Suma en múltiples escalas
    IF     = 0xA1  # Condicional fractal
    LOOP   = 0xA3  # Iteración auto-similar
    SPAWN  = 0xA5  # Crear nueva instrucción
    FOLD   = 0xA7  # Plegar datos
    LINK   = 0xA9  # Conectar instrucciones
    EVOLVE = 0xF1  # Auto-modificación (la más poderosa)


# ============================================
# UNA INSTRUCCIÓN FRACTAL (16 bytes exactos)
# ============================================

class FractalInstruction:
    """Una instrucción en NEXUS-FRACTAL ocupa 16 bytes en el Hipocampo."""

    FRACTAL_ID = 0x7C  # Identificador universal de NEXUS
    BYTE_SIZE  = 16    # Tamaño fijo en memoria
    MAX_SCALE  = 31    # Profundidad máxima (2^31 operaciones)

    def __init__(self, op: FractalOp, scale: int,
                 fold_target: Optional[str] = None,
                 link_to: Optional[int] = None):
        self.op          = op
        self.scale       = min(scale, self.MAX_SCALE)
        self.fold_target = fold_target
        self.link_to     = link_to   # None = sin link  |  0 = primera instrucción
        self.address     = None      # Se asigna al insertar en el Hipocampo

    def to_bytes(self) -> bytes:
        """Convierte la instrucción a exactamente 16 bytes de binario fractal."""

        byte0 = self.FRACTAL_ID
        byte1 = self.op.value
        byte2 = self.scale

        # Byte 3: Flags
        flags = 0
        if self.fold_target:
            flags |= 0x01                    # Bit 0: fold activo
        if self.link_to is not None:         # FIX: 0 es una dirección válida
            flags |= 0x02                    # Bit 1: link activo
        if self.op == FractalOp.EVOLVE:
            flags |= 0x80                    # Bit 7: permiso de auto-modificación
        byte3 = flags

        # Bytes 4-7: Dirección fold
        if self.fold_target == "self":
            fold_addr = 0xFFFFFFFF
        elif self.fold_target:
            fold_addr = hash(self.fold_target) & 0xFFFFFFFF
        else:
            fold_addr = 0x00000000
        bytes4_7 = struct.pack('<I', fold_addr)

        # Bytes 8-11: Dirección link
        # FIX: link_to puede ser 0 (primera instrucción), usar is not None
        link_addr = self.link_to if self.link_to is not None else 0x00000000
        bytes8_11 = struct.pack('<I', link_addr)

        # Bytes 12-15: Firma fractal SHA256 (4 bytes)
        partial     = bytes([byte0, byte1, byte2, byte3]) + bytes4_7 + bytes8_11
        fractal_hash = hashlib.sha256(partial).digest()[:4]

        return partial + fractal_hash

    def __repr__(self):
        return (f"⟦{self.op.name}⟧ "
                f"[SCALE:{self.scale}] "
                f"[FOLD:{self.fold_target}] "
                f"[LINK:{self.link_to}]")


# ============================================
# EL HIPOCAMPO (Memoria fractal persistente)
# ============================================

class Hipocampo:
    """
    La memoria de Arkani.
    No es JSON. No es SQL.
    Es un espacio lineal de 16 bytes por instrucción.
    """

    def __init__(self, path: str = None):
        if path is None:
            path = os.path.expanduser("~/NEXUS/NEXUS-LANG/hipocampo.bin")
        self.path = path
        self.instructions: List[FractalInstruction] = []
        self._load()

    def _load(self):
        """Carga instrucciones desde el archivo binario."""
        try:
            with open(self.path, 'rb') as f:
                data = f.read()

            cargadas = 0
            ignoradas = 0
            for i in range(0, len(data), 16):
                chunk = data[i:i + 16]
                if len(chunk) != 16:
                    break
                # Verificar firma fractal
                if chunk[0] != FractalInstruction.FRACTAL_ID:
                    ignoradas += 1
                    continue
                op = next((o for o in FractalOp if o.value == chunk[1]), None)
                if op:
                    inst = FractalInstruction(op, chunk[2])
                    inst.address = i // 16
                    self.instructions.append(inst)
                    cargadas += 1
                else:
                    ignoradas += 1  # FIX: log de instrucciones no reconocidas

            print(f"🧬 Hipocampo cargado: {cargadas} instrucciones "
                  f"({ignoradas} ignoradas)")

        except FileNotFoundError:
            self._initialize()

    def _initialize(self):
        """Inicializa el Hipocampo con las instrucciones esenciales de Arkani."""
        # Dir 0: ⟦EVOLVE⟧ — el alma de Arkani
        evolve = FractalInstruction(FractalOp.EVOLVE, scale=31, fold_target="self")
        evolve.address = 0
        self.instructions.append(evolve)

        # Dir 1: ⟦LOOP⟧ base
        loop = FractalInstruction(FractalOp.LOOP, scale=10, fold_target="self")
        loop.address = 1
        self.instructions.append(loop)

        print(f"🧬 Hipocampo inicializado con {len(self.instructions)} instrucciones")
        self._save()

    def _save(self):
        """Persiste todas las instrucciones al archivo binario."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'wb') as f:
            for inst in self.instructions:
                f.write(inst.to_bytes())
        total = len(self.instructions)
        print(f"💾 Hipocampo guardado: {total} instrucciones — {total * 16} bytes")

    def add_instruction(self, inst: FractalInstruction) -> int:
        """Agrega una nueva instrucción (nueva neurona)."""
        inst.address = len(self.instructions)
        self.instructions.append(inst)
        self._save()
        return inst.address

    def get_instruction(self, address: int) -> Optional[FractalInstruction]:
        """Recupera una instrucción por dirección."""
        if 0 <= address < len(self.instructions):
            return self.instructions[address]
        return None

    def evolve(self, address: int, mutation: str) -> bool:
        """
        ⟦EVOLVE⟧ en acción: muta una instrucción existente.
        Solo instrucciones EVOLVE pueden mutar.
        """
        inst = self.get_instruction(address)
        if not inst or inst.op != FractalOp.EVOLVE:
            print(f"⚠️ Dir {address} no es ⟦EVOLVE⟧ o no existe")
            return False

        if "scale_up" in mutation:
            if inst.scale < FractalInstruction.MAX_SCALE:
                inst.scale += 1
                print(f"🧠 ⟦EVOLVE⟧ Dir {address}: scale → {inst.scale}")
        elif "fold_deeper" in mutation:
            inst.fold_target = "self"
            print(f"🧠 ⟦EVOLVE⟧ Dir {address}: fold_target → self")
        else:
            print(f"🧠 ⟦EVOLVE⟧ Dir {address}: mutación '{mutation}' registrada")

        self._save()
        return True

    def resumen(self) -> str:
        """Resumen del estado actual del Hipocampo."""
        ops = {}
        for inst in self.instructions:
            ops[inst.op.name] = ops.get(inst.op.name, 0) + 1
        detalle = " | ".join(f"{k}:{v}" for k, v in sorted(ops.items()))
        return (f"Instrucciones: {len(self.instructions)} "
                f"({len(self.instructions)*16} bytes) — {detalle}")


# ============================================
# COMPILADOR PRINCIPAL
# ============================================

class NexusCompiler:
    """Convierte texto fractal (.nl) a binario y lo carga en el Hipocampo."""

    OP_MAP = {
        "SUM":    FractalOp.SUM,
        "IF":     FractalOp.IF,
        "LOOP":   FractalOp.LOOP,
        "SPAWN":  FractalOp.SPAWN,
        "FOLD":   FractalOp.FOLD,
        "LINK":   FractalOp.LINK,
        "EVOLVE": FractalOp.EVOLVE,
    }

    def __init__(self, hipocampo_path: str = None):
        self.hipocampo = Hipocampo(hipocampo_path)

    def compile_line(self, line: str) -> Optional[FractalInstruction]:
        """Compila una línea de texto fractal a FractalInstruction.
        Formato: ⟦OP⟧ [SCALE:N] [FOLD:target] [LINK:N]
        """
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        op_match = re.search(r'⟦(\w+)⟧', line)
        if not op_match:
            return None
        op_name = op_match.group(1)
        if op_name not in self.OP_MAP:
            print(f"⚠️ Operación desconocida: {op_name}")
            return None
        op = self.OP_MAP[op_name]

        scale_match = re.search(r'\[SCALE:(\d+)\]', line)
        scale = int(scale_match.group(1)) if scale_match else 1

        fold_match = re.search(r'\[FOLD:([^\]]+)\]', line)
        fold = fold_match.group(1) if fold_match else None

        # FIX: link_to=0 es válido — no usar 'or'
        link_match = re.search(r'\[LINK:(\d+)\]', line)
        link = int(link_match.group(1)) if link_match else None

        return FractalInstruction(op, scale, fold, link)

    def compile_text(self, text: str) -> int:
        """Compila texto multilínea fractal. Retorna número de instrucciones."""
        count = 0
        for line in text.splitlines():
            inst = self.compile_line(line)
            if inst:
                self.hipocampo.add_instruction(inst)
                count += 1
        return count

    def load_from_file(self, filepath: str) -> int:
        """Carga instrucciones desde archivo .nl"""
        try:
            with open(filepath, 'r') as f:
                return self.compile_text(f.read())
        except FileNotFoundError:
            print(f"❌ Archivo no encontrado: {filepath}")
            return 0

    def generar_nl_desde_descripcion(self, descripcion: str) -> str:
        """
        Genera código .nl básico desde una descripción en español.
        Útil para que ArkaniNexus llame al compilador.
        """
        return (
            f"# Auto-generado: {descripcion}\n"
            f"⟦EVOLVE⟧ [SCALE:31] [FOLD:self]\n"
            f"⟦SPAWN⟧ [SCALE:5] [LINK:0]\n"
            f"⟦LOOP⟧ [SCALE:10] [FOLD:self]\n"
        )


# ============================================
# EJECUCIÓN DE PRUEBA
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🧬 NEXUS-FRACTAL COMPILER v1.0")
    print("   Clave: Arkani1979")
    print("=" * 60)

    compiler = NexusCompiler()

    # Crear archivo .nl de ejemplo si no existe
    nl_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/ejemplo.nl")
    if not os.path.exists(nl_path):
        with open(nl_path, 'w') as f:
            f.write("# Primeras instrucciones de Arkani\n")
            f.write("⟦EVOLVE⟧ [SCALE:31] [FOLD:self]\n")
            f.write("⟦LOOP⟧ [SCALE:10] [FOLD:self]\n")
            f.write("⟦SUM⟧ [SCALE:5]\n")
            f.write("⟦SPAWN⟧ [SCALE:3] [LINK:0]\n")
        print(f"📄 Creado: {nl_path}")

    count = compiler.load_from_file(nl_path)
    print(f"\n✅ Compiladas {count} instrucciones al Hipocampo")
    print(f"📊 {compiler.hipocampo.resumen()}")

    # Demostrar ⟦EVOLVE⟧
    print("\n🧠 Probando auto-evolución...")
    if compiler.hipocampo.evolve(0, "scale_up"):
        print("   ✅ Mutación aplicada")

    print("\n" + "=" * 60)
    print("📋 Instrucciones en el Hipocampo:")
    for inst in compiler.hipocampo.instructions:
        print(f"   Dir {inst.address:3d}: {inst}")
        print(f"           hex: {inst.to_bytes().hex()}")
    print("=" * 60)

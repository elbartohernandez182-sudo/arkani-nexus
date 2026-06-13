"""
tokenizer.py — Tokenizador BPE Fractal ARKANI
==============================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Convierte texto a tokens numéricos y viceversa.
Incluye tokens especiales para las 7 operaciones fractales.

USO:
    from tokenizer import FractalTokenizer
    tok = FractalTokenizer()
    tok.entrenar(["hola mundo", "SPAWN(x) FOLD(y)"])
    ids = tok.encode("hola SPAWN mundo")
    texto = tok.decode(ids)
"""

import re
import json
import os
from pathlib import Path
from collections import Counter
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# TOKENS ESPECIALES FRACTALES
# Estos tokens tienen IDs reservados — nunca se sobreescriben
# ─────────────────────────────────────────────────────────────────────────────
TOKENS_ESPECIALES = {
    "<|PAD|>":    0,   # relleno para batches
    "<|BOS|>":    1,   # inicio de secuencia
    "<|EOS|>":    2,   # fin de secuencia
    "<|UNK|>":    3,   # token desconocido
    "<SUM>":      4,   # operación SUM
    "<IF>":       5,   # operación IF
    "<LOOP>":     6,   # operación LOOP
    "<SPAWN>":    7,   # operación SPAWN
    "<FOLD>":     8,   # operación FOLD
    "<LINK>":     9,   # operación LINK
    "<EVOLVE>":   10,  # operación EVOLVE
    "<|SEP|>":    11,  # separador
    "<|SYS|>":    12,  # inicio system prompt
    "<|USER|>":   13,  # inicio turno usuario
    "<|ASST|>":   14,  # inicio turno asistente
}

ID_PAD  = TOKENS_ESPECIALES["<|PAD|>"]
ID_BOS  = TOKENS_ESPECIALES["<|BOS|>"]
ID_EOS  = TOKENS_ESPECIALES["<|EOS|>"]
ID_UNK  = TOKENS_ESPECIALES["<|UNK|>"]

# IDs de las 7 operaciones — el modelo aprende a generarlos nativamente
IDS_FRACTALES = {
    op: TOKENS_ESPECIALES[f"<{op}>"]
    for op in ["SUM", "IF", "LOOP", "SPAWN", "FOLD", "LINK", "EVOLVE"]
}


# ─────────────────────────────────────────────────────────────────────────────
# TOKENIZADOR BPE FRACTAL
# ─────────────────────────────────────────────────────────────────────────────
class FractalTokenizer:
    """
    Tokenizador BPE (Byte Pair Encoding) con soporte nativo
    para las 7 operaciones fractales de ARKANI.

    BPE aprende fusiones óptimas del corpus:
      "hola" → ["h","o","l","a"] → ["ho","la"] → ["hola"]
    """

    def __init__(self, vocab_size: int = 8000):
        self.vocab_size    = vocab_size
        self.vocab         = {}      # token_str → id
        self.vocab_inverso = {}      # id → token_str
        self.merges        = {}      # (par) → token_fusionado
        self.entrenado     = False

        # Inicializar con tokens especiales
        self._init_tokens_especiales()

    def _init_tokens_especiales(self):
        """Reserva los primeros IDs para tokens especiales fractales."""
        for token, idx in TOKENS_ESPECIALES.items():
            self.vocab[token]         = idx
            self.vocab_inverso[idx]   = token

    # ── Entrenamiento BPE ────────────────────────────────────────────────────

    def entrenar(self, corpus: list[str], verbose: bool = True) -> None:
        """
        Entrena el tokenizador BPE sobre el corpus.

        Args:
            corpus: lista de textos de entrenamiento
            verbose: mostrar progreso
        """
        if verbose:
            print(f"Entrenando tokenizador BPE...")
            print(f"  Corpus: {len(corpus)} textos")
            print(f"  Vocab objetivo: {self.vocab_size} tokens")

        # Paso 1: Vocabulario inicial — caracteres únicos del corpus
        chars = set()
        for texto in corpus:
            chars.update(texto)

        # Agregar caracteres al vocab (después de los tokens especiales)
        id_actual = max(self.vocab.values()) + 1
        for char in sorted(chars):
            if char not in self.vocab:
                self.vocab[char]              = id_actual
                self.vocab_inverso[id_actual] = char
                id_actual += 1

        if verbose:
            print(f"  Caracteres base: {len(chars)}")

        # Paso 2: Preparar corpus como secuencias de caracteres
        # Cada palabra termina con </w> para marcar límites
        vocab_palabras = Counter()
        for texto in corpus:
            palabras = texto.split()
            for palabra in palabras:
                # Preservar tokens fractales como unidades atómicas
                if any(op in palabra for op in ["SUM", "IF", "LOOP", "SPAWN", "FOLD", "LINK", "EVOLVE"]):
                    vocab_palabras[palabra + "</w>"] += 1
                else:
                    secuencia = " ".join(list(palabra)) + " </w>"
                    vocab_palabras[secuencia] += 1

        # Paso 3: Aprender fusiones BPE
        n_fusiones = self.vocab_size - id_actual
        if verbose:
            print(f"  Aprendiendo {n_fusiones} fusiones BPE...")

        for i in range(max(0, n_fusiones)):
            pares = self._contar_pares(vocab_palabras)
            if not pares:
                break

            # Fusionar el par más frecuente
            mejor_par = max(pares, key=pares.get)
            nuevo_token = "".join(mejor_par)

            self.merges[mejor_par] = nuevo_token

            # Agregar al vocabulario
            if nuevo_token not in self.vocab:
                self.vocab[nuevo_token]       = id_actual
                self.vocab_inverso[id_actual] = nuevo_token
                id_actual += 1

            # Aplicar fusión al corpus
            vocab_palabras = self._aplicar_fusion(mejor_par, vocab_palabras)

            if verbose and i % 500 == 0 and i > 0:
                print(f"  Fusión {i}/{n_fusiones}: '{mejor_par[0]}' + '{mejor_par[1]}' → '{nuevo_token}'")

        self.entrenado = True
        if verbose:
            print(f"  ✓ Vocabulario final: {len(self.vocab)} tokens")

    def _contar_pares(self, vocab_palabras: dict) -> Counter:
        """Cuenta frecuencia de cada par de símbolos adyacentes."""
        pares = Counter()
        for palabra, freq in vocab_palabras.items():
            simbolos = palabra.split()
            for i in range(len(simbolos) - 1):
                pares[(simbolos[i], simbolos[i+1])] += freq
        return pares

    def _aplicar_fusion(self, par: tuple, vocab_palabras: dict) -> dict:
        """Aplica una fusión BPE a todo el vocabulario de palabras."""
        nuevo_vocab = {}
        patron = re.compile(
            r'(?<!\S)' + re.escape(' '.join(par)) + r'(?!\S)'
        )
        for palabra, freq in vocab_palabras.items():
            nueva_palabra = patron.sub(''.join(par), palabra)
            nuevo_vocab[nueva_palabra] = freq
        return nuevo_vocab

    # ── Encoding ─────────────────────────────────────────────────────────────

    def encode(
        self,
        texto: str,
        agregar_bos: bool = True,
        agregar_eos: bool = True,
        max_length: int = None,
    ) -> list[int]:
        """
        Convierte texto a lista de IDs.

        Args:
            texto: texto a tokenizar
            agregar_bos: agregar token de inicio
            agregar_eos: agregar token de fin
            max_length: truncar si excede este largo

        Returns:
            lista de enteros (IDs de tokens)
        """
        if not self.entrenado:
            # Tokenización de emergencia por caracteres
            return self._encode_caracteres(texto, agregar_bos, agregar_eos)

        ids = []
        if agregar_bos:
            ids.append(ID_BOS)

        # Tokenizar palabra por palabra
        palabras = texto.split()
        for i, palabra in enumerate(palabras):
            # Detectar tokens fractales especiales
            token_fractal = self._detectar_token_fractal(palabra)
            if token_fractal:
                ids.append(TOKENS_ESPECIALES[token_fractal])
                continue

            # BPE normal
            ids.extend(self._bpe_encode_palabra(palabra, es_ultima=(i == len(palabras)-1)))

        if agregar_eos:
            ids.append(ID_EOS)

        # Truncar si necesario
        if max_length and len(ids) > max_length:
            ids = ids[:max_length-1] + [ID_EOS]

        return ids

    def _detectar_token_fractal(self, palabra: str) -> Optional[str]:
        """Detecta si una palabra es una operación fractal."""
        palabra_limpia = palabra.strip("(),: ")
        for op in ["SUM", "IF", "LOOP", "SPAWN", "FOLD", "LINK", "EVOLVE"]:
            if palabra_limpia == op or palabra_limpia == f"<{op}>":
                return f"<{op}>"
        return None

    def _bpe_encode_palabra(self, palabra: str, es_ultima: bool = False) -> list[int]:
        """Aplica BPE a una sola palabra."""
        if not palabra:
            return []

        # Iniciar con caracteres individuales
        simbolos = list(palabra)
        if es_ultima:
            simbolos.append("</w>")
        else:
            simbolos[-1] = simbolos[-1] + "</w>"

        # Aplicar fusiones aprendidas
        cambio = True
        while cambio and len(simbolos) > 1:
            cambio = False
            nuevo = []
            i = 0
            while i < len(simbolos) - 1:
                par = (simbolos[i], simbolos[i+1])
                if par in self.merges:
                    nuevo.append(self.merges[par])
                    i += 2
                    cambio = True
                else:
                    nuevo.append(simbolos[i])
                    i += 1
            if i < len(simbolos):
                nuevo.append(simbolos[i])
            simbolos = nuevo

        # Convertir símbolos a IDs
        ids = []
        for s in simbolos:
            ids.append(self.vocab.get(s, ID_UNK))
        return ids

    def _encode_caracteres(self, texto: str, agregar_bos: bool, agregar_eos: bool) -> list[int]:
        """Tokenización de emergencia — un ID por carácter."""
        ids = [ID_BOS] if agregar_bos else []
        for char in texto:
            ids.append(self.vocab.get(char, ID_UNK))
        if agregar_eos:
            ids.append(ID_EOS)
        return ids

    # ── Decoding ─────────────────────────────────────────────────────────────

    def decode(self, ids: list[int], limpiar: bool = True) -> str:
        """
        Convierte lista de IDs a texto.

        Args:
            ids: lista de enteros
            limpiar: eliminar tokens especiales de control

        Returns:
            texto decodificado
        """
        tokens = []
        for id_ in ids:
            token = self.vocab_inverso.get(id_, "<|UNK|>")
            # Saltar tokens de control si limpiar=True
            if limpiar and token in ("<|BOS|>", "<|EOS|>", "<|PAD|>"):
                continue
            tokens.append(token)

        # Reconstruir texto
        texto = "".join(tokens)

        # Limpiar marcadores BPE
        texto = texto.replace("</w>", " ")
        texto = texto.replace("  ", " ").strip()

        return texto

    # ── Batch encoding ────────────────────────────────────────────────────────

    def encode_batch(
        self,
        textos: list[str],
        max_length: int = 512,
        padding: bool = True,
    ) -> tuple[list[list[int]], list[list[int]]]:
        """
        Tokeniza un batch de textos con padding.

        Returns:
            (input_ids, attention_mask)
        """
        batch_ids = [
            self.encode(t, max_length=max_length)
            for t in textos
        ]

        if not padding:
            masks = [[1] * len(ids) for ids in batch_ids]
            return batch_ids, masks

        # Padding al largo máximo del batch
        largo_max = max(len(ids) for ids in batch_ids)
        input_ids = []
        masks     = []

        for ids in batch_ids:
            n_pad = largo_max - len(ids)
            input_ids.append(ids + [ID_PAD] * n_pad)
            masks.append([1] * len(ids) + [0] * n_pad)

        return input_ids, masks

    # ── Estadísticas ──────────────────────────────────────────────────────────

    def estadisticas(self, texto: str) -> dict:
        """Muestra estadísticas de tokenización de un texto."""
        ids     = self.encode(texto)
        tokens  = [self.vocab_inverso.get(i, "?") for i in ids]
        ops     = [t for t in tokens if t in TOKENS_ESPECIALES and
                   any(op in t for op in ["SUM","IF","LOOP","SPAWN","FOLD","LINK","EVOLVE"])]
        return {
            "texto_original":  texto,
            "n_chars":         len(texto),
            "n_tokens":        len(ids),
            "ratio_compresion": round(len(texto) / max(len(ids), 1), 2),
            "tokens_fractales": ops,
            "ids":             ids[:20],  # primeros 20
        }

    def cobertura_fractal(self, textos: list[str]) -> dict:
        """Analiza cobertura de operaciones fractales en un corpus."""
        ops = {op: 0 for op in ["SUM","IF","LOOP","SPAWN","FOLD","LINK","EVOLVE"]}
        total_tokens = 0
        for texto in textos:
            ids = self.encode(texto)
            total_tokens += len(ids)
            for op, id_op in IDS_FRACTALES.items():
                ops[op] += ids.count(id_op)
        return {
            "total_tokens":    total_tokens,
            "ops_por_token":   {op: round(c/max(total_tokens,1)*100, 2) for op, c in ops.items()},
            "ops_totales":     ops,
        }

    # ── Persistencia ─────────────────────────────────────────────────────────

    def guardar(self, directorio: str = "./fractal_tokenizer"):
        """Guarda el tokenizador entrenado en disco."""
        Path(directorio).mkdir(parents=True, exist_ok=True)

        datos = {
            "vocab_size":  self.vocab_size,
            "vocab":       self.vocab,
            "merges":      {f"{k[0]}|||{k[1]}": v for k, v in self.merges.items()},
            "entrenado":   self.entrenado,
            "version":     "1.0",
            "protocolo":   "Wardenclyffe",
        }

        ruta = os.path.join(directorio, "tokenizer.json")
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)

        print(f"✓ Tokenizador guardado en: {ruta}")
        print(f"  Vocabulario: {len(self.vocab)} tokens")
        print(f"  Fusiones BPE: {len(self.merges)}")

    @classmethod
    def cargar(cls, directorio: str = "./fractal_tokenizer") -> "FractalTokenizer":
        """Carga un tokenizador previamente entrenado."""
        ruta = os.path.join(directorio, "tokenizer.json")

        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)

        tok = cls(vocab_size=datos["vocab_size"])
        tok.vocab = {k: int(v) for k, v in datos["vocab"].items()}
        tok.vocab_inverso = {int(v): k for k, v in tok.vocab.items()}
        tok.merges = {
            tuple(k.split("|||")): v
            for k, v in datos["merges"].items()
        }
        tok.entrenado = datos["entrenado"]

        print(f"✓ Tokenizador cargado desde: {ruta}")
        print(f"  Vocabulario: {len(tok.vocab)} tokens")
        return tok


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo del tokenizador fractal
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — Tokenizador BPE Fractal")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    # Corpus de entrenamiento fractal
    corpus = [
        "Soy ARKANI, asistente fractal basado en el Protocolo Wardenclyffe",
        "SPAWN(perspectiva) FOLD(sintesis) LINK(conceptos) EVOLVE(error)",
        "SUM(A, B) integra conceptos preservando ambos elementos",
        "IF(condicion, entonces, sino) bifurca el flujo de razonamiento",
        "LOOP(n, operacion) itera refinando el estado en cada paso",
        "EVOLVE detecta errores y aplica correcciones automaticamente",
        "el motor fractal corre en Python puro sin dependencias externas",
        "tokenizador embeddings attention feedforward inferencia servidor",
        "arquitectura transformer con operaciones fractales integradas",
        "autoprogramacion fractal reescribir motor de inferencia propio",
        "Protocolo Wardenclyffe inteligencia distribuida sin GPU requerida",
        "FractalLM reemplaza Ollama con motor Python NumPy completamente",
        "cada token generado pasa por SPAWN FOLD LINK antes de salir",
        "memoria hipocampo corto plazo largo plazo conversaciones previas",
        "fine-tuning LoRA adaptadores ligeros entrenamiento CPU viable",
    ] * 10  # repetir para que BPE aprenda mejor

    # Entrenar tokenizador
    tok = FractalTokenizer(vocab_size=500)
    tok.entrenar(corpus, verbose=True)

    print("\n--- PRUEBAS DE ENCODING ---")

    # Test 1: texto simple
    texto1 = "hola quien eres"
    ids1 = tok.encode(texto1)
    dec1 = tok.decode(ids1)
    print(f"\nTexto:    '{texto1}'")
    print(f"IDs:      {ids1}")
    print(f"Decoded:  '{dec1}'")

    # Test 2: con operaciones fractales
    texto2 = "SPAWN analiza FOLD sintetiza EVOLVE corrige"
    ids2 = tok.encode(texto2)
    dec2 = tok.decode(ids2)
    print(f"\nTexto:    '{texto2}'")
    print(f"IDs:      {ids2}")
    print(f"Fractales: {[i for i in ids2 if i in IDS_FRACTALES.values()]}")
    print(f"Decoded:  '{dec2}'")

    # Test 3: estadísticas
    print("\n--- ESTADÍSTICAS ---")
    stats = tok.estadisticas("SPAWN(arquitectura) FOLD(motor) LINK(arkani, wardenclyffe)")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Test 4: batch encoding
    print("\n--- BATCH ENCODING ---")
    batch = ["hola", "SPAWN fractal", "motor arkani wardenclyffe"]
    ids_batch, masks = tok.encode_batch(batch, max_length=20)
    for i, (ids, mask) in enumerate(zip(ids_batch, masks)):
        print(f"  [{i}] {len(ids)} tokens, mask_sum={sum(mask)}")

    # Test 5: cobertura fractal del corpus
    print("\n--- COBERTURA FRACTAL ---")
    cob = tok.cobertura_fractal(corpus[:5])
    print(f"  Total tokens: {cob['total_tokens']}")
    for op, pct in cob['ops_por_token'].items():
        print(f"  {op:8}: {pct}% de todos los tokens")

    # Guardar
    print("\n--- GUARDANDO ---")
    tok.guardar("./fractal_tokenizer")

    # Recargar y verificar
    tok2 = FractalTokenizer.cargar("./fractal_tokenizer")
    ids_check = tok2.encode("EVOLVE motor fractal")
    print(f"✓ Recarga OK: {ids_check}")

    print("\n✓ tokenizer.py — listo")
    print("  Siguiente: embeddings.py")

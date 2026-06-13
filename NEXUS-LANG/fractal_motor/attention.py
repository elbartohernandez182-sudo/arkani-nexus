"""
attention.py — Multi-Head Attention Fractal ARKANI
===================================================
Protocolo Wardenclyffe — Motor Fractal v1.0

El mecanismo que permite que cada token 'observe' a todos los demás.
Sin atención, el transformer es una bolsa de palabras.
Con atención, entiende relaciones y contexto.

ANALOGÍA FRACTAL:
  SPAWN(n_heads) — cada cabeza analiza desde un ángulo diferente
  FOLD(cabezas)  — sintetiza todas las perspectivas en una sola

USO:
    from attention import MultiHeadAttention
    attn = MultiHeadAttention(d_model=256, n_heads=8)
    output = attn.forward(x, mask=mask)  # (batch, seq, d_model)
"""

import numpy as np
import json
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES AUXILIARES
# ─────────────────────────────────────────────────────────────────────────────

def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    """Softmax numéricamente estable."""
    x_max = np.max(x, axis=axis, keepdims=True)
    exp_x = np.exp(x - x_max)
    return exp_x / (np.sum(exp_x, axis=axis, keepdims=True) + 1e-8)


def crear_causal_mask(seq_len: int) -> np.ndarray:
    """
    Máscara causal — token i solo puede atender a tokens 0..i
    Sin esto el modelo 'hace trampa' viendo el futuro durante entrenamiento.
    1 = permitido, 0 = bloqueado
    """
    mask = np.tril(np.ones((seq_len, seq_len), dtype=np.float32))
    return mask[np.newaxis, np.newaxis, :, :]  # (1, 1, seq, seq)


def crear_padding_mask(tokens: np.ndarray, pad_id: int = 0) -> np.ndarray:
    """Evita atender a tokens de relleno (PAD)."""
    mask = (tokens != pad_id).astype(np.float32)
    return mask[:, np.newaxis, np.newaxis, :]  # (batch, 1, 1, seq)


# ─────────────────────────────────────────────────────────────────────────────
# KV-CACHE — acelera inferencia autorregresiva
# ─────────────────────────────────────────────────────────────────────────────
class KVCache:
    """
    Caché de Keys y Values para inferencia rápida.

    Sin caché: cada token generado recalcula K,V de TODOS los anteriores → O(n²)
    Con caché: guarda K,V y solo calcula el nuevo token → O(n)

    En ThinkPad i5-8350U esto hace la diferencia entre
    30 segundos/token y 3 segundos/token.
    """

    def __init__(self, n_layers: int, n_heads: int, max_seq_len: int, d_k: int):
        self.n_layers    = n_layers
        self.n_heads     = n_heads
        self.max_seq_len = max_seq_len
        self.d_k         = d_k
        self.limpiar()

    def limpiar(self):
        """Reinicia el caché para una nueva secuencia."""
        self.cache_k  = [
            np.zeros((1, self.n_heads, self.max_seq_len, self.d_k), dtype=np.float32)
            for _ in range(self.n_layers)
        ]
        self.cache_v  = [
            np.zeros((1, self.n_heads, self.max_seq_len, self.d_k), dtype=np.float32)
            for _ in range(self.n_layers)
        ]
        self.pos = 0

    def actualizar(self, capa: int, k: np.ndarray, v: np.ndarray):
        """Agrega K,V del token actual."""
        self.cache_k[capa][:, :, self.pos, :] = k[:, :, 0, :]
        self.cache_v[capa][:, :, self.pos, :] = v[:, :, 0, :]

    def obtener(self, capa: int) -> tuple:
        """Retorna K,V acumulados hasta la posición actual."""
        pos = self.pos + 1
        return (
            self.cache_k[capa][:, :, :pos, :],
            self.cache_v[capa][:, :, :pos, :]
        )

    def avanzar(self):
        self.pos += 1

    def memoria_mb(self) -> float:
        total = sum(k.nbytes + v.nbytes
                    for k, v in zip(self.cache_k, self.cache_v))
        return total / 1e6


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-HEAD ATTENTION FRACTAL
# ─────────────────────────────────────────────────────────────────────────────
class MultiHeadAttention:
    """
    Atención multi-cabeza fractal.

    Cada cabeza es un SPAWN — analiza el texto desde un ángulo diferente:
      Cabeza 0: relaciones sintácticas
      Cabeza 1: relaciones semánticas
      Cabeza 2: operaciones fractales
      ...
      Cabeza N: patrones de largo alcance

    FOLD al final sintetiza todas las perspectivas.
    """

    def __init__(self, d_model: int, n_heads: int, seed: int = 1979):
        assert d_model % n_heads == 0, \
            f"d_model ({d_model}) debe ser divisible entre n_heads ({n_heads})"

        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k     = d_model // n_heads  # dimensión por cabeza

        rng   = np.random.default_rng(seed)
        escala = np.sqrt(2.0 / d_model)

        # Proyecciones lineales — aprenden durante el entrenamiento
        self.W_q = rng.normal(0, escala, (d_model, d_model)).astype(np.float32)
        self.W_k = rng.normal(0, escala, (d_model, d_model)).astype(np.float32)
        self.W_v = rng.normal(0, escala, (d_model, d_model)).astype(np.float32)
        self.W_o = rng.normal(0, escala, (d_model, d_model)).astype(np.float32)

        # Bias (opcional — mejora estabilidad)
        self.b_q = np.zeros(d_model, dtype=np.float32)
        self.b_k = np.zeros(d_model, dtype=np.float32)
        self.b_v = np.zeros(d_model, dtype=np.float32)
        self.b_o = np.zeros(d_model, dtype=np.float32)

        # Cache para backward
        self._cache = {}

    def _split_heads(self, x: np.ndarray) -> np.ndarray:
        """
        SPAWN(n_heads): divide d_model en n_heads perspectivas paralelas.
        (batch, seq, d_model) → (batch, n_heads, seq, d_k)
        """
        batch, seq, _ = x.shape
        x = x.reshape(batch, seq, self.n_heads, self.d_k)
        return x.transpose(0, 2, 1, 3)

    def _merge_heads(self, x: np.ndarray) -> np.ndarray:
        """
        FOLD(cabezas): reúne todas las perspectivas en una sola representación.
        (batch, n_heads, seq, d_k) → (batch, seq, d_model)
        """
        batch, _, seq, _ = x.shape
        x = x.transpose(0, 2, 1, 3)
        return x.reshape(batch, seq, self.d_model)

    def _atencion_escalada(
        self,
        Q: np.ndarray,
        K: np.ndarray,
        V: np.ndarray,
        mask: np.ndarray = None,
    ) -> tuple:
        """
        Scaled Dot-Product Attention:
        Attention(Q,K,V) = softmax(QK^T / sqrt(d_k)) × V

        Q pregunta, K indexa, V responde.
        Como un motor de búsqueda diferenciable.
        """
        escala = np.sqrt(self.d_k)

        # Scores de atención: (batch, heads, seq_q, seq_k)
        scores = Q @ K.transpose(0, 1, 3, 2) / escala

        # Aplicar máscara (causal o padding)
        if mask is not None:
            scores = np.where(mask == 0, -1e9, scores)

        # Distribución de atención
        pesos = softmax(scores)  # (batch, heads, seq_q, seq_k)

        # Output ponderado
        output = pesos @ V  # (batch, heads, seq_q, d_k)

        return output, pesos

    def forward(
        self,
        x:     np.ndarray,
        mask:  np.ndarray = None,
        cache: KVCache    = None,
        capa:  int        = 0,
    ) -> np.ndarray:
        """
        Forward pass de la atención multi-cabeza.

        Args:
            x:     (batch, seq_len, d_model) — entrada
            mask:  máscara causal o de padding
            cache: KVCache para inferencia rápida (opcional)
            capa:  índice de capa para el cache

        Returns:
            (batch, seq_len, d_model) — salida con contexto
        """
        # Proyectar a Q, K, V
        Q = x @ self.W_q + self.b_q  # (batch, seq, d_model)
        K = x @ self.W_k + self.b_k
        V = x @ self.W_v + self.b_v

        # SPAWN: dividir en n_heads cabezas
        Q = self._split_heads(Q)  # (batch, heads, seq, d_k)
        K = self._split_heads(K)
        V = self._split_heads(V)

        # Usar KV-Cache si está disponible (modo inferencia)
        if cache is not None:
            cache.actualizar(capa, K, V)
            K, V = cache.obtener(capa)

        # Atención escalada en paralelo por cabeza
        attended, pesos = self._atencion_escalada(Q, K, V, mask)

        # FOLD: reunir cabezas
        merged = self._merge_heads(attended)  # (batch, seq, d_model)

        # Proyección final
        output = merged @ self.W_o + self.b_o

        # Guardar para backward
        self._cache = {
            'x': x, 'Q': Q, 'K': K, 'V': V,
            'pesos': pesos, 'merged': merged
        }

        return output

    def contar_parametros(self) -> dict:
        """Cuenta parámetros entrenables."""
        d = self.d_model
        return {
            'W_q': d * d,
            'W_k': d * d,
            'W_v': d * d,
            'W_o': d * d,
            'bias': 4 * d,
            'total': 4 * d * d + 4 * d,
        }

    def analizar_atencion(self, pesos: np.ndarray, tokens: list = None) -> dict:
        """
        Analiza los patrones de atención aprendidos.
        Útil para entender qué relaciones aprende cada cabeza.
        """
        # Promedio por cabeza
        pesos_mean = pesos.mean(axis=0)  # (heads, seq, seq)
        entropia_por_cabeza = []
        for h in range(self.n_heads):
            p = pesos_mean[h]
            ent = -(p * np.log(p + 1e-8)).sum(axis=-1).mean()
            entropia_por_cabeza.append(float(ent))

        return {
            'n_heads':      self.n_heads,
            'entropia':     entropia_por_cabeza,
            'cabeza_mas_enfocada': int(np.argmin(entropia_por_cabeza)),
            'cabeza_mas_difusa':   int(np.argmax(entropia_por_cabeza)),
        }

    # ── Persistencia ─────────────────────────────────────────────────────────

    def guardar(self, directorio: str):
        """Guarda los pesos de la capa de atención."""
        Path(directorio).mkdir(parents=True, exist_ok=True)
        np.save(f"{directorio}/W_q.npy", self.W_q)
        np.save(f"{directorio}/W_k.npy", self.W_k)
        np.save(f"{directorio}/W_v.npy", self.W_v)
        np.save(f"{directorio}/W_o.npy", self.W_o)
        config = {'d_model': self.d_model, 'n_heads': self.n_heads}
        with open(f"{directorio}/config.json", 'w') as f:
            json.dump(config, f)

    @classmethod
    def cargar(cls, directorio: str) -> "MultiHeadAttention":
        """Carga una capa de atención guardada."""
        with open(f"{directorio}/config.json") as f:
            config = json.load(f)
        attn = cls(**config)
        attn.W_q = np.load(f"{directorio}/W_q.npy")
        attn.W_k = np.load(f"{directorio}/W_k.npy")
        attn.W_v = np.load(f"{directorio}/W_v.npy")
        attn.W_o = np.load(f"{directorio}/W_o.npy")
        return attn


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo de la atención fractal
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — Multi-Head Attention Fractal")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    d_model = 64
    n_heads = 4
    batch   = 2
    seq_len = 8

    attn = MultiHeadAttention(d_model=d_model, n_heads=n_heads)
    params = attn.contar_parametros()
    print(f"\n✓ Atención creada: d_model={d_model}, n_heads={n_heads}")
    print(f"  Parámetros: {params['total']:,}")
    print(f"  d_k por cabeza: {attn.d_k}")

    # Test 1: forward pass
    print("\n--- FORWARD PASS ---")
    x    = np.random.randn(batch, seq_len, d_model).astype(np.float32)
    mask = crear_causal_mask(seq_len)
    out  = attn.forward(x, mask=mask)
    print(f"  Input:  {x.shape}")
    print(f"  Output: {out.shape}")
    print(f"  ✓ Shape preservado: {x.shape == out.shape}")
    print(f"  Norma media output: {np.linalg.norm(out, axis=-1).mean():.4f}")

    # Test 2: máscara causal
    print("\n--- MÁSCARA CAUSAL ---")
    mask_vis = crear_causal_mask(6)[0, 0]
    print("  Máscara 6×6 (1=ve, 0=bloqueado):")
    for fila in mask_vis:
        print("  " + " ".join("█" if v else "░" for v in fila))

    # Test 3: KV-Cache
    print("\n--- KV-CACHE ---")
    n_layers = 4
    cache = KVCache(n_layers=n_layers, n_heads=n_heads,
                    max_seq_len=512, d_k=attn.d_k)
    print(f"  Cache creado: {cache.memoria_mb():.2f} MB")

    # Simular generación token por token con cache
    x_single = np.random.randn(1, 1, d_model).astype(np.float32)
    for paso in range(4):
        out_cached = attn.forward(x_single, cache=cache, capa=0)
        cache.avanzar()
        print(f"  Token {paso+1}: output shape {out_cached.shape} ✓")

    # Test 4: análisis de atención
    print("\n--- ANÁLISIS DE ATENCIÓN ---")
    x_full = np.random.randn(1, seq_len, d_model).astype(np.float32)
    mask_full = crear_causal_mask(seq_len)
    _ = attn.forward(x_full, mask=mask_full)
    analisis = attn.analizar_atencion(attn._cache['pesos'])
    print(f"  Cabeza más enfocada: {analisis['cabeza_mas_enfocada']}")
    print(f"  Cabeza más difusa:   {analisis['cabeza_mas_difusa']}")
    print(f"  Entropía por cabeza:")
    for i, ent in enumerate(analisis['entropia']):
        barra = "█" * int(ent * 5)
        print(f"    Cabeza {i}: {ent:.4f} {barra}")

    # Test 5: persistencia
    print("\n--- PERSISTENCIA ---")
    attn.guardar("./attn_test")
    attn2 = MultiHeadAttention.cargar("./attn_test")
    out2  = attn2.forward(x, mask=mask)
    diff  = np.abs(out - out2).max()
    print(f"  Diferencia máx tras recarga: {diff:.8f} (debe ser ~0)")

    print("\n✓ attention.py — listo")
    print("  Siguiente: ffn.py")

"""
embeddings.py — Embeddings Fractales ARKANI
============================================
Protocolo Wardenclyffe — Motor Fractal v1.0

Convierte tokens (enteros) en vectores densos.
Los 7 ejes del espacio fractal corresponden a las 7 operaciones.

USO:
    from embeddings import FractalEmbedding
    emb = FractalEmbedding(vocab_size=8000, embed_dim=256)
    vectores = emb.forward(tokens)  # (batch, seq, 256)
"""

import numpy as np
from pathlib import Path
import json

# IDs de tokens fractales (deben coincidir con tokenizer.py)
IDS_FRACTALES = {
    "SUM":    4,
    "IF":     5,
    "LOOP":   6,
    "SPAWN":  7,
    "FOLD":   8,
    "LINK":   9,
    "EVOLVE": 10,
}


# ─────────────────────────────────────────────────────────────────────────────
# POSITIONAL ENCODING SINUSOIDAL
# ─────────────────────────────────────────────────────────────────────────────
def positional_encoding(max_seq_len: int, embed_dim: int) -> np.ndarray:
    """
    Codifica la posición de cada token en el espacio de embeddings.
    Sin esto el transformer trata 'gato come pez' igual que 'pez come gato'.

    Usa senos y cosenos a diferentes frecuencias:
      - Dimensiones bajas = frecuencia baja = posición global
      - Dimensiones altas = frecuencia alta = posición local
    """
    PE = np.zeros((max_seq_len, embed_dim), dtype=np.float32)
    posiciones = np.arange(max_seq_len)[:, np.newaxis]
    dimensiones = np.arange(embed_dim)[np.newaxis, :]
    angulos = posiciones / np.power(10000, (2 * (dimensiones // 2)) / embed_dim)
    PE[:, 0::2] = np.sin(angulos[:, 0::2])  # pares → seno
    PE[:, 1::2] = np.cos(angulos[:, 1::2])  # impares → coseno
    return PE


# ─────────────────────────────────────────────────────────────────────────────
# FRACTAL EMBEDDING
# ─────────────────────────────────────────────────────────────────────────────
class FractalEmbedding:
    """
    Capa de embedding fractal.

    La diferencia con un embedding normal:
    Los 7 primeros ejes del espacio vectorial están alineados
    con las 7 operaciones fractales. Cuando el modelo genera
    un token SPAWN, su vector apunta en la dirección 'spawn'
    del espacio semántico.
    """

    def __init__(
        self,
        vocab_size:   int,
        embed_dim:    int,
        max_seq_len:  int = 2048,
        seed:         int = 1979,
    ):
        self.vocab_size  = vocab_size
        self.embed_dim   = embed_dim
        self.max_seq_len = max_seq_len
        self.seed        = seed

        rng = np.random.default_rng(seed)

        # Matriz de embeddings — inicialización de Kaiming
        escala = np.sqrt(2.0 / embed_dim)
        self.W = rng.normal(0, escala, (vocab_size, embed_dim)).astype(np.float32)

        # Alinear los 7 ejes fractales con los tokens especiales
        self._inicializar_ejes_fractales()

        # Positional encoding — fijo, no se entrena
        self.PE = positional_encoding(max_seq_len, embed_dim)

        # Gradientes acumulados para actualización
        self._grad = np.zeros_like(self.W)

    def _inicializar_ejes_fractales(self):
        """
        Los tokens SUM, IF, LOOP, SPAWN, FOLD, LINK, EVOLVE
        se inicializan como vectores ortogonales entre sí.
        Esto ayuda al modelo a distinguirlos desde el inicio.
        """
        n_ops = len(IDS_FRACTALES)
        # Crear n_ops vectores ortogonales usando QR decomposition
        rng = np.random.default_rng(self.seed + 42)
        M = rng.normal(0, 1, (n_ops, self.embed_dim)).astype(np.float32)
        Q, _ = np.linalg.qr(M.T)  # Q tiene columnas ortogonales
        Q = Q.T[:n_ops]  # (n_ops, embed_dim)

        for i, (op, id_op) in enumerate(IDS_FRACTALES.items()):
            if id_op < self.vocab_size:
                self.W[id_op] = Q[i] * np.sqrt(self.embed_dim)

    def forward(
        self,
        tokens: np.ndarray,
        agregar_pe: bool = True,
    ) -> np.ndarray:
        """
        Convierte tokens a vectores.

        Args:
            tokens: (batch, seq_len) de enteros
            agregar_pe: sumar positional encoding

        Returns:
            (batch, seq_len, embed_dim) de float32
        """
        # Validar índices
        tokens_clip = np.clip(tokens, 0, self.vocab_size - 1)

        # Lookup — operación O(1)
        x = self.W[tokens_clip]  # (batch, seq_len, embed_dim)

        # Sumar positional encoding
        if agregar_pe:
            seq_len = tokens.shape[-1]
            x = x + self.PE[:seq_len]

        return x

    def backward(
        self,
        tokens:     np.ndarray,
        grad_output: np.ndarray,
        lr:         float = 1e-3,
    ) -> None:
        """
        Actualiza los embeddings por gradiente descendente.
        Solo actualiza los tokens que aparecieron en el forward.
        """
        # Acumular gradientes por token (puede repetirse en el batch)
        np.add.at(self._grad, tokens.flatten(), grad_output.reshape(-1, self.embed_dim))

        # Aplicar actualización
        self.W -= lr * self._grad

        # Limpiar gradientes
        self._grad.fill(0)

        # Re-normalizar tokens fractales para mantener ortogonalidad
        self._normalizar_fractales()

    def _normalizar_fractales(self):
        """Mantiene los vectores fractales con norma consistente."""
        for op, id_op in IDS_FRACTALES.items():
            if id_op < self.vocab_size:
                norma = np.linalg.norm(self.W[id_op])
                if norma > 0:
                    self.W[id_op] = self.W[id_op] / norma * np.sqrt(self.embed_dim)

    # ── Análisis semántico ───────────────────────────────────────────────────

    def similitud_coseno(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """Distancia semántica entre dos embeddings."""
        norma = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norma < 1e-8:
            return 0.0
        return float(np.dot(v1, v2) / norma)

    def tokens_cercanos(self, vector: np.ndarray, top_k: int = 5) -> list:
        """
        Encuentra los k tokens más similares semánticamente.
        Útil para explorar el espacio fractal aprendido.
        """
        normas = np.linalg.norm(self.W, axis=1, keepdims=True)
        W_norm = self.W / (normas + 1e-8)
        v_norm = vector / (np.linalg.norm(vector) + 1e-8)
        sims   = W_norm @ v_norm
        top_ids = np.argsort(sims)[-top_k:][::-1]
        return [(int(i), float(sims[i])) for i in top_ids]

    def distancia_fractal(self, id_token: int) -> dict:
        """
        Mide qué tan cerca está un token de cada operación fractal.
        Útil para entender qué 'tipo' de token es semánticamente.
        """
        if id_token >= self.vocab_size:
            return {}
        vector = self.W[id_token]
        distancias = {}
        for op, id_op in IDS_FRACTALES.items():
            if id_op < self.vocab_size:
                distancias[op] = round(self.similitud_coseno(vector, self.W[id_op]), 4)
        return distancias

    def mapa_fractal(self, tokens_ids: list) -> np.ndarray:
        """
        Proyecta tokens al espacio de las 7 operaciones fractales.
        Retorna una matriz (n_tokens, 7) con las similitudes.
        Útil para visualizar cómo el modelo 've' los tokens.
        """
        n = len(tokens_ids)
        mapa = np.zeros((n, 7), dtype=np.float32)
        for i, id_tok in enumerate(tokens_ids):
            dist = self.distancia_fractal(id_tok)
            for j, op in enumerate(["SUM","IF","LOOP","SPAWN","FOLD","LINK","EVOLVE"]):
                mapa[i, j] = dist.get(op, 0.0)
        return mapa

    # ── Estadísticas ─────────────────────────────────────────────────────────

    def estadisticas(self) -> dict:
        """Resumen del estado del embedding."""
        normas = np.linalg.norm(self.W, axis=1)
        ops_stats = {}
        for op, id_op in IDS_FRACTALES.items():
            if id_op < self.vocab_size:
                # Similitud entre cada par de operaciones
                sims = []
                for op2, id_op2 in IDS_FRACTALES.items():
                    if op != op2 and id_op2 < self.vocab_size:
                        sims.append(self.similitud_coseno(self.W[id_op], self.W[id_op2]))
                ops_stats[op] = {
                    "norma": round(float(normas[id_op]), 4),
                    "sim_max_con_otras": round(max(sims) if sims else 0, 4),
                }
        return {
            "vocab_size":    self.vocab_size,
            "embed_dim":     self.embed_dim,
            "norma_media":   round(float(normas.mean()), 4),
            "norma_std":     round(float(normas.std()), 4),
            "ops_fractales": ops_stats,
        }

    # ── Persistencia ─────────────────────────────────────────────────────────

    def guardar(self, directorio: str = "./fractal_motor"):
        """Guarda los pesos del embedding."""
        Path(directorio).mkdir(parents=True, exist_ok=True)
        np.save(f"{directorio}/embeddings_W.npy", self.W)
        config = {
            "vocab_size":  self.vocab_size,
            "embed_dim":   self.embed_dim,
            "max_seq_len": self.max_seq_len,
            "seed":        self.seed,
            "version":     "1.0",
        }
        with open(f"{directorio}/embeddings_config.json", "w") as f:
            json.dump(config, f, indent=2)
        print(f"✓ Embeddings guardados en {directorio}/")

    @classmethod
    def cargar(cls, directorio: str = "./fractal_motor") -> "FractalEmbedding":
        """Carga embeddings previamente guardados."""
        with open(f"{directorio}/embeddings_config.json") as f:
            config = json.load(f)
        config.pop("version", None)  # eliminar campos no usados en __init__
        emb = cls(**config)
        emb.W = np.load(f"{directorio}/embeddings_W.npy")
        print(f"✓ Embeddings cargados desde {directorio}/")
        return emb


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo del embedding fractal
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — Embeddings Fractales")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    # Crear embedding
    emb = FractalEmbedding(vocab_size=1000, embed_dim=64)
    print(f"\n✓ Embedding creado: {emb.vocab_size} tokens × {emb.embed_dim} dims")

    # Test 1: forward pass
    print("\n--- FORWARD PASS ---")
    tokens = np.array([[1, 7, 42, 8, 10, 2]])  # BOS SPAWN token FOLD EVOLVE EOS
    x = emb.forward(tokens)
    print(f"  Input shape:  {tokens.shape}")
    print(f"  Output shape: {x.shape}")
    print(f"  Dtype: {x.dtype}")
    print(f"  Norma media: {np.linalg.norm(x, axis=-1).mean():.4f}")

    # Test 2: ortogonalidad de operaciones fractales
    print("\n--- ORTOGONALIDAD FRACTAL ---")
    print("  Similitudes entre operaciones (ideal: cercano a 0):")
    ops = list(IDS_FRACTALES.items())
    for i, (op1, id1) in enumerate(ops):
        for j, (op2, id2) in enumerate(ops):
            if i < j:
                sim = emb.similitud_coseno(emb.W[id1], emb.W[id2])
                barra = "█" * int(abs(sim) * 20)
                print(f"  {op1:8} ↔ {op2:8}: {sim:+.4f} {barra}")

    # Test 3: mapa fractal
    print("\n--- MAPA FRACTAL ---")
    tokens_prueba = [7, 42, 8, 100, 10]  # SPAWN, token_normal, FOLD, token_normal, EVOLVE
    mapa = emb.mapa_fractal(tokens_prueba)
    ops_nombres = ["SUM","IF","LOOP","SPAWN","FOLD","LINK","EVOLVE"]
    print(f"  {'TOKEN':8} " + " ".join(f"{op:7}" for op in ops_nombres))
    for i, id_tok in enumerate(tokens_prueba):
        valores = " ".join(f"{mapa[i,j]:+.3f}" for j in range(7))
        print(f"  {id_tok:8} {valores}")

    # Test 4: tokens cercanos a SPAWN
    print("\n--- TOKENS CERCANOS A SPAWN ---")
    cercanos = emb.tokens_cercanos(emb.W[IDS_FRACTALES["SPAWN"]], top_k=5)
    for id_tok, sim in cercanos:
        print(f"  ID {id_tok:4}: similitud {sim:.4f}")

    # Test 5: estadísticas
    print("\n--- ESTADÍSTICAS ---")
    stats = emb.estadisticas()
    print(f"  Norma media: {stats['norma_media']}")
    print(f"  Norma std:   {stats['norma_std']}")
    print("  Operaciones fractales:")
    for op, s in stats["ops_fractales"].items():
        print(f"    {op:8}: norma={s['norma']}, sim_max={s['sim_max_con_otras']}")

    # Test 6: guardar y recargar
    print("\n--- PERSISTENCIA ---")
    emb.guardar("./fractal_motor_test")
    emb2 = FractalEmbedding.cargar("./fractal_motor_test")
    x2 = emb2.forward(tokens)
    diff = np.abs(x - x2).max()
    print(f"  Diferencia máx tras recarga: {diff:.8f} (debe ser ~0)")

    print("\n✓ embeddings.py — listo")
    print("  Siguiente: attention.py")


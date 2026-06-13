"""
modelo.py — FractalLM Completo
===============================
Protocolo Wardenclyffe — Motor Fractal v1.0

Este es el LLM fractal de ARKANI — ensamblado desde cero.
No depende de PyTorch, TensorFlow, ni Ollama.
Solo Python + NumPy.

ARQUITECTURA:
  Embedding + PositionalEncoding
  → N × TransformerBlock (Attention + FFN + LayerNorm)
  → LayerNorm final
  → LM Head (proyección a vocabulario)

USO:
    from modelo import FractalLM
    config = FractalLMConfig(vocab_size=8000, d_model=256, n_layers=4, n_heads=8)
    modelo = FractalLM(config)
    logits = modelo.forward(tokens)  # (batch, seq, vocab_size)
"""

import numpy as np
import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from ffn import FeedForward, LayerNorm, TransformerBlock
from attention import MultiHeadAttention, KVCache, crear_causal_mask
from embeddings import FractalEmbedding
from tokenizer import FractalTokenizer


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DEL MODELO
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class FractalLMConfig:
    """
    Configuración completa del FractalLM.
    Diferentes tamaños para diferentes hardware:
    """
    vocab_size:  int   = 8000    # tamaño del vocabulario
    d_model:     int   = 256     # dimensión de embeddings
    n_layers:    int   = 4       # número de bloques transformer
    n_heads:     int   = 8       # cabezas de atención
    d_ff:        int   = None    # dimensión FFN (default: 4×d_model)
    max_seq_len: int   = 1024    # longitud máxima de secuencia
    seed:        int   = 1979    # semilla reproducibilidad
    nombre:      str   = "FractalLM-MINI"
    version:     str   = "1.0"
    protocolo:   str   = "Wardenclyffe"

    def __post_init__(self):
        if self.d_ff is None:
            self.d_ff = 4 * self.d_model
        # Validaciones
        assert self.d_model % self.n_heads == 0, \
            f"d_model ({self.d_model}) debe ser divisible entre n_heads ({self.n_heads})"

    def contar_parametros(self) -> int:
        """Estima el total de parámetros del modelo."""
        params_emb    = self.vocab_size * self.d_model
        params_bloque = (4 * self.d_model**2 +        # atención
                         2 * self.d_model * self.d_ff + # FFN
                         4 * self.d_model)              # LayerNorm×2
        params_head   = self.vocab_size * self.d_model  # LM head
        return params_emb + self.n_layers * params_bloque + params_head

    def ram_estimada_mb(self) -> float:
        """Estima RAM necesaria en MB (FP32)."""
        return self.contar_parametros() * 4 / 1e6


# Configuraciones predefinidas
CONFIGS = {
    "nano": FractalLMConfig(
        vocab_size=4000, d_model=128, n_layers=2, n_heads=4,
        nombre="FractalLM-NANO"
    ),  # ~20MB RAM — pruebas rápidas
    "mini": FractalLMConfig(
        vocab_size=8000, d_model=256, n_layers=4, n_heads=8,
        nombre="FractalLM-MINI"
    ),  # ~100MB RAM — ThinkPad
    "small": FractalLMConfig(
        vocab_size=16000, d_model=512, n_layers=6, n_heads=8,
        nombre="FractalLM-SMALL"
    ),  # ~400MB RAM — PC normal
    "medium": FractalLMConfig(
        vocab_size=32000, d_model=1024, n_layers=12, n_heads=16,
        nombre="FractalLM-MEDIUM"
    ),  # ~1.5GB RAM — laptop moderna
}


# ─────────────────────────────────────────────────────────────────────────────
# FRACTAL LM — EL MODELO COMPLETO
# ─────────────────────────────────────────────────────────────────────────────
class FractalLM:
    """
    FractalLM — El primer LLM con lenguaje fractal nativo.

    Diferencia con modelos existentes:
    - Tokens <SPAWN>, <FOLD>, <EVOLVE> son ciudadanos de primera clase
    - Los 7 ejes del espacio de embeddings son las 7 operaciones
    - El modelo puede inspeccionar y modificar sus propios pesos (EVOLVE)
    - 100% Python + NumPy — sin dependencias externas
    """

    def __init__(self, config: FractalLMConfig):
        self.config = config
        self._construir_modelo()

    def _construir_modelo(self):
        """Construye todas las capas del modelo."""
        cfg = self.config
        seed = cfg.seed

        # Capa de entrada — embeddings con ejes fractales
        self.embedding = FractalEmbedding(
            vocab_size=cfg.vocab_size,
            embed_dim=cfg.d_model,
            max_seq_len=cfg.max_seq_len,
            seed=seed,
        )

        # N bloques Transformer apilados
        self.bloques = [
            TransformerBlock(
                d_model=cfg.d_model,
                n_heads=cfg.n_heads,
                d_ff=cfg.d_ff,
                seed=seed + i,
            )
            for i in range(cfg.n_layers)
        ]

        # Normalización final
        self.norm_final = LayerNorm(cfg.d_model)

        # LM Head — proyecta a logits sobre el vocabulario
        # Weight tying: comparte pesos con embedding (ahorra parámetros)
        # El LM Head ES la transpuesta de la matriz de embeddings
        self._weight_tying = True

        # KV-Cache para inferencia rápida
        d_k = cfg.d_model // cfg.n_heads
        self.kv_cache = KVCache(
            n_layers=cfg.n_layers,
            n_heads=cfg.n_heads,
            max_seq_len=cfg.max_seq_len,
            d_k=d_k,
        )

    def forward(
        self,
        tokens:      np.ndarray,
        mask:        np.ndarray = None,
        usar_cache:  bool = False,
    ) -> np.ndarray:
        """
        Forward pass completo del FractalLM.

        Args:
            tokens:     (batch, seq_len) enteros
            mask:       máscara causal (auto-generada si None)
            usar_cache: usar KV-Cache para inferencia token a token

        Returns:
            logits: (batch, seq_len, vocab_size) float32
        """
        batch, seq_len = tokens.shape

        # Máscara causal automática
        if mask is None:
            mask = crear_causal_mask(seq_len)

        # 1. Embedding + Positional Encoding
        x = self.embedding.forward(tokens, agregar_pe=True)
        # x: (batch, seq_len, d_model)

        # 2. N bloques Transformer
        for i, bloque in enumerate(self.bloques):
            cache = self.kv_cache if usar_cache else None
            x = bloque.forward(x, mask=mask, cache=cache, capa=i)

        # 3. Normalización final
        x = self.norm_final.forward(x)

        # 4. Proyección a logits (weight tying)
        logits = x @ self.embedding.W.T
        # logits: (batch, seq_len, vocab_size)

        return logits

    def contar_parametros(self) -> dict:
        """Cuenta parámetros por componente."""
        cfg = self.config
        params_emb    = cfg.vocab_size * cfg.d_model
        params_bloque = sum(
            b.contar_parametros()['total']
            for b in self.bloques
        )
        params_norm   = 2 * cfg.d_model
        # Weight tying: LM head no cuenta extra
        total = params_emb + params_bloque + params_norm

        return {
            'embedding':     params_emb,
            'bloques':       params_bloque,
            'norm_final':    params_norm,
            'lm_head':       0,  # weight tying
            'total':         total,
            'total_M':       round(total / 1e6, 2),
            'ram_fp32_mb':   round(total * 4 / 1e6, 1),
        }

    def resumen(self) -> str:
        """Imprime resumen del modelo."""
        cfg    = self.config
        params = self.contar_parametros()
        lineas = [
            f"{'='*50}",
            f"  {cfg.nombre} — Protocolo {cfg.protocolo}",
            f"{'='*50}",
            f"  vocab_size:  {cfg.vocab_size:,}",
            f"  d_model:     {cfg.d_model}",
            f"  n_layers:    {cfg.n_layers}",
            f"  n_heads:     {cfg.n_heads}",
            f"  d_ff:        {cfg.d_ff}",
            f"  max_seq_len: {cfg.max_seq_len}",
            f"  Parámetros:  {params['total_M']}M",
            f"  RAM FP32:    {params['ram_fp32_mb']}MB",
            f"{'='*50}",
        ]
        return '\n'.join(lineas)

    # ── EVOLVE — el modelo inspecciona sus propios pesos ─────────────────────

    def evolve_inspeccion(self) -> dict:
        """
        EVOLVE: ARKANI inspecciona sus propios pesos.
        Detecta capas con problemas (gradientes muertos, saturación).
        """
        informe = {}

        # Inspeccionar embeddings
        normas_emb = np.linalg.norm(self.embedding.W, axis=1)
        informe['embedding'] = {
            'norma_media': round(float(normas_emb.mean()), 4),
            'norma_std':   round(float(normas_emb.std()), 4),
            'tokens_muertos': int((normas_emb < 0.01).sum()),
        }

        # Inspeccionar bloques
        informe['bloques'] = []
        for i, bloque in enumerate(self.bloques):
            norma_W1 = float(np.linalg.norm(bloque.ffn.W1))
            norma_W2 = float(np.linalg.norm(bloque.ffn.W2))
            norma_Wq = float(np.linalg.norm(bloque.attn.W_q))
            informe['bloques'].append({
                'capa':    i,
                'ffn_W1':  round(norma_W1, 4),
                'ffn_W2':  round(norma_W2, 4),
                'attn_Wq': round(norma_Wq, 4),
                'estado':  'ok' if 0.1 < norma_W1 < 1000 else 'revisar',
            })

        return informe

    def evolve_reiniciar_capa(self, capa: int):
        """
        EVOLVE: reinicia los pesos de una capa específica.
        Útil si una capa se saturó durante el entrenamiento.
        """
        if 0 <= capa < len(self.bloques):
            seed_nuevo = self.config.seed + capa + 1000
            self.bloques[capa] = TransformerBlock(
                d_model=self.config.d_model,
                n_heads=self.config.n_heads,
                d_ff=self.config.d_ff,
                seed=seed_nuevo,
            )
            print(f"✓ Capa {capa} reiniciada con seed {seed_nuevo}")

    # ── Persistencia ─────────────────────────────────────────────────────────

    def guardar(self, directorio: str = "./fractal_model"):
        """
        Guarda el modelo completo en disco.
        Formato propio .arkani — sin dependencias.
        """
        Path(directorio).mkdir(parents=True, exist_ok=True)

        # Config
        config_dict = asdict(self.config)
        with open(f"{directorio}/config.json", 'w') as f:
            json.dump(config_dict, f, indent=2)

        # Embeddings
        np.save(f"{directorio}/embedding_W.npy", self.embedding.W)

        # Bloques
        for i, bloque in enumerate(self.bloques):
            bloque_dir = f"{directorio}/bloque_{i:02d}"
            Path(bloque_dir).mkdir(exist_ok=True)
            # Atención
            np.save(f"{bloque_dir}/attn_Wq.npy", bloque.attn.W_q)
            np.save(f"{bloque_dir}/attn_Wk.npy", bloque.attn.W_k)
            np.save(f"{bloque_dir}/attn_Wv.npy", bloque.attn.W_v)
            np.save(f"{bloque_dir}/attn_Wo.npy", bloque.attn.W_o)
            # FFN
            np.save(f"{bloque_dir}/ffn_W1.npy", bloque.ffn.W1)
            np.save(f"{bloque_dir}/ffn_W2.npy", bloque.ffn.W2)
            np.save(f"{bloque_dir}/ffn_b1.npy", bloque.ffn.b1)
            np.save(f"{bloque_dir}/ffn_b2.npy", bloque.ffn.b2)
            # LayerNorm
            np.save(f"{bloque_dir}/norm1_gamma.npy", bloque.norm1.gamma)
            np.save(f"{bloque_dir}/norm1_beta.npy",  bloque.norm1.beta)
            np.save(f"{bloque_dir}/norm2_gamma.npy", bloque.norm2.gamma)
            np.save(f"{bloque_dir}/norm2_beta.npy",  bloque.norm2.beta)

        # Norm final
        np.save(f"{directorio}/norm_final_gamma.npy", self.norm_final.gamma)
        np.save(f"{directorio}/norm_final_beta.npy",  self.norm_final.beta)

        params = self.contar_parametros()
        print(f"✓ FractalLM guardado en: {directorio}/")
        print(f"  Parámetros: {params['total_M']}M")
        print(f"  RAM:        {params['ram_fp32_mb']}MB")

    @classmethod
    def cargar(cls, directorio: str) -> "FractalLM":
        """Carga un FractalLM guardado."""
        with open(f"{directorio}/config.json") as f:
            config_dict = json.load(f)

        config = FractalLMConfig(**config_dict)
        modelo = cls(config)

        # Embeddings
        modelo.embedding.W = np.load(f"{directorio}/embedding_W.npy")

        # Bloques
        for i, bloque in enumerate(modelo.bloques):
            d = f"{directorio}/bloque_{i:02d}"
            bloque.attn.W_q = np.load(f"{d}/attn_Wq.npy")
            bloque.attn.W_k = np.load(f"{d}/attn_Wk.npy")
            bloque.attn.W_v = np.load(f"{d}/attn_Wv.npy")
            bloque.attn.W_o = np.load(f"{d}/attn_Wo.npy")
            bloque.ffn.W1   = np.load(f"{d}/ffn_W1.npy")
            bloque.ffn.W2   = np.load(f"{d}/ffn_W2.npy")
            bloque.ffn.b1   = np.load(f"{d}/ffn_b1.npy")
            bloque.ffn.b2   = np.load(f"{d}/ffn_b2.npy")
            bloque.norm1.gamma = np.load(f"{d}/norm1_gamma.npy")
            bloque.norm1.beta  = np.load(f"{d}/norm1_beta.npy")
            bloque.norm2.gamma = np.load(f"{d}/norm2_gamma.npy")
            bloque.norm2.beta  = np.load(f"{d}/norm2_beta.npy")

        modelo.norm_final.gamma = np.load(f"{directorio}/norm_final_gamma.npy")
        modelo.norm_final.beta  = np.load(f"{directorio}/norm_final_beta.npy")

        print(f"✓ FractalLM cargado desde: {directorio}/")
        return modelo


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — demo del FractalLM completo
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  ARKANI — FractalLM Completo")
    print("  Protocolo Wardenclyffe — Motor v1.0")
    print("=" * 55)

    # Test con configuración NANO — más rápida para demo
    config = CONFIGS["nano"]
    modelo = FractalLM(config)

    print(modelo.resumen())

    params = modelo.contar_parametros()
    print(f"\n  Desglose de parámetros:")
    for k, v in params.items():
        print(f"    {k:15}: {v}")

    # Test 1: forward pass
    print("\n--- FORWARD PASS ---")
    batch, seq_len = 2, 16
    tokens = np.random.randint(0, config.vocab_size, (batch, seq_len))
    logits = modelo.forward(tokens)
    print(f"  Input tokens: {tokens.shape}")
    print(f"  Logits:       {logits.shape}")
    print(f"  ✓ Shape: (batch={batch}, seq={seq_len}, vocab={config.vocab_size})")
    print(f"  Logits min/max: {logits.min():.4f} / {logits.max():.4f}")

    # Test 2: generar siguiente token
    print("\n--- PREDICCIÓN SIGUIENTE TOKEN ---")
    def softmax(x):
        e = np.exp(x - x.max())
        return e / e.sum()

    logits_ultimo = logits[0, -1]  # último token del primer ejemplo
    probs         = softmax(logits_ultimo)
    top5_ids      = np.argsort(probs)[-5:][::-1]
    print(f"  Top 5 tokens más probables:")
    for id_tok in top5_ids:
        print(f"    ID {id_tok:5}: {probs[id_tok]:.6f}")

    # Test 3: EVOLVE — inspección propia
    print("\n--- EVOLVE: INSPECCIÓN PROPIA ---")
    informe = modelo.evolve_inspeccion()
    print(f"  Embedding — norma media: {informe['embedding']['norma_media']}")
    print(f"  Tokens muertos: {informe['embedding']['tokens_muertos']}")
    print(f"  Bloques:")
    for b in informe['bloques']:
        estado = "✓" if b['estado'] == 'ok' else "⚠"
        print(f"    {estado} Capa {b['capa']}: ffn_W1={b['ffn_W1']:.3f}, attn_Wq={b['attn_Wq']:.3f}")

    # Test 4: comparar tamaños de configuración
    print("\n--- COMPARATIVA DE CONFIGURACIONES ---")
    print(f"  {'Config':8} {'Params':>10} {'RAM MB':>10} {'Viable en':>20}")
    print(f"  {'-'*52}")
    for nombre, cfg in CONFIGS.items():
        p = cfg.contar_parametros()
        ram = cfg.ram_estimada_mb()
        if ram < 200:
            hw = "cualquier laptop"
        elif ram < 500:
            hw = "4GB RAM"
        elif ram < 2000:
            hw = "8GB RAM"
        else:
            hw = "16GB RAM"
        print(f"  {nombre:8} {p/1e6:>8.1f}M {ram:>8.0f}MB   {hw}")

    # Test 5: guardar y cargar
    print("\n--- PERSISTENCIA ---")
    modelo.guardar("./fractal_model_test")
    modelo2 = FractalLM.cargar("./fractal_model_test")
    logits2 = modelo2.forward(tokens)
    diff    = np.abs(logits - logits2).max()
    print(f"  Diferencia máx tras recarga: {diff:.8f} (debe ser ~0)")

    print("\n✓ modelo.py — FractalLM completo y funcional")
    print("  Siguiente: inferencia.py — generación token a token")

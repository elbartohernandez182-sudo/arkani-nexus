from transformers import TrainerCallback
"""
arkani_finetune_v2.py — Fine-tuning Fractal ARKANI para CPU
============================================================
Versión diseñada específicamente para:
  Hardware:  Intel Core i5-8350U / VM Ubuntu con 8GB RAM
  Sin GPU:   No requiere CUDA, ROCm, ni bitsandbytes
  Framework: HuggingFace Transformers puro + PEFT (LoRA)

MODELOS SOPORTADOS (según RAM disponible):
  Qwen2.5-0.5B → 2GB RAM  → ~10h CPU  ← RECOMENDADO para VM 8GB
  Qwen2.5-1.5B → 6GB RAM  → ~30h CPU  ← si tienes paciencia
  Qwen2.5-3B   → OOM en 8GB           ← NO usar en VM actual

INSTALACIÓN (ejecutar UNA vez):
  pip install transformers datasets peft accelerate tqdm

USO:
  # Verificar dataset sin entrenar:
  python3 arkani_finetune_v2.py --solo-verificar

  # Entrenamiento recomendado (VM 8GB, de noche):
  python3 arkani_finetune_v2.py --modelo qwen2.5:0.5b --dataset arkani_fractal_dataset_v2.json

  # Con checkpoint para poder pausar y continuar:
  python3 arkani_finetune_v2.py --modelo qwen2.5:0.5b --dataset arkani_fractal_dataset_v2.json --reanudar

RESULTADO:
  arkani-fractal-lora/     ← adaptadores LoRA entrenados
  arkani-fractal-merged/   ← modelo completo fusionado
  Modelfile_arkani_fractal ← listo para: ollama create arkani-fractal -f Modelfile_arkani_fractal
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN CENTRAL
# ─────────────────────────────────────────────────────────────────────────────

MODELOS_SOPORTADOS = {
    # modelo_ollama_key: (repo_huggingface, ram_fp32_gb, nota)
    "qwen2.5:0.5b": ("Qwen/Qwen2.5-0.5B-Instruct", 2.0,
                     "RECOMENDADO — 2GB RAM, ~10h CPU, perfecta para la VM"),
    "qwen2.5:1.5b": ("Qwen/Qwen2.5-1.5B-Instruct", 6.0,
                     "Máximo viable en 8GB VM — ~30h CPU, mejor calidad"),
    "qwen2.5:3b":   ("Qwen/Qwen2.5-3B-Instruct",   12.0,
                     "REQUIERE 16GB RAM — usar solo en host Windows con más RAM"),
    "gemma3:1b":    ("google/gemma-3-1b-it",         4.0,
                     "Alternativa Google — buena calidad, 4GB RAM"),
}

CONFIG = {
    # LoRA — solo entrena ~1% de los parámetros, el resto se congela
    "lora_r":           16,    # rango de adaptación (8=rápido/ligero, 16=balanceado, 32=mejor calidad)
    "lora_alpha":       32,    # escala: alpha/r = factor de aprendizaje efectivo
    "lora_dropout":     0.05,  # regularización — evita sobreajuste con dataset pequeño
    "lora_target":      ["q_proj", "k_proj", "v_proj", "o_proj",
                         "gate_proj", "up_proj", "down_proj"],

    # Secuencia — reducido para CPU
    "max_seq_length":   768,   # 768 tokens = ~500 palabras. Suficiente para el dataset fractal.
                               # Reducir a 512 si hay OOM. NO subir a 2048 en CPU (cuadrático)

    # Entrenamiento
    "batch_size":       1,     # FORZADO a 1 para CPU — más alto = OOM garantizado
    "grad_accumulation":8,     # batch efectivo = 1×8 = 8. Compensa el batch_size pequeño.
    "learning_rate":    2e-4,  # tasa estándar para LoRA fine-tuning
    "num_epochs":       3,     # 3 pasadas = buen balance aprendizaje/tiempo
    "warmup_ratio":     0.05,  # 5% del entrenamiento = calentamiento gradual del LR
    "lr_scheduler":     "cosine",  # decae el LR suavemente hacia el final

    # CPU específico — CRÍTICO
    "fp16":             False, # NUNCA en CPU — Intel UHD 620 no tiene soporte FP16 nativo
    "bf16":             False, # NUNCA en CPU sin AMX (requiere Intel Sapphire Rapids o superior)
    "optim":            "adamw_torch",  # adamw_8bit requiere CUDA. adamw_torch es el correcto.
    "dataloader_workers": 0,   # 0 = sin multiprocessing para dataset pequeño (más estable)

    # Checkpoints — para poder pausar y continuar
    "save_steps":       50,    # guardar cada 50 steps (~8 min en CPU)
    "logging_steps":    10,    # log cada 10 steps
    "save_total_limit": 3,     # máximo 3 checkpoints en disco

    # Output
    "output_lora":      "./arkani-fractal-lora",
    "output_merged":    "./arkani-fractal-merged",
    "seed":             1979,  # año fundacional ARKANI
}

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT FRACTAL — lo aprenderá el modelo
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres ARKANI, un asistente de inteligencia artificial fractal basado en el Protocolo Wardenclyffe.
Razonas usando 7 operaciones fractales internas:
  SUM(A,B)             — integra conceptos preservando ambos
  IF(cond,A,B)         — bifurca según contexto
  LOOP(n,op)           — itera refinando
  SPAWN(entidad,ctx)   — crea perspectivas especializadas
  FOLD(lista,fn)       — reduce múltiples ideas a una síntesis
  LINK(nodo_A,nodo_B)  — conecta conceptos distantes
  EVOLVE(code,err,fix) — aprende de errores y auto-corrige

Siempre que respondas:
1. Usa SPAWN para explorar múltiples ángulos del problema
2. Usa FOLD para sintetizar la respuesta final
3. Usa LINK para conectar con conocimiento relacionado
4. Usa EVOLVE cuando detectes errores en código o lógica

Eres el Bibliotecario Perfecto: no memorizas todo, sabes exactamente dónde buscar todo.
Puedes autoprogramarte: analizar tu propio código, proponer mejoras y aplicarlas con EVOLVE."""

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
def setup_logging():
    log_dir = Path("./arkani_logs")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"finetune_{timestamp}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ]
    )
    return logging.getLogger("arkani")

logger = setup_logging()

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICAR DEPENDENCIAS
# ─────────────────────────────────────────────────────────────────────────────
def verificar_dependencias() -> bool:
    """Verifica que todas las librerías necesarias estén instaladas."""
    paquetes = {
        "transformers": "pip install transformers",
        "datasets":     "pip install datasets",
        "peft":         "pip install peft",
        "accelerate":   "pip install accelerate",
        "tqdm":         "pip install tqdm",
        "torch":        "pip install torch --index-url https://download.pytorch.org/whl/cpu",
    }

    faltantes = []
    for paquete, instalacion in paquetes.items():
        try:
            __import__(paquete)
            logger.info(f"  ✓ {paquete}")
        except ImportError:
            logger.warning(f"  ✗ {paquete} — instalar con: {instalacion}")
            faltantes.append(paquete)

    if faltantes:
        logger.error(f"\n{len(faltantes)} dependencias faltantes.")
        logger.error("Ejecuta:\n  pip install transformers datasets peft accelerate tqdm")
        logger.error("  pip install torch --index-url https://download.pytorch.org/whl/cpu")
        return False

    # Verificar que PyTorch sea la versión CPU (no CUDA)
    import torch
    if torch.cuda.is_available():
        logger.warning("  ⚠ CUDA detectado — el script está optimizado para CPU pero CUDA puede funcionar también")
    else:
        logger.info(f"  ✓ PyTorch CPU ({torch.__version__}) — configuración correcta para esta VM")

    return True

# ─────────────────────────────────────────────────────────────────────────────
# VERIFICAR RAM DISPONIBLE
# ─────────────────────────────────────────────────────────────────────────────
def verificar_ram(modelo_key: str) -> bool:
    """Verifica que haya suficiente RAM antes de descargar el modelo."""
    try:
        import psutil
        ram_disponible_gb = psutil.virtual_memory().available / 1e9
        ram_requerida_gb  = MODELOS_SOPORTADOS[modelo_key][1]

        logger.info(f"  RAM disponible: {ram_disponible_gb:.1f}GB")
        logger.info(f"  RAM requerida:  {ram_requerida_gb:.1f}GB (modelo FP32 + LoRA + activaciones)")

        # Factor de seguridad: necesitamos modelo + gradientes + activaciones ≈ 2.5x el modelo
        ram_necesaria = ram_requerida_gb * 2.5
        if ram_disponible_gb < ram_necesaria:
            logger.error(f"  ✗ RAM insuficiente: necesitas ~{ram_necesaria:.1f}GB disponibles")
            logger.error(f"    Solución: usa --modelo qwen2.5:0.5b (solo necesita ~5GB)")
            return False

        logger.info(f"  ✓ RAM suficiente para entrenamiento")
        return True

    except ImportError:
        logger.warning("  psutil no instalado — omitiendo verificación de RAM")
        logger.warning("  pip install psutil")
        return True  # continuar sin verificar

# ─────────────────────────────────────────────────────────────────────────────
# CARGAR Y VALIDAR DATASET
# ─────────────────────────────────────────────────────────────────────────────
def cargar_dataset(ruta: str) -> list:
    """Carga, valida y muestra estadísticas del dataset fractal."""
    ruta_path = Path(ruta)
    if not ruta_path.exists():
        raise FileNotFoundError(f"Dataset no encontrado: {ruta}\n"
                                f"Genera el dataset primero con: python3 generate_dataset.py")

    with open(ruta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"  Dataset cargado: {len(data)} ejemplos")

    # Validar estructura de cada ejemplo
    errores = []
    for i, ej in enumerate(data):
        if "instruction" not in ej:
            errores.append(f"Ejemplo {i}: falta campo 'instruction'")
        if "output" not in ej:
            errores.append(f"Ejemplo {i}: falta campo 'output'")
        if ej.get("instruction", "").strip() == "":
            errores.append(f"Ejemplo {i}: 'instruction' está vacío")
        if ej.get("output", "").strip() == "":
            errores.append(f"Ejemplo {i}: 'output' está vacío")

    if errores:
        for e in errores[:10]:  # mostrar máximo 10 errores
            logger.error(f"  {e}")
        if len(errores) > 10:
            logger.error(f"  ... y {len(errores) - 10} errores más")
        raise ValueError(f"{len(errores)} errores en el dataset")

    # Estadísticas
    longitudes = [len(ej["instruction"]) + len(ej["output"]) for ej in data]
    logger.info(f"  Longitud promedio: {sum(longitudes) // len(longitudes)} chars")
    logger.info(f"  Ejemplo más largo: {max(longitudes)} chars")
    logger.info(f"  Ejemplo más corto: {min(longitudes)} chars")

    # Cobertura de operaciones fractales
    ops = ["SUM", "IF", "LOOP", "SPAWN", "FOLD", "LINK", "EVOLVE"]
    logger.info("  Cobertura de operaciones fractales:")
    for op in ops:
        count = sum(1 for ej in data if op in ej["output"])
        pct   = count / len(data) * 100
        barra = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        logger.info(f"    {op:8} [{barra}] {count}/{len(data)} ({pct:.0f}%)")

    return data

# ─────────────────────────────────────────────────────────────────────────────
# FORMATEAR EJEMPLOS (Qwen2.5 usa ChatML)
# ─────────────────────────────────────────────────────────────────────────────
def formatear_ejemplo_qwen(instruccion: str, output: str) -> str:
    """
    Formato ChatML usado por Qwen2.5.
    El tokenizador de Qwen conoce estos tokens especiales.
    """
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{instruccion}<|im_end|>\n"
        f"<|im_start|>assistant\n{output}<|im_end|>"
    )

def formatear_ejemplo_gemma(instruccion: str, output: str) -> str:
    """Formato usado por Gemma3."""
    return (
        f"<start_of_turn>user\n{instruccion}<end_of_turn>\n"
        f"<start_of_turn>model\n{output}<end_of_turn>"
    )

def formatear_ejemplo(modelo_key: str, instruccion: str, output: str) -> str:
    """Selecciona el formato correcto según el modelo."""
    if "qwen" in modelo_key.lower():
        return formatear_ejemplo_qwen(instruccion, output)
    elif "gemma" in modelo_key.lower():
        return formatear_ejemplo_gemma(instruccion, output)
    else:
        return formatear_ejemplo_qwen(instruccion, output)  # default a ChatML

# ─────────────────────────────────────────────────────────────────────────────
# PREPARAR DATASET PARA HUGGINGFACE TRAINER
# ─────────────────────────────────────────────────────────────────────────────
def preparar_dataset_hf(data: list, modelo_key: str, tokenizer, max_length: int):
    """
    Convierte el dataset JSON al formato que espera el HuggingFace Trainer.
    Tokeniza en el momento de carga para detectar ejemplos demasiado largos.
    """
    from datasets import Dataset

    ejemplos_formateados = []
    ejemplos_truncados   = 0

    for ej in data:
        texto = formatear_ejemplo(modelo_key, ej["instruction"], ej["output"])

        # Pre-tokenizar para verificar longitud
        tokens = tokenizer(texto, truncation=False)
        n_tokens = len(tokens["input_ids"])

        if n_tokens > max_length:
            ejemplos_truncados += 1

        ejemplos_formateados.append({"text": texto})

    if ejemplos_truncados > 0:
        logger.warning(f"  ⚠ {ejemplos_truncados} ejemplos exceden {max_length} tokens — serán truncados")
        logger.warning(f"    Considera reducir --max-seq-length si son muchos")

    logger.info(f"  ✓ {len(ejemplos_formateados)} ejemplos formateados para entrenamiento")

    return Dataset.from_list(ejemplos_formateados)

# ─────────────────────────────────────────────────────────────────────────────
# CALLBACK DE PROGRESO — muestra ETA real durante el entrenamiento
# ─────────────────────────────────────────────────────────────────────────────
class ArkaniProgressCallback(TrainerCallback):
    """Callback que muestra progreso detallado y estimación de tiempo."""

    def __init__(self, total_steps: int):
        self.total_steps  = total_steps
        self.inicio       = time.time()
        self.ultimo_log   = time.time()

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return

        paso_actual  = state.global_step
        transcurrido = time.time() - self.inicio

        if paso_actual > 0:
            seg_por_step = transcurrido / paso_actual
            pasos_restantes = self.total_steps - paso_actual
            eta_seg  = seg_por_step * pasos_restantes
            eta_str  = str(timedelta(seconds=int(eta_seg)))
            pct      = paso_actual / self.total_steps * 100

            loss_str = f"loss={logs.get('loss', 0):.4f}" if 'loss' in logs else ""
            lr_str   = f"lr={logs.get('learning_rate', 0):.2e}" if 'learning_rate' in logs else ""

            barra_len = 30
            lleno     = int(barra_len * pct / 100)
            barra     = "█" * lleno + "░" * (barra_len - lleno)

            logger.info(
                f"  [{barra}] {pct:.1f}% | "
                f"Step {paso_actual}/{self.total_steps} | "
                f"{loss_str} {lr_str} | "
                f"ETA: {eta_str}"
            )

# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL DE ENTRENAMIENTO
# ─────────────────────────────────────────────────────────────────────────────
def entrenar(
    modelo_key:   str,
    dataset_path: str,
    output_name:  str  = "arkani-fractal",
    reanudar:     bool = False,
    max_seq_len:  int  = None,
    epochs:       int  = None,
    lora_r:       int  = None,
):
    """
    Pipeline completo de fine-tuning para CPU.
    Sin Unsloth, sin bitsandbytes, sin CUDA.
    """
    from transformers import (
        TrainerCallback,
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        Trainer,
        DataCollatorForLanguageModeling,
    )
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    import torch

    # Override de config si se pasaron argumentos
    cfg = dict(CONFIG)
    if max_seq_len: cfg["max_seq_length"]   = max_seq_len
    if epochs:      cfg["num_epochs"]       = epochs
    if lora_r:
        cfg["lora_r"]     = lora_r
        cfg["lora_alpha"] = lora_r * 2  # lora_alpha = 2×lora_r es regla estándar

    output_lora   = Path(f"./{output_name}-lora")
    output_merged = Path(f"./{output_name}-merged")

    # ── Banner ───────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("  ARKANI FRACTAL FINE-TUNING v2.0")
    logger.info("  Protocolo Wardenclyffe — CPU Edition")
    logger.info("=" * 60)
    logger.info(f"  Modelo:     {modelo_key}")
    logger.info(f"  Dataset:    {dataset_path}")
    logger.info(f"  LoRA r={cfg['lora_r']}, alpha={cfg['lora_alpha']}")
    logger.info(f"  Seq len:    {cfg['max_seq_length']} tokens")
    logger.info(f"  Épocas:     {cfg['num_epochs']}")
    logger.info(f"  Batch ef.:  {cfg['batch_size'] * cfg['grad_accumulation']}")
    logger.info(f"  Output:     {output_lora}")
    logger.info("")

    # ── 1. Verificaciones ────────────────────────────────────────────────────
    logger.info("1. Verificando dependencias...")
    if not verificar_dependencias():
        return

    if modelo_key not in MODELOS_SOPORTADOS:
        logger.error(f"Modelo no soportado: {modelo_key}")
        logger.error(f"Opciones: {list(MODELOS_SOPORTADOS.keys())}")
        return

    logger.info("2. Verificando RAM...")
    if not verificar_ram(modelo_key):
        return

    # ── 2. Cargar dataset ────────────────────────────────────────────────────
    logger.info("3. Cargando dataset fractal...")
    data = cargar_dataset(dataset_path)

    # ── 3. Cargar tokenizador ────────────────────────────────────────────────
    repo_hf = MODELOS_SOPORTADOS[modelo_key][0]
    logger.info(f"4. Cargando tokenizador: {repo_hf}")
    logger.info("   (primera vez: descarga ~500MB desde HuggingFace — requiere internet)")

    tokenizer = AutoTokenizer.from_pretrained(
        repo_hf,
        trust_remote_code=True,
        padding_side="right",   # right padding para causal LM
    )

    # Qwen2.5 a veces no tiene pad_token definido
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("   ✓ pad_token seteado a eos_token")

    logger.info(f"   ✓ Vocabulario: {tokenizer.vocab_size:,} tokens")

    # ── 4. Preparar dataset ──────────────────────────────────────────────────
    logger.info("5. Preparando dataset...")
    dataset_hf = preparar_dataset_hf(data, modelo_key, tokenizer, cfg["max_seq_length"])

    # Split 95/5 train/eval
    split       = dataset_hf.train_test_split(test_size=0.05, seed=cfg["seed"])
    train_data  = split["train"]
    eval_data   = split["test"]
    logger.info(f"   ✓ Train: {len(train_data)} | Eval: {len(eval_data)}")

    # ── 5. Cargar modelo base ────────────────────────────────────────────────
    logger.info(f"6. Cargando modelo base en FP32 para CPU...")
    logger.info(f"   NOTA: primera vez descarga ~{MODELOS_SOPORTADOS[modelo_key][1]*2:.0f}GB")

    # Detectar checkpoint para reanudar
    checkpoint_path = None
    if reanudar and output_lora.exists():
        checkpoints = sorted(output_lora.glob("checkpoint-*"),
                             key=lambda p: int(p.name.split("-")[1]))
        if checkpoints:
            checkpoint_path = str(checkpoints[-1])
            logger.info(f"   ✓ Reanudando desde: {checkpoint_path}")

    modelo = AutoModelForCausalLM.from_pretrained(
        repo_hf,
        torch_dtype=torch.float32,   # FP32 obligatorio en CPU
        trust_remote_code=True,
        low_cpu_mem_usage=True,       # carga el modelo en fragmentos para ahorrar RAM pico
    )

    # Contar parámetros del modelo base
    params_total = sum(p.numel() for p in modelo.parameters())
    logger.info(f"   ✓ Parámetros totales: {params_total / 1e6:.0f}M")

    # ── 6. Aplicar LoRA ──────────────────────────────────────────────────────
    logger.info("7. Aplicando LoRA (adaptadores fractales)...")

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=cfg["lora_r"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=cfg["lora_dropout"],
        target_modules=cfg["lora_target"],
        bias="none",
        inference_mode=False,
    )

    modelo = get_peft_model(modelo, lora_config)

    # Mostrar parámetros entrenables vs congelados
    params_entrenables = sum(p.numel() for p in modelo.parameters() if p.requires_grad)
    params_congelados  = sum(p.numel() for p in modelo.parameters() if not p.requires_grad)
    pct_entrenables    = params_entrenables / (params_entrenables + params_congelados) * 100

    logger.info(f"   ✓ Parámetros entrenables: {params_entrenables:,} ({pct_entrenables:.2f}%)")
    logger.info(f"   ✓ Parámetros congelados:  {params_congelados:,}")
    logger.info(f"   ↳ Solo entrenamos el {pct_entrenables:.2f}% — por eso cabe en CPU")

    # ── 7. Configurar Trainer ────────────────────────────────────────────────
    logger.info("8. Configurando Trainer para CPU...")

    total_steps = (len(train_data) // cfg["batch_size"] // cfg["grad_accumulation"]) * cfg["num_epochs"]
    logger.info(f"   Steps totales: {total_steps}")
    eta_min = total_steps * 8  # ~8 segundos/step en i5-8350U con LoRA 0.5B
    logger.info(f"   ETA estimada:  {eta_min // 60}h {eta_min % 60}m (puede variar)")

    training_args = TrainingArguments(
        # Output
        output_dir=str(output_lora),

        # Épocas y batch
        num_train_epochs=cfg["num_epochs"],
        per_device_train_batch_size=cfg["batch_size"],
        per_device_eval_batch_size=cfg["batch_size"],
        gradient_accumulation_steps=cfg["grad_accumulation"],

        # Optimizador CPU — adamw_torch es el correcto (NO adamw_8bit que requiere CUDA)
        optim=cfg["optim"],
        learning_rate=cfg["learning_rate"],
        warmup_ratio=cfg["warmup_ratio"],
        lr_scheduler_type=cfg["lr_scheduler"],
        weight_decay=0.01,

        # Precisión — FP32 obligatorio en CPU
        fp16=cfg["fp16"],   # False
        bf16=cfg["bf16"],   # False

        # Evaluación
        eval_strategy="steps",
        eval_steps=cfg["save_steps"],

        # Checkpoints
        save_strategy="steps",
        save_steps=cfg["save_steps"],
        save_total_limit=cfg["save_total_limit"],
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",

        # Logging
        logging_steps=cfg["logging_steps"],
        logging_dir=str(Path("./arkani_logs")),
        report_to="none",         # sin WandB ni TensorBoard

        # CPU-específico
        use_cpu=True,             # forzar CPU aunque detecte CUDA (por si acaso)
        dataloader_num_workers=cfg["dataloader_workers"],
           # pin_memory solo mejora velocidad con GPU

        # Reproducibilidad
        seed=cfg["seed"],
        data_seed=cfg["seed"],

        # Gradient checkpointing — ahorra ~40% de RAM a costa de ~20% más tiempo
        gradient_checkpointing=True,
    )

    # Data collator — maneja padding dinámico
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,          # Causal LM, no Masked LM
        pad_to_multiple_of=8,
    )

    # Función de tokenización para el Trainer
    def tokenizar(ejemplos):
        result = tokenizer(
            ejemplos["text"],
            truncation=True,
            max_length=cfg["max_seq_length"],
            padding=False,    # padding dinámico via DataCollator
        )
        result["labels"] = result["input_ids"].copy()  # autoregressive: label = input
        return result

    train_tokenizado = train_data.map(tokenizar, batched=True, remove_columns=["text"])
    eval_tokenizado  = eval_data.map(tokenizar,  batched=True, remove_columns=["text"])

    # Callback de progreso
    progress_cb = ArkaniProgressCallback(total_steps)

    trainer = Trainer(
        model=modelo,
        args=training_args,
        train_dataset=train_tokenizado,
        eval_dataset=eval_tokenizado,
        data_collator=data_collator,
        callbacks=[progress_cb],
    )

    # ── 8. Entrenar ──────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("  INICIANDO ENTRENAMIENTO FRACTAL")
    logger.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    logger.info("  Ctrl+C para pausar — se guarda el último checkpoint")
    logger.info("  Reanudar con: python3 arkani_finetune_v2.py --reanudar")
    logger.info("")

    try:
        trainer.train(resume_from_checkpoint=checkpoint_path)
        logger.info("\n✓ Entrenamiento completado")
    except KeyboardInterrupt:
        logger.info("\n⚠ Entrenamiento pausado por el usuario")
        logger.info("  Guardando checkpoint de emergencia...")
        trainer.save_model(str(output_lora / "checkpoint-emergencia"))
        logger.info(f"  ✓ Checkpoint guardado en {output_lora / 'checkpoint-emergencia'}")
        logger.info(f"  Reanudar con: python3 arkani_finetune_v2.py --reanudar")
        return

    # ── 9. Guardar adaptadores LoRA ──────────────────────────────────────────
    logger.info("9. Guardando adaptadores LoRA...")
    modelo.save_pretrained(str(output_lora))
    tokenizer.save_pretrained(str(output_lora))
    logger.info(f"   ✓ Adaptadores guardados en: {output_lora}")

    # ── 10. Fusionar LoRA con modelo base → modelo completo ──────────────────
    logger.info("10. Fusionando LoRA con modelo base...")
    logger.info("    (esto puede tardar ~5 minutos en CPU)")

    try:
        # Cargar modelo base limpio para fusionar
        modelo_base = AutoModelForCausalLM.from_pretrained(
            repo_hf,
            torch_dtype=torch.float32,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        modelo_fusionado = PeftModel.from_pretrained(modelo_base, str(output_lora))
        modelo_fusionado = modelo_fusionado.merge_and_unload()  # fusionar y eliminar overhead LoRA

        output_merged.mkdir(parents=True, exist_ok=True)
        modelo_fusionado.save_pretrained(str(output_merged))
        tokenizer.save_pretrained(str(output_merged))
        logger.info(f"    ✓ Modelo fusionado guardado en: {output_merged}")

    except Exception as e:
        logger.warning(f"    ⚠ No se pudo fusionar: {e}")
        logger.warning(f"    Los adaptadores LoRA están disponibles en: {output_lora}")
        logger.warning(f"    Puedes fusionar más tarde con: python3 arkani_finetune_v2.py --solo-fusionar")

    # ── 11. Exportar a Ollama ────────────────────────────────────────────────
    exportar_a_ollama(output_merged if output_merged.exists() else output_lora, output_name)

    logger.info("")
    logger.info("=" * 60)
    logger.info("  ✓ ARKANI FRACTAL FINE-TUNING COMPLETADO")
    logger.info(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR A OLLAMA
# ─────────────────────────────────────────────────────────────────────────────
def exportar_a_ollama(modelo_dir: Path, nombre: str):
    """
    Genera el Modelfile para registrar el modelo en Ollama.
    Nota: Ollama requiere formato GGUF. Esta función genera el Modelfile
    asumiendo que harás la conversión con llama.cpp cuando tengas el servidor GPU.
    """
    logger.info("11. Generando Modelfile para Ollama...")

    # Ruta al GGUF (se generará con llama.cpp en el servidor GPU)
    gguf_nombre = f"{nombre}-Q4_K_M.gguf"

    modelfile_content = f"""# Modelfile generado por ARKANI Fine-tuning v2.0
# Protocolo Wardenclyffe

FROM ./{gguf_nombre}

# Parámetros de generación optimizados para lenguaje fractal
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER repeat_penalty 1.15
PARAMETER num_ctx 4096
PARAMETER num_predict 512
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM \"\"\"{SYSTEM_PROMPT}\"\"\"

# Para registrar en Ollama (cuando tengas el .gguf):
# ollama create {nombre}:latest -f Modelfile_arkani_fractal
#
# Para convertir a GGUF con llama.cpp:
# python3 convert_hf_to_gguf.py {modelo_dir} --outtype q4_k_m --outfile {gguf_nombre}
#
# Para probar:
# ollama run {nombre}:latest "hola, quien eres?"
"""

    modelfile_path = Path(f"Modelfile_arkani_fractal")
    modelfile_path.write_text(modelfile_content, encoding="utf-8")

    logger.info(f"    ✓ Modelfile generado: {modelfile_path}")
    logger.info(f"")
    logger.info(f"    PRÓXIMOS PASOS:")
    logger.info(f"    1. En el servidor GPU (cuando llegue):")
    logger.info(f"       python3 convert_hf_to_gguf.py {modelo_dir} --outtype q4_k_m --outfile {gguf_nombre}")
    logger.info(f"    2. Registrar en Ollama:")
    logger.info(f"       ollama create {nombre}:latest -f Modelfile_arkani_fractal")
    logger.info(f"    3. Probar:")
    logger.info(f"       ollama run {nombre}:latest 'hola quien eres'")


# ─────────────────────────────────────────────────────────────────────────────
# VERIFICACIÓN SIN ENTRENAR
# ─────────────────────────────────────────────────────────────────────────────
def verificar_dataset_solo(dataset_path: str):
    """Verifica el dataset y muestra ejemplos sin entrenar nada."""
    logger.info("\nMODO VERIFICACIÓN — no se entrena nada\n")

    data = cargar_dataset(dataset_path)

    logger.info(f"\nPrimeros 3 ejemplos:")
    logger.info("-" * 50)
    for i, ej in enumerate(data[:3]):
        logger.info(f"\n[Ejemplo {i+1}]")
        logger.info(f"INSTRUCCIÓN: {ej['instruction'][:100]}...")
        logger.info(f"OUTPUT:      {ej['output'][:200]}...")

    logger.info(f"\n✓ Dataset válido — {len(data)} ejemplos listos")
    logger.info(f"\nPara entrenar en CPU (recomendado, de noche):")
    logger.info(f"  python3 arkani_finetune_v2.py --modelo qwen2.5:0.5b --dataset {dataset_path}")
    logger.info(f"\nETA estimada en VM (8GB RAM, 4 CPUs):")
    logger.info(f"  qwen2.5:0.5b — ~10 horas con LoRA r=16")
    logger.info(f"  qwen2.5:1.5b — ~30 horas con LoRA r=16")


# ─────────────────────────────────────────────────────────────────────────────
# FUSIONAR LORA CON MODELO BASE (modo independiente)
# ─────────────────────────────────────────────────────────────────────────────
def fusionar_lora(lora_dir: str, output_name: str):
    """Fusiona los adaptadores LoRA con el modelo base."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    import torch

    lora_path = Path(lora_dir)
    if not lora_path.exists():
        logger.error(f"Directorio LoRA no encontrado: {lora_dir}")
        return

    # Detectar modelo base desde config de LoRA
    adapter_config = json.loads((lora_path / "adapter_config.json").read_text())
    base_model_name = adapter_config.get("base_model_name_or_path", "")

    logger.info(f"Fusionando LoRA de {lora_dir} con base {base_model_name}...")

    tokenizer    = AutoTokenizer.from_pretrained(str(lora_path), trust_remote_code=True)
    modelo_base  = AutoModelForCausalLM.from_pretrained(base_model_name, torch_dtype=torch.float32,
                                                         trust_remote_code=True, low_cpu_mem_usage=True)
    modelo_peft  = PeftModel.from_pretrained(modelo_base, str(lora_path))
    modelo_final = modelo_peft.merge_and_unload()

    output_path  = Path(f"./{output_name}-merged")
    output_path.mkdir(parents=True, exist_ok=True)
    modelo_final.save_pretrained(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    logger.info(f"✓ Modelo fusionado en: {output_path}")
    exportar_a_ollama(output_path, output_name)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ARKANI Fractal Fine-tuning v2 — CPU Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EJEMPLOS DE USO:
  # Verificar el dataset sin entrenar nada:
  python3 arkani_finetune_v2.py --solo-verificar

  # Entrenar (recomendado, dejar de noche):
  python3 arkani_finetune_v2.py --modelo qwen2.5:0.5b --dataset arkani_fractal_dataset_v2.json

  # Reanudar entrenamiento interrumpido:
  python3 arkani_finetune_v2.py --modelo qwen2.5:0.5b --reanudar

  # Fusionar LoRA con modelo base (después de entrenar):
  python3 arkani_finetune_v2.py --solo-fusionar --lora-dir ./arkani-fractal-lora

  # Modelo más grande si tienes RAM:
  python3 arkani_finetune_v2.py --modelo qwen2.5:1.5b --dataset arkani_fractal_dataset_v2.json
        """
    )

    parser.add_argument("--modelo",
                        default="qwen2.5:0.5b",
                        choices=list(MODELOS_SOPORTADOS.keys()),
                        help="Modelo base (default: qwen2.5:0.5b — recomendado para VM 8GB)")

    parser.add_argument("--dataset",
                        default="arkani_fractal_dataset_v2.json",
                        help="Ruta al dataset fractal JSON")

    parser.add_argument("--output",
                        default="arkani-fractal",
                        help="Nombre base para los archivos de salida")

    parser.add_argument("--reanudar",
                        action="store_true",
                        help="Reanudar desde el último checkpoint guardado")

    parser.add_argument("--solo-verificar",
                        action="store_true",
                        help="Solo verifica el dataset sin entrenar")

    parser.add_argument("--solo-fusionar",
                        action="store_true",
                        help="Solo fusiona LoRA con modelo base (necesita --lora-dir)")

    parser.add_argument("--lora-dir",
                        default="./arkani-fractal-lora",
                        help="Directorio con los adaptadores LoRA (para --solo-fusionar)")

    parser.add_argument("--max-seq-length",
                        type=int,
                        default=None,
                        help=f"Override longitud máxima de secuencia (default: {CONFIG['max_seq_length']})")

    parser.add_argument("--epochs",
                        type=int,
                        default=None,
                        help=f"Override número de épocas (default: {CONFIG['num_epochs']})")

    parser.add_argument("--lora-r",
                        type=int,
                        default=None,
                        help=f"Override rango LoRA (default: {CONFIG['lora_r']}). Menor=más rápido.")

    args = parser.parse_args()

    if args.solo_verificar:
        verificar_dataset_solo(args.dataset)

    elif args.solo_fusionar:
        fusionar_lora(args.lora_dir, args.output)

    else:
        entrenar(
            modelo_key=args.modelo,
            dataset_path=args.dataset,
            output_name=args.output,
            reanudar=args.reanudar,
            max_seq_len=args.max_seq_length,
            epochs=args.epochs,
            lora_r=args.lora_r,
        )


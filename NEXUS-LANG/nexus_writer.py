import os

def arkani_write_code(module_name, code_content):
    path = os.path.expanduser(f"~/NEXUS/NEXUS-LANG/autogen/{module_name}.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    header = "# --- NEXUS-LANG AUTO-GENERATED CODE ---\n# Arkani-Simbiosis Activa\n\n"
    with open(path, "w") as f:
        f.write(header + code_content)
    
    print(f"🧬 [AUTO-PROGRAMACIÓN]: Módulo '{module_name}' escrito con éxito.")
    return path

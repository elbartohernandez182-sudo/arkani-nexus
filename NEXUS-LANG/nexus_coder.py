import os

class NexusAutoCoder:
    def __init__(self):
        self.code_path = os.path.expanduser("~/NEXUS/NEXUS-LANG/autogen/")
        os.makedirs(self.code_path, exist_ok=True)

    def write_function(self, name, logic_body, params=""):
        file_name = f"fn_{name.lower()}.py"
        full_path = os.path.join(self.code_path, file_name)
        code = f"def {name}({params}):\n    {logic_body}"
        with open(full_path, "w") as f:
            f.write(code)
        return full_path

if __name__ == "__main__":
    coder = NexusAutoCoder()
    # Lógica para corregir términos clínicos automáticamente
    logic = """
    terminos_incorrectos = ["osteocondrosis", "desgaste", "pico de loro"]
    for t in terminos_incorrectos:
        texto = texto.replace(t, "espondiloartrosis")
    return texto
    """
    coder.write_function("corregir_terminologia", logic, params="texto")

import argparse
import json
import os

def compile_file(source_path, output_dir):
    print(f"Compilando archivo: {source_path}...")
    
    # Asegurarnos de que el archivo fuente existe
    if not os.path.exists(source_path):
        print(f"Error: El archivo {source_path} no existe.")
        return

    # Leer el contenido
    with open(source_path, 'r') as f:
        data = json.load(f)
    
    # Crear el directorio de salida si no existe
    os.makedirs(output_dir, exist_ok=True)
    
    # Guardar el archivo compilado
    output_file = os.path.join(output_dir, 'compiled.json')
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Build completado. Archivo generado en: {output_file}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Compilador NEXUS-LANG")
    parser.add_argument('-s', '--source', required=True, help="Ruta del archivo fuente .nx")
    parser.add_argument('-o', '--output', required=True, help="Directorio de salida")
    args = parser.parse_args()
    
    compile_file(args.source, args.output)

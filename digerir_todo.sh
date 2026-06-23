#!/bin/bash
DIGESTOR="python3 /home/arkani/NEXUS/NEXUS-LANG/fractal_motor/digestion_fractal.py"
MEMORIA="/home/arkani/NEXUS/memoria_permanente"
LOG="/home/arkani/NEXUS/logs/digestion_completa.log"

archivos=(
"20260618_083706_python_decoradores_historia_de_python.txt"
"20260618_083706_python_decoradores_python.txt"
"20260618_124338_python_decoradores_avanzados_mojo__lenguaje_de_pro.txt"
"20260618_130321_radiologia_dicom_python_real_python__radiologia_di.txt"
"20260618_133415_pydicom_dataset_dicom_python_real_python__pydicom_.txt"
"20260618_134524_dicom_estandar_radiologia_imagen_m_dica.txt"
"20260618_134524_dicom_estandar_radiologia_telemedicina.txt"
"20260618_134524_dicom_estandar_radiologia_telepatolog_a.txt"
"20260618_135538_tac_tomografia_computarizada_radiologia_radiolog_a.txt"
"20260618_135538_tac_tomografia_computarizada_radiologia_tomograf_a.txt"
"20260618_140719_pydicom_github_io.txt"
"20260618_145735_es_wikipedia_org.txt"
"20260618_145736_es_wikipedia_org.txt"
)

echo "Iniciando: $(date)" >> $LOG
for i in "${!archivos[@]}"; do
    echo "[$((i+1))/${#archivos[@]}] ${archivos[$i]}" >> $LOG
    if [ $i -gt 0 ] && [ $((i % 3)) -eq 0 ]; then
        echo "Reiniciando Ollama..." >> $LOG
        sudo systemctl restart ollama
        sleep 20
    fi
    $DIGESTOR --libro "$MEMORIA/${archivos[$i]}" --silencioso >> $LOG 2>&1
    sleep 5
done
echo "Completado: $(date)" >> $LOG

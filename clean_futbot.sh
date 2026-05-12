#!/bin/bash

PROJECT=~/futbot-v3

echo "🧹 Limpiando proyecto en $PROJECT..."

# Python cache
find $PROJECT -type d -name "__pycache__" -exec rm -rf {} +
find $PROJECT -type f -name "*.pyc" -delete

# Node / basura JS
rm -rf $PROJECT/**/node_modules 2>/dev/null
rm -rf $PROJECT/**/.opencode 2>/dev/null

# Archivos generados raros
find $PROJECT -type f -name "*.data.json" -delete
find $PROJECT -type f -name "*.meta.json" -delete


# Tests pesados (opcional)

# Logs y temporales
find $PROJECT -type f -name "*.log" -delete
find $PROJECT -type f -name "*.aux" -delete
find $PROJECT -type f -name "*.out" -delete

echo "✅ Limpieza completa."

#!/usr/bin/env bash
# Sincroniza la version de version.py hacia buildozer.spec.
# version.py es la fuente de verdad: la app la lee en pantalla y el
# actualizador la compara con latest.json; buildozer solo debe seguirla.
#
#   bash scripts/sync_version.sh
set -euo pipefail

cd "$(dirname "$0")/.."

version=$(sed -n 's/^VERSION *= *"\(.*\)".*/\1/p' version.py)
codigo=$(sed -n 's/^VERSION_CODE *= *\([0-9][0-9]*\).*/\1/p' version.py)

if [ -z "$version" ] || [ -z "$codigo" ]; then
    echo "No se pudo leer VERSION/VERSION_CODE de version.py" >&2
    exit 1
fi

sed -i "s/^version *= *.*/version = $version/" buildozer.spec
# versionCode del APK: version.py VERSION_CODE es la fuente de verdad.
sed -i "s/^android\.numeric_version *= *.*/android.numeric_version = $codigo/" buildozer.spec

echo "version.py     -> VERSION=$version  VERSION_CODE=$codigo"
grep -nE '^(version|android\.numeric_version) *= *' buildozer.spec

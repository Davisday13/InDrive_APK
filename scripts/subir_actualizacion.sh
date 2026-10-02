#!/usr/bin/env bash
# Sube el APK y latest.json al bucket publico 'apk' de Supabase para que
# las instaladas descubran la actualizacion en un toque.
#
#   export SUPABASE_SERVICE_KEY="sb_secret_..."        # preferido
#   # o bien:
#   export SUPABASE_EMAIL="davis.fernandez@oteima.ac.pa"
#   export SUPABASE_PASSWORD="..."
#
#   bash scripts/subir_actualizacion.sh [ruta-del-apk]
#
# Nada de esto se guarda en el repositorio: van por variable de entorno.
set -euo pipefail

SUPABASE_URL="https://lbhsbbwtmljzqoyrkcxj.supabase.co"
SUPABASE_KEY="sb_publishable_GuSF7A9pz9w0YPxlzOmuhg_Tqa2U9Q4"
BUCKET="apk"

cd "$(dirname "$0")/.."

version=$(sed -n 's/^VERSION *= *"\(.*\)".*/\1/p' version.py)
codigo=$(sed -n 's/^VERSION_CODE *= *\([0-9][0-9]*\).*/\1/p' version.py)
nota=$(sed -n 's/^NOTA *= *"\(.*\)".*/\1/p' version.py)

if [ -z "$version" ] || [ -z "$codigo" ]; then
    echo "No se pudo leer version.py" >&2
    exit 1
fi

# ---------------------------------------------------------------- APK ----
apk="${1:-}"
if [ -z "$apk" ]; then
    for candidato in \
        "bin/InDrive-Finanzas-$version.apk" \
        "$HOME/InDrive_APK/bin/indrive_finanzas-$version-arm64-v8a-debug.apk"
    do
        if [ -f "$candidato" ]; then
            apk="$candidato"
            break
        fi
    done
fi
if [ -z "$apk" ] || [ ! -f "$apk" ]; then
    apk=$(ls -1t bin/*.apk "$HOME"/InDrive_APK/bin/*.apk 2>/dev/null | head -n 1 || true)
fi
if [ -z "$apk" ] || [ ! -f "$apk" ]; then
    echo "No se encontro el APK. Compila antes o pasa la ruta: " >&2
    echo "  bash scripts/subir_actualizacion.sh ruta/al.apk" >&2
    exit 1
fi

nombre=$(basename "$apk")
peso=$(wc -c < "$apk" | tr -d ' ')
resumen=$(sha256sum "$apk" | cut -d' ' -f1)

# ------------------------------------------------------------ sesion ----
token="${SUPABASE_SERVICE_KEY:-}"
if [ -z "$token" ]; then
    if [ -z "${SUPABASE_EMAIL:-}" ] || [ -z "${SUPABASE_PASSWORD:-}" ]; then
        echo "Falta SUPABASE_SERVICE_KEY (o SUPABASE_EMAIL y SUPABASE_PASSWORD)." >&2
        exit 1
    fi
    token=$(curl -s -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
        -H "apikey: $SUPABASE_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$SUPABASE_EMAIL\",\"password\":\"$SUPABASE_PASSWORD\"}" \
        | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("access_token", ""))
except Exception:
    print("")')
    if [ -z "$token" ]; then
        echo "No se pudo iniciar sesion en Supabase." >&2
        exit 1
    fi
fi

# --------------------------------------------------------- APK publico ----
echo "Subiendo $nombre ($peso bytes, sha256 ${resumen:0:12}...) ..."
http=$(curl -s -o /tmp/_indrive_upload.out -w '%{http_code}' \
    -X PUT "$SUPABASE_URL/storage/v1/object/$BUCKET/$nombre" \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/vnd.android.package-archive" \
    -H "x-upsert: true" \
    --data-binary "@$apk")
if [ "$http" != "200" ] && [ "$http" != "201" ]; then
    echo "Fallo la subida del APK (HTTP $http):" >&2
    cat /tmp/_indrive_upload.out >&2
    exit 1
fi

# ------------------------------------------------------- latest.json ----
json=$(python3 - "$version" "$codigo" "$nombre" "$nota" "$resumen" "$peso" <<'PY'
import json, sys
v, c, a, n, s, p = sys.argv[1:7]
print(json.dumps({
    "version": v,
    "version_code": int(c),
    "apk": a,
    "nota": n,
    "sha256": s,
    "peso": int(p),
}, ensure_ascii=False))
PY
)

echo "Publicando latest.json -> $json"
http=$(curl -s -o /tmp/_indrive_upload.out -w '%{http_code}' \
    -X PUT "$SUPABASE_URL/storage/v1/object/$BUCKET/latest.json" \
    -H "Authorization: Bearer $token" \
    -H "Content-Type: application/json" \
    -H "x-upsert: true" \
    --data-binary "$json")
if [ "$http" != "200" ] && [ "$http" != "201" ]; then
    echo "Fallo la subida de latest.json (HTTP $http):" >&2
    cat /tmp/_indrive_upload.out >&2
    exit 1
fi

# ----------------------------------------------------------- verificacion ----
echo "Verificando lectura publica (sin sesion) ..."
publico=$(curl -s "$SUPABASE_URL/storage/v1/object/public/$BUCKET/latest.json")
if ! printf '%s' "$publico" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d.get("version_code"), "latest.json sin version_code"
assert d.get("apk"), "latest.json sin apk"
'; then
    echo "latest.json no es legible publicamente: $publico" >&2
    exit 1
fi

echo "Verificando que el APK publico pesa lo mismo ..."
http=$(curl -s -o /tmp/_indrive_check.apk -w '%{http_code}' \
    "$SUPABASE_URL/storage/v1/object/public/$BUCKET/$nombre")
real=$(wc -c < /tmp/_indrive_check.apk | tr -d ' ')
if [ "$http" != "200" ] || [ "$real" != "$peso" ]; then
    echo "El APK publico no coincide (HTTP $http, $real bytes, esperado $peso)." >&2
    exit 1
fi
rm -f /tmp/_indrive_check.apk /tmp/_indrive_upload.out

echo
echo "OK: v$version (codigo $codigo) publicada."
echo "    https://lbhsbbwtmljzqoyrkcxj.supabase.co/storage/v1/object/public/$BUCKET/latest.json"
echo
echo "Para que el boton lo ofrezca hay que subir tambien un APK compilado"
echo "con el NUEVO version_code: versiones iguales no se ofrecen."

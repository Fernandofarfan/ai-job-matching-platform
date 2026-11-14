#!/usr/bin/env bash
# Baseline de OWASP ZAP (spider + reglas pasivas) sobre la app levantada, con la sesión de ZAP_EMAIL iniciada.
# Uso: ZAP_EMAIL=... ZAP_PASSWORD=... scripts/zap_scan.sh [http://127.0.0.1:5000] [carpeta de reportes]
# Sale con 1 si hay alertas FAIL y con 2 si hay WARN; las aceptadas van como IGNORE en .zap/rules.tsv.
set -euo pipefail
BASE=${1:-http://127.0.0.1:5000}
OUT=${2:-zap}
IMAGE=ghcr.io/zaproxy/zaproxy@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af

mkdir -p "$OUT" && chmod 777 "$OUT"
cp .zap/rules.tsv "$OUT/"

jar=$(mktemp)
trap 'rm -f "$jar"' EXIT
token=$(curl -sf -c "$jar" "$BASE/login" | grep -o 'name="csrf_token" value="[^"]*"' | head -1 | sed 's/.*value="//;s/"$//')
curl -sf -b "$jar" -c "$jar" -o /dev/null --data-urlencode "csrf_token=$token" \
  --data-urlencode "email=$ZAP_EMAIL" --data-urlencode "password=$ZAP_PASSWORD" "$BASE/login"
session=$(awk '$6 == "session" {print $7}' "$jar")
if [ "$(curl -s -o /dev/null -w '%{http_code}' -H "Cookie: session=$session" "$BASE/tracker")" != 200 ]; then
  echo "No se pudo iniciar sesión con ZAP_EMAIL" >&2
  exit 1
fi

# Cada pedido de ZAP lleva la cookie de sesión. El spider no manda formularios POST
# (borrarían datos) ni visita /logout ni /lang/, que cerrarían o cambiarían la sesión.
docker run --rm --network host -v "$(realpath "$OUT")":/zap/wrk:rw "$IMAGE" zap-baseline.py \
  -t "$BASE/" -m 3 -c rules.tsv -J report.json -r report.html -w report.md \
  -z "-config replacer.full_list(0).description=sesion -config replacer.full_list(0).enabled=true \
      -config replacer.full_list(0).matchtype=REQ_HEADER -config replacer.full_list(0).matchstr=Cookie \
      -config replacer.full_list(0).regex=false -config replacer.full_list(0).replacement=session=$session \
      -config spider.postform=false \
      -config globalexcludeurl.url_list.url(0).regex=^https?://[^/]+/(logout|lang/).*$ \
      -config globalexcludeurl.url_list.url(0).enabled=true"

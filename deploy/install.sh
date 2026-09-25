#!/bin/bash
# Installiert oder aktualisiert die Doichain REST API auf doi-btc-node.
# Erwartet den Quellcode unter /root/doichain-api-src (per tar/rsync hochgeladen).
# Idempotent und auch auf einem frischen Server lauffaehig: legt Benutzer, venv, Zertifikat,
# Umgebungsdatei (nur wenn sie fehlt) und Einzahlungsadresse an. Eine vorhandene Umgebungsdatei
# wird nie veraendert.
set -euo pipefail
SRC=${1:-/root/doichain-api-src}
BASE=/opt/doichain-api
APP=$BASE/app
VENV=$BASE/venv
ENV_FILE=/etc/doichain-api/doichain-api.env
CERT_DIR=/etc/ssl/doichain-api
DOI_CONF=/home/doichain/.doichain/doichain.conf

id doiapi >/dev/null 2>&1 || useradd --system --home-dir "$BASE" --shell /usr/sbin/nologin doiapi
install -d -o doiapi -g doiapi -m 0750 "$BASE"
install -d -o doiapi -g doiapi -m 0750 "$APP"
install -d -m 0755 /etc/doichain-api "$CERT_DIR"
[ -x "$VENV/bin/python" ] || sudo -u doiapi python3 -m venv "$VENV"

rsync -a --delete --exclude "__pycache__" "$SRC/doichain_api/" "$APP/doichain_api/"
install -m 0644 "$SRC/requirements.txt" "$APP/requirements.txt"
[ -f "$SRC/README.md" ] && install -m 0644 "$SRC/README.md" "$APP/README.md"
chown -R doiapi:doiapi "$BASE"
chmod -R o-rwx "$APP"
sudo -u doiapi "$VENV/bin/pip" install -q -r "$APP/requirements.txt"

# Uebergangszertifikat, bis certbot ein echtes holt.
if [ ! -f "$CERT_DIR/selfsigned.crt" ]; then
  IP=$(hostname -I | awk '{print $1}')
  openssl req -x509 -nodes -newkey rsa:2048 -days 730 -keyout "$CERT_DIR/selfsigned.key" -out "$CERT_DIR/selfsigned.crt" \
    -subj "/CN=doi-btc-node Doichain API" -addext "subjectAltName=IP:${IP},DNS:api.doi.zone,DNS:doi-api.sendlabs.de" >/dev/null 2>&1
  chmod 600 "$CERT_DIR/selfsigned.key"
fi

# Umgebungsdatei nur anlegen, wenn sie fehlt. RPC-Zugang aus doichain.conf, Schluessel neu erzeugt.
if [ ! -f "$ENV_FILE" ]; then
  RPCUSER=$(grep -E "^rpcuser=" "$DOI_CONF" 2>/dev/null | head -1 | cut -d= -f2- || true)
  RPCPW=$(grep -E "^rpcpassword=" "$DOI_CONF" 2>/dev/null | head -1 | cut -d= -f2- || true)
  umask 077
  printf "%s\n" \
    "# Doichain REST API, Umgebungsdatei. Keine Kopie in Notizen, Schluessel gehoeren nach Vaultwarden." \
    "DOI_RPC_URL=http://127.0.0.1:8339/" \
    "DOI_RPC_USER=${RPCUSER:-admin}" \
    "DOI_RPC_PASSWORD=${RPCPW:-BITTE-EINTRAGEN}" \
    "DOI_RPC_WALLET=doichain" \
    "DOI_ELECTRUM_HOST=127.0.0.1" \
    "DOI_ELECTRUM_PORT=50001" \
    "DOI_EXPLORER_URL=https://doi-explorer.le-space.de" \
    "DOI_PUBLIC_READ=true" \
    "DOI_API_KEYS_READ=" \
    "DOI_API_KEYS_WRITE=$(openssl rand -hex 24)" \
    "DOI_API_KEYS_ADMIN=$(openssl rand -hex 24)" \
    "DOI_POE_PREFIX=poe/" \
    "DOI_MAX_UPLOAD_BYTES=52428800" > "$ENV_FILE"
  chown root:doiapi "$ENV_FILE"; chmod 0640 "$ENV_FILE"
  echo "Umgebungsdatei $ENV_FILE neu angelegt (Schluessel dort ablesen und in Vaultwarden sichern)."
fi

# Einzahlungsadresse mit Label api-funding einmalig anlegen (nur wenn die Node erreichbar ist).
if command -v doichain-cli >/dev/null && [ -d /home/doichain/.doichain ]; then
  CLI="doichain-cli -datadir=/home/doichain/.doichain -rpcwallet=doichain"
  $CLI getaddressesbylabel api-funding >/dev/null 2>&1 || $CLI getnewaddress api-funding legacy >/dev/null 2>&1 || true
fi

# nginx: Versionsanzeige global abschalten (Ubuntu liefert die Zeile auskommentiert).
grep -qE "^\s*server_tokens\s+off;" /etc/nginx/nginx.conf || sed -i -E 's/^(\s*)#\s*server_tokens off;/\1server_tokens off;/' /etc/nginx/nginx.conf

install -m 0644 "$SRC/deploy/doichain-api.service" /etc/systemd/system/doichain-api.service
# nginx-Vorlage nur einspielen, solange certbot die Datei noch nicht angefasst hat. Sonst wuerde das
# echte Zertifikat beim naechsten API-Update durch das selbstsignierte ersetzt.
NGX=/etc/nginx/sites-available/doichain-api
if [ -f "$NGX" ] && grep -q "managed by Certbot" "$NGX"; then
  echo "HINWEIS: $NGX enthaelt certbot-Eintraege und bleibt unveraendert. Aenderungen aus deploy/nginx-doichain-api.conf bitte von Hand uebernehmen."
else
  install -m 0644 "$SRC/deploy/nginx-doichain-api.conf" "$NGX"
fi
ln -sf "$NGX" /etc/nginx/sites-enabled/doichain-api
nginx -t
systemctl daemon-reload
systemctl enable doichain-api.service >/dev/null 2>&1 || true
systemctl restart doichain-api.service
systemctl reload nginx
sleep 3
systemctl --no-pager --lines=0 status doichain-api.service | head -5
curl -s -m 15 http://127.0.0.1:8080/health; echo

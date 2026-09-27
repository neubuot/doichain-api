# Doichain API

REST-Schnittstelle vor einer Doichain-Node (Doichain Core v31.1.6). Stellt alle Doichain-Funktionen
über HTTP bereit: **Proof of Existence**, **`name_doi`** und die übrigen Namensoperationen, Blöcke,
Transaktionen, Mempool, Adressguthaben (über ElectrumX) und das Wallet der Node. Interaktive
Dokumentation (Swagger) unter `/docs`.

*English summary: a FastAPI service in front of Doichain Core v31.1.6 exposing proof of existence,
`name_doi` and all name operations, chain queries, address balances (via ElectrumX) and wallet functions
as a documented REST API with API-key tiers, nginx TLS termination and rate limiting. The manual
(`docs/Handbuch.md`) is in German.*

Produktivinstanz: Hetzner-Server `doi-btc-node`, **https://doi-api.sendlabs.de/** (Landingpage mit Spielwiese,
`/docs` Swagger, `/poe/` die Nachweis-App Verifile), Let's Encrypt, später zusätzlich `api.doi.zone`.
Betreiber: DOI Labs AG. Stand: Version 1.4.1, 26.09.2026.

**Neu in 1.4.0: MCP-Server für KI-Agenten** unter **https://doi-api.sendlabs.de/mcp**. Claude, ChatGPT, Cursor,
VS Code und jeder andere MCP-Client binden die Doichain mit dieser einen Adresse ein (Streamable HTTP, ohne Anmeldung)
und können Nachweise verankern und prüfen, Namen, Blöcke, Transaktionen und Adressen lesen. Im Browser zeigt dieselbe
Adresse die Landingpage mit Einbauanleitung.

Drei Web-Oberflächen liegen im Ordner `web/` und werden vom Installer mit ausgeliefert:

- **Verifile** (`web/verifile`): Proof of Existence für Endnutzer. Datei ins Feld ziehen, SHA-256 entsteht im Browser
  (kein Upload), ein Klick verankert den Hash in der Doichain, die Seite zeigt Blockzeit und Bestätigungen und liefert
  den Nachweis als JSON oder Druckansicht. Nutzt den eingeschränkten **poe**-Schlüssel mit Tageskontingent.
  Live unter **https://verifile.it/** (Let's Encrypt, `deploy/nginx-verifile.conf`), zusätzlich unter `/poe/` des API-Hosts.
- **Landingpage der API** (`web/api-site`): Erklärung, Live-Status der Node, Spielwiese für lesende Aufrufe,
  Codebeispiele und Links, ausgeliefert unter `/` des API-Hosts.
- **Landingpage des MCP-Servers** (`web/mcp-site`): Einbauanleitung für Claude Code, Claude, ChatGPT, Cursor und VS Code,
  Werkzeugliste, Sicherheit, FAQ, Deutsch und Englisch. nginx liefert sie aus, wenn ein Browser `/mcp` aufruft.

## Inhalt

- [Funktionen](#funktionen)
- [Architektur](#architektur)
- [Voraussetzungen](#voraussetzungen)
- [Installation auf dem Server](#installation-auf-dem-server)
- [Konfiguration](#konfiguration)
- [Zugriffsstufen](#zugriffsstufen)
- [Erste Aufrufe](#erste-aufrufe)
- [Proof of Existence](#proof-of-existence)
- [MCP-Server für KI-Agenten](#mcp-server-für-ki-agenten)
- [Betrieb](#betrieb)
- [Lokale Entwicklung](#lokale-entwicklung)
- [Projektstruktur](#projektstruktur)
- [Sicherheit](#sicherheit)
- [Dokumentation und Lizenz](#dokumentation-und-lizenz)

## Funktionen

| Bereich | Endpunkte (Auszug) |
|---|---|
| Status | `GET /health` (503 bei stehender Kette, fehlenden Headern, IBD oder Fork-Verstoß), `GET /v1/status` |
| Kette | `GET /v1/blocks`, `GET /v1/block/{höhe oder hash}`, `GET /v1/tx/{txid}` (mit dekodierten Namensoperationen), `POST /v1/tx/decode`, `POST /v1/tx/send`, `GET /v1/mempool`, `GET /v1/network` |
| Adressen | `GET /v1/address/{adresse}`, `/history`, `/utxos` für `N…`, `6…` und `dc1q…` |
| Namen | `GET /v1/name/{name}`, `/history`, `GET /v1/name?name=…` und `GET /v1/names/history?name=…` (eindeutig für jeden Namen), `GET /v1/names` (Blättern über `after`/`next_after`), `GET /v1/names/pending`, `POST /v1/name/doi`, `/update`, `/new`, `/firstupdate`, `/sendtoname` |
| Proof of Existence | `GET /v1/poe/{sha256}`, `POST /v1/poe/verify`, `POST /v1/poe/verify/file`, `POST /v1/poe`, `POST /v1/poe/file` (beide mit optionalem `reanchor` für abgelaufene Hashes) |
| Wallet | `GET /v1/wallet`, `/funding-address`, `/names`, `/transactions`, `/utxos`, `POST /v1/wallet/address`, `/abandon`, `/send` |
| Werkzeuge | `GET /v1/validate/{adresse}`, `POST /v1/message/verify`, `/sign`, `GET /v1/fee`, `POST /v1/rpc` (Durchgriff mit Sperrliste) |

Alle Fehler kommen einheitlich als `{"error": {"type": …, "code": …, "message": …}}`, auch die von nginx
erzeugten (413, 429, 502, 504). Schreibende Aufrufe prüfen nach dem Absenden, ob die Node die Transaktion
tatsächlich in den Mempool übernommen hat, und verwerfen sie sonst im Wallet.

## Architektur

```
Client (curl, Python, Browser, n8n, DocuSeal-Webhook)        KI-Agent (Claude, ChatGPT, Cursor …)
   │  HTTPS 443                                                 │  HTTPS 443, POST /mcp
   ▼                                                            ▼
nginx  (TLS, Ratenbegrenzung 10/s je IP, MCP 5/s, Uploads 1/s, Body-Grenzen, JSON-Fehlerseiten)
   │  HTTP 127.0.0.1:8080                  │  HTTP 127.0.0.1:8081
   │                                       ▼
   │                          doichain_mcp (Dienst doichain-mcp, Benutzer doimcp, 13 Werkzeuge)
   │  ◄──────────── ruft nur die REST-API auf, X-Forwarded-For = Client-IP
   ▼
uvicorn + FastAPI  (doichain_api, Dienst doichain-api, Benutzer doiapi, 2 Worker)
   │                          │
   │ JSON-RPC 127.0.0.1:8339  │ Electrum-Protokoll 127.0.0.1:50001
   ▼                          ▼
Doichain Core v31.1.6      ElectrumX 2.0.0 (Doichain-Fork mit Namensindex)
(txindex, namehistory,     liefert Guthaben, Historie und UTXOs beliebiger Adressen
 Wallet "doichain")
```

Die API hält keinen eigenen Zustand. Alles kommt live von der Node und vom ElectrumX. Die Node und
ElectrumX sind nur lokal erreichbar, nach außen spricht ausschließlich nginx.

## Voraussetzungen

- Ubuntu 24.04 (oder vergleichbar), Python 3.12, nginx, `rsync`, `openssl`, `certbot` für das spätere echte Zertifikat
- **Doichain Core v31.1.6** ([Releases](https://github.com/Doichain/doichain-core/releases)), Konfiguration mindestens:

  ```
  server=1
  txindex=1
  namehistory=1
  nameencoding=utf8
  valueencoding=utf8
  fallbackfee=0.001
  rpcbind=127.0.0.1
  rpcallowip=127.0.0.1
  ```

  `fallbackfee` ist Pflicht, weil `estimatesmartfee` auf Doichain keine Schätzung liefert. Nach dem Sync
  muss `getblockhash 431018` den Wert `71d50ff12b090561cc918ddb560334b4350758c7eace3f058dd332fb112f4b67`
  liefern (Kette nach dem Sicherheits-Fork vom 11.09.2026).
- Ein geladenes Wallet (Standardname `doichain`) mit etwas DOI für Gebühren und die 0,01 DOI je Eintrag, die im Namen gebunden bleiben und mit seinem Ablauf verloren sind.
- **ElectrumX** aus dem [Doichain-Fork](https://github.com/Doichain/electrumx) (Version 2.0.0-doi1 oder neuer) auf `127.0.0.1:50001` für die Adressabfragen. Ohne ElectrumX funktionieren alle Endpunkte außer `/v1/address/*`.

## Installation auf dem Server

Der Installer ist idempotent und legt auf einem frischen Server alles Nötige an: Systembenutzer `doiapi`,
virtuelle Python-Umgebung, selbstsigniertes Übergangszertifikat, Umgebungsdatei mit zufälligen
API-Schlüsseln (RPC-Zugang wird aus `/home/doichain/.doichain/doichain.conf` übernommen), Einzahlungsadresse
im Wallet, systemd-Dienst und nginx-Site. Eine vorhandene Umgebungsdatei wird nie verändert, eine von
certbot bearbeitete nginx-Datei bleibt unangetastet.

Vom Arbeitsplatz aus (kopiert das Arbeitsverzeichnis und führt den Installer aus):

```bash
bash deploy/push-to-server.sh root@136.243.155.62
```

Oder direkt auf dem Server:

```bash
git clone https://github.com/neubuot/doichain-api.git /root/doichain-api-src
bash /root/doichain-api-src/deploy/install.sh
```

Danach die Schlüssel einmalig ablesen und im Passwortmanager ablegen:

```bash
grep -E '^DOI_API_KEYS_(WRITE|ADMIN)=' /etc/doichain-api/doichain-api.env
```

Prüfung: `curl -s http://127.0.0.1:8080/health` und von außen `https://<host>/docs`.

Echtes Zertifikat, sobald ein Hostname auf den Server zeigt:

```bash
certbot --nginx -d api.doi.zone --redirect -m <mailadresse> --agree-tos -n
```

## Konfiguration

Alle Einstellungen kommen aus `/etc/doichain-api/doichain-api.env` (Vorlage: `deploy/doichain-api.env.example`).

| Variable | Bedeutung | Standard |
|---|---|---|
| `DOI_RPC_URL`, `DOI_RPC_USER`, `DOI_RPC_PASSWORD` | JSON-RPC der Node | `http://127.0.0.1:8339/` |
| `DOI_RPC_WALLET` | Name des Wallets für schreibende Aufrufe | `doichain` |
| `DOI_ELECTRUM_HOST`, `DOI_ELECTRUM_PORT` | lokaler ElectrumX | `127.0.0.1`, `50001` |
| `DOI_EXPLORER_URL` | Basis der Explorer-Links in den Antworten | `https://doi-explorer.le-space.de` |
| `DOI_PUBLIC_READ` | Lesen ohne Schlüssel erlauben | `true` |
| `DOI_API_KEYS_READ`, `DOI_API_KEYS_POE`, `DOI_API_KEYS_WRITE`, `DOI_API_KEYS_ADMIN` | Schlüssel je Stufe, kommagetrennt, nur ASCII, mindestens 16 Zeichen | |
| `DOI_POE_PUBLIC_PER_IP_DAY`, `DOI_POE_PUBLIC_PER_DAY` | Tageskontingent des poe-Schlüssels je IP-Adresse und insgesamt (UTC-Tag) | `10`, `200` |
| `DOI_STATE_DIR` | Ablage der Kontingent-Datenbank | `/var/lib/doichain-api` |
| `DOI_POE_PREFIX` | Namenspräfix der Nachweise | `poe/` |
| `DOI_MAX_UPLOAD_BYTES` | Grenze für Datei-Uploads | `52428800` |

Der Dienst prüft die Schlüssel beim Start und bricht mit klarer Meldung ab, wenn ein Eintrag unbrauchbar ist.

## Zugriffsstufen

| Stufe | Erlaubt | Nachweis |
|---|---|---|
| read | alles Lesende | ohne Schlüssel (solange `DOI_PUBLIC_READ=true`), sonst Leseschlüssel |
| poe | nur Nachweise anlegen, mit Tageskontingent je IP und insgesamt (`GET /v1/poe/quota`) | poe-Schlüssel (steht in der Verifile-App, deshalb eingeschränkt) |
| write | PoE anlegen, `name_doi`, `name_update`, `name_new`, `name_firstupdate`, Rohtransaktion senden, Wallet lesen, Adresse anlegen, Transaktion verwerfen, `regexp` in der Namenssuche | write-Schlüssel |
| admin | Auszahlungen, `sendtoname`, Nachricht signieren, RPC-Durchgriff | admin-Schlüssel |

Schlüssel per Header `X-API-Key: <schlüssel>` oder `Authorization: Bearer <schlüssel>`. In `/docs` über
**Authorize** eintragen.

## Erste Aufrufe

```bash
# Status der Node
curl https://doi-api.sendlabs.de/v1/status

# Nachweis prüfen
curl https://doi-api.sendlabs.de/v1/poe/$(sha256sum vertrag.pdf | cut -d' ' -f1)

# Nachweis anlegen (write-Schlüssel, Wallet braucht Guthaben)
curl -X POST https://doi-api.sendlabs.de/v1/poe/file \
  -H "X-API-Key: <write-schluessel>" -F "file=@vertrag.pdf" -F "note=Mietvertrag"

# Namen lesen und registrieren
curl https://doi-api.sendlabs.de/v1/name/Ottmar
curl -X POST https://doi-api.sendlabs.de/v1/name/doi \
  -H "X-API-Key: <write-schluessel>" -H "content-type: application/json" \
  -d '{"name":"id/doi-labs","value":"{\"web\":\"https://doi-labs.li\"}"}'
```

Python:

```python
import hashlib, requests
API = "https://doi-api.sendlabs.de/v1"
h = hashlib.sha256(open("vertrag.pdf", "rb").read()).hexdigest()
print(requests.get(f"{API}/poe/{h}").json()["status"])  # unknown, pending, confirmed, expired
```

Bei einer Neuinstallation ohne Hostnamen liefert nginx zunächst ein selbstsigniertes Zertifikat (der Installer
erzeugt es), dann mit `--cacert` arbeiten und nie die Prüfung abschalten.

## Proof of Existence

Die API registriert für jeden Nachweis den Namen `poe/<sha256>` per `name_doi`. Das Dokument bleibt beim
Aufrufer, nur der Hash geht auf die Kette. Als Wert wird ein kompaktes JSON gespeichert:

```json
{"v":1,"alg":"sha256","hash":"<hash>","ts":"2026-09-25T19:12:03Z","file":"vertrag.pdf","note":"Mietvertrag"}
```

Der Zeitstempel lässt sich nachträglich nicht ändern, das Dokument selbst kommt nie auf die Kette.

Regeln der Kette: 0,01 DOI je Name (im Namen gebunden und mit dem Ablauf verloren, kein Pfand, das zurückfließt),
Ablauf nach 36.000 Blöcken (rund 250 Tage), nur der Inhaber kann einen aktiven Namen ändern oder verlängern
(`POST /v1/name/doi` mit write-Schlüssel), ein Nachweis ist erst nach der ersten Bestätigung endgültig, je Name
nur eine unbestätigte Operation. Nach dem Ablauf ist der Name frei und kann von jedem neu registriert werden.

`GET /v1/poe/{hash}` (ebenso `POST /v1/poe/verify` und `/verify/file`) liefert Status, Blockhöhe, Blockzeit,
Bestätigungen, Inhaber und Explorer-Link des aktuellen Eintrags. Der eigentliche Nachweis ist immer
`first_anchored`, die erste Verankerung mit `txid`, `height`, `block_hash`, `block_time_iso`, `value`, `value_json`
und `owner_address` (Inhaber zu diesem Zeitpunkt, `null`, wenn unbekannt). `reregistered_after_expiry: true` zeigt,
dass der Name abgelaufen war und danach neu registriert wurde, `current_registration_start` nennt dann `txid`,
`height`, `block_time_iso` und `explorer_tx` dieser Neuregistrierung. Inhaber und Wert auf oberster Ebene gehören
in diesem Fall nicht zum ursprünglichen Nachweis. Aktualisierungen des Inhabers vor dem Ablauf zählen nicht als
Neuregistrierung.

`POST /v1/poe` und `POST /v1/poe/file` antworten für einen aktiven oder wartenden Hash mit 409, sie verlängern
keine aktiven Namen. Für einen abgelaufenen Hash kommt ebenfalls 409 mit Block und Zeit der ersten Verankerung,
es sei denn, der Aufruf setzt ausdrücklich `"reanchor": true` (Formularfeld `reanchor=true` bei `/v1/poe/file`).
Dann entsteht eine neue, spätere Registrierung, die Antwort enthält `reanchored_after_expiry: true` (und
`renewed` mit demselben Wert für ältere Clients), der ursprüngliche Nachweis bleibt unverändert.

## MCP-Server für KI-Agenten

Der MCP-Server (`doichain_mcp/server.py`, MCP-SDK 2.x) macht die öffentlichen Funktionen der API als Werkzeuge
für KI-Agenten nutzbar. Er läuft als eigener Dienst `doichain-mcp` (Benutzer `doimcp`, 127.0.0.1:8081) hinter
nginx unter `/mcp`, zustandslos mit JSON-Antworten, und spricht ausschließlich mit der REST-API. Auf RPC, Wallet
und die Schlüsseldatei der API hat er keinen Zugriff.

Einbinden, zum Beispiel in Claude Code:

```bash
claude mcp add --scope user --transport http doichain https://doi-api.sendlabs.de/mcp
```

| Werkzeug | Zweck |
|---|---|
| `anchor_proof` | SHA-256 als `poe/<hash>` verankern (einziges schreibendes Werkzeug, bereits verankerte Hashes werden erkannt, abgelaufene nur mit `reanchor_expired: true` erneut, das ergibt einen späteren Zeitstempel) |
| `check_proof` | Status, Block, Zeit und Transaktion der ersten Verankerung, eine spätere Registrierung getrennt |
| `hash_text` | SHA-256 eines kurzen Textes (im Server berechnet, nichts wird gespeichert, Dateien hasht der Agent selbst) |
| `get_anchoring_quota` | verbleibendes Tageskontingent des Aufrufers |
| `lookup_name`, `get_name_history`, `search_names` | Namen lesen, Historie, Suche nach Präfix (mit `include_expired` auch abgelaufene) |
| `check_name_expiry` | bis zu 25 Namen: aktiv, läuft bald ab, abgelaufen, frei, mit geschätztem Datum (gemessener Blockabstand) |
| `get_chain_status`, `get_block`, `get_transaction`, `get_address`, `verify_message` | Kette, Adressen, signierte Nachrichten |

Verankern nutzt den öffentlichen poe-Schlüssel (derselbe wie Verifile) mit dem Tageskontingent je Client-IP.
nginx setzt `X-Real-IP`, der MCP-Server reicht die Adresse als `X-Forwarded-For` an die API weiter. Wer einen
eigenen Schlüssel im Header `X-API-Key` mitschickt, verankert damit (write-Schlüssel ohne Kontingent).
`Authorization: Bearer` wertet der MCP-Server nur aus, wenn `DOI_MCP_ACCEPT_BEARER=true` gesetzt ist (Standard aus). Gehostete Apps (Claude im Browser, ChatGPT) verbinden sich aus den Rechenzentren ihrer Anbieter,
ihre Nutzer teilen sich deshalb das Kontingent dieser Adressen. Namen und Werte aus der Kette tragen in den Antworten die Endung `_untrusted`, damit Agenten sie als Daten
und nicht als Anweisung behandeln. `GET /mcp` ohne `text/html` beantwortet nginx mit 405 (kein SSE-Strom im
zustandslosen Betrieb), Browser bekommen die Landingpage. Gesundheitsprüfung: `GET /mcp/health`.
Unterstützte Protokollversionen: 2024-11-05 bis 2026-07-28, keine JSON-RPC-Batches, keine Clients direkt im Browser (kein CORS).
Namen fragt der MCP-Server über `GET /v1/name?name=…` ab, weil Namen mit `/history` am Ende im Pfadformat mehrdeutig sind.

**Öffentliches Repo und MCP-Verzeichnis:** Der MCP-Server ist zusätzlich öffentlich unter
**https://github.com/neubuot/doichain-mcp** (MIT-Lizenz, englische README, Werkzeugreferenz, Tests, CI) und im offiziellen
MCP-Verzeichnis als `io.github.neubuot/doichain` eingetragen. `server.json`, README und Workflows pflegt das öffentliche Repo,
`server.py`, Landingpage und systemd-Unit dieses Repo. Abgleich mit `bash deploy/sync-public-mcp.sh`, eine neue Version
im Verzeichnis entsteht durch einen Tag `vX.Y.Z` im öffentlichen Repo (GitHub Actions mit OIDC).

## Betrieb

| Was | Wie |
|---|---|
| Dienst | `systemctl status doichain-api`, `journalctl -u doichain-api -f`, Warnungen mit `-p warning` |
| MCP-Server | `systemctl status doichain-mcp`, `journalctl -u doichain-mcp -f`, Umgebung `/etc/doichain-mcp/doichain-mcp.env` (vom Installer erzeugt) |
| nginx | `/etc/nginx/sites-available/doichain-api`, Logs `/var/log/nginx/doichain-api.*.log` |
| Update | Code nach `/root/doichain-api-src`, dann `bash deploy/install.sh` (oder `deploy/push-to-server.sh` vom Arbeitsplatz) |
| Überwachung | `GET /health` liefert 200 nur bei gesunder, synchroner Kette, sonst 503 mit `problems`, `GET /mcp/health` für den MCP-Server |
| Gebühren | feste Rate 100 sat/vB (`fallbackfee=0.001`), Auszahlungen setzen `fee_rate` explizit |

## Lokale Entwicklung

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DOI_RPC_URL=http://127.0.0.1:8339/ DOI_RPC_USER=... DOI_RPC_PASSWORD=... DOI_API_KEYS_WRITE=$(openssl rand -hex 24)
uvicorn doichain_api.main:app --reload --port 8080
```

Ohne eigene Node lassen sich RPC und ElectrumX per SSH-Tunnel auf den Server legen
(`ssh -L 8339:127.0.0.1:8339 -L 50001:127.0.0.1:50001 root@136.243.155.62`).

## Projektstruktur

```
doichain_api/
  main.py        Endpunkte, Fehlerabbildung, PoE-Logik, RPC-Sperrliste
  rpc.py         asynchroner JSON-RPC-Client (Positions- und benannte Parameter)
  electrum.py    Base58/Bech32-Dekodierung, Scripthash, ElectrumX-Client
  auth.py        Schlüsselstufen als OpenAPI-Sicherheitsschema
  config.py      Einstellungen aus Umgebungsvariablen, Startprüfung der Schlüssel
  quota.py       Tageskontingent des poe-Schluessels (SQLite)
doichain_mcp/
  server.py      MCP-Server (13 Werkzeuge, Streamable HTTP, zustandslos), ruft nur die REST-API auf
web/
  verifile/      PoE-Web-App (index.html, app.js, style.css, config.example.js)
  api-site/      Landingpage der API mit Spielwiese
  mcp-site/      Landingpage des MCP-Servers (index.html, style.css, app.js, icon.svg)
deploy/
  install.sh                 idempotenter Installer (Benutzer, venv, Zertifikat, env, systemd, nginx, Web-Oberflächen)
  push-to-server.sh          Arbeitsverzeichnis hochladen und Installer ausführen
  sync-public-mcp.sh         MCP-Server mit dem öffentlichen Repo neubuot/doichain-mcp abgleichen
  doichain-api.service       systemd-Unit (gehärtet, StateDirectory)
  doichain-mcp.service       systemd-Unit des MCP-Servers (eigener Benutzer doimcp)
  nginx-doichain-api.conf    TLS, Ratenbegrenzung, Body-Grenzen, JSON-Fehlerseiten, Landingpage und /poe/
  nginx-verifile.conf        eigener vHost für verifile.app / verifile.it
  doichain-api.env.example   Vorlage der Umgebungsdatei
docs/
  Handbuch.md                ausführliches Handbuch (deutsch)
  doichain-api-selfsigned.crt  Übergangszertifikat der Produktivinstanz
requirements.txt             Abhängigkeiten der API
requirements-mcp.txt         Abhängigkeiten des MCP-Servers (eigene venv)
CHANGELOG.md
```

## Sicherheit

- Schlüssel und RPC-Zugang liegen nur in der Umgebungsdatei (root:doiapi, 0640), nie im Repo.
- Das Node-Wallet ist ein Hot Wallet mit Betriebsguthaben. Der admin-Schlüssel erlaubt Auszahlungen.
- Der RPC-Durchgriff sperrt Schlüsselmaterial, Wallet-Dateien, Dateizugriff und Node-Steuerung (Liste plus Präfixregel für künftige Core-Releases).
- nginx: nur ECDHE-Verfahren, keine Versionsanzeige, keine Einbettung, Ratenbegrenzung, Body-Grenzen je Endpunkt.
- systemd: `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`, eigener Benutzer ohne Login.
- Der MCP-Server läuft als eigener Benutzer `doimcp` ohne Lesezugriff auf `/etc/doichain-api`, kennt nur den öffentlichen poe-Schlüssel und bietet keine Wallet-, Namensänderungs- oder RPC-Werkzeuge. Host- und Origin-Prüfung gegen DNS-Rebinding, eigene Ratenzone in nginx.
- Zwei unabhängige Prüfrunden (Sicherheit, Korrektheit, Robustheit, Handbuch) mit 71 eingearbeiteten Befunden, siehe `CHANGELOG.md`.

## Dokumentation und Lizenz

- Ausführliches Handbuch: [`docs/Handbuch.md`](docs/Handbuch.md)
- OpenAPI-Beschreibung: `/openapi.json` der laufenden Instanz
- Doichain: [Core](https://github.com/Doichain/doichain-core), [ElectrumX-Fork](https://github.com/Doichain/electrumx), [Explorer](https://doi-explorer.le-space.de)

Lizenz noch nicht festgelegt (Repo privat). Bis dahin alle Rechte vorbehalten, DOI Labs AG.
Entwickelt von Ottmar Neuburger mit Claude (Anthropic), September 2026.

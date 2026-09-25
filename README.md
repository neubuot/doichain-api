# Doichain API

REST-Schnittstelle vor einer Doichain-Node (Doichain Core v31.1.6). Stellt alle Doichain-Funktionen
über HTTP bereit: **Proof of Existence**, **`name_doi`** und die übrigen Namensoperationen, Blöcke,
Transaktionen, Mempool, Adressguthaben (über ElectrumX) und das Wallet der Node. Interaktive
Dokumentation (Swagger) unter `/docs`.

*English summary: a FastAPI service in front of Doichain Core v31.1.6 exposing proof of existence,
`name_doi` and all name operations, chain queries, address balances (via ElectrumX) and wallet functions
as a documented REST API with API-key tiers, nginx TLS termination and rate limiting. The manual
(`docs/Handbuch.md`) is in German.*

Produktivinstanz: Hetzner-Server `doi-btc-node`, **https://doi-api.sendlabs.de/docs** (Let's Encrypt, später
zusätzlich `api.doi.zone`). Betreiber: DOI Labs AG. Stand: Version 1.2.0, 25.09.2026.

## Inhalt

- [Funktionen](#funktionen)
- [Architektur](#architektur)
- [Voraussetzungen](#voraussetzungen)
- [Installation auf dem Server](#installation-auf-dem-server)
- [Konfiguration](#konfiguration)
- [Zugriffsstufen](#zugriffsstufen)
- [Erste Aufrufe](#erste-aufrufe)
- [Proof of Existence](#proof-of-existence)
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
| Namen | `GET /v1/name/{name}`, `/history`, `GET /v1/names` (Blättern über `after`/`next_after`), `GET /v1/names/pending`, `POST /v1/name/doi`, `/update`, `/new`, `/firstupdate`, `/sendtoname` |
| Proof of Existence | `GET /v1/poe/{sha256}`, `POST /v1/poe/verify`, `POST /v1/poe/verify/file`, `POST /v1/poe`, `POST /v1/poe/file` |
| Wallet | `GET /v1/wallet`, `/funding-address`, `/names`, `/transactions`, `/utxos`, `POST /v1/wallet/address`, `/abandon`, `/send` |
| Werkzeuge | `GET /v1/validate/{adresse}`, `POST /v1/message/verify`, `/sign`, `GET /v1/fee`, `POST /v1/rpc` (Durchgriff mit Sperrliste) |

Alle Fehler kommen einheitlich als `{"error": {"type": …, "code": …, "message": …}}`, auch die von nginx
erzeugten (413, 429, 502, 504). Schreibende Aufrufe prüfen nach dem Absenden, ob die Node die Transaktion
tatsächlich in den Mempool übernommen hat, und verwerfen sie sonst im Wallet.

## Architektur

```
Client (curl, Python, Browser, n8n, DocuSeal-Webhook)
   │  HTTPS 443
   ▼
nginx  (TLS, Ratenbegrenzung 10/s je IP, Uploads 1/s, Body-Grenzen 64 KB / 1 MB / 52 MB, JSON-Fehlerseiten)
   │  HTTP 127.0.0.1:8080
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
- Ein geladenes Wallet (Standardname `doichain`) mit etwas DOI für Gebühren und das Namenspfand von 0,01 DOI je Eintrag.
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
| `DOI_API_KEYS_READ`, `DOI_API_KEYS_WRITE`, `DOI_API_KEYS_ADMIN` | Schlüssel je Stufe, kommagetrennt, nur ASCII, mindestens 16 Zeichen | |
| `DOI_POE_PREFIX` | Namenspräfix der Nachweise | `poe/` |
| `DOI_MAX_UPLOAD_BYTES` | Grenze für Datei-Uploads | `52428800` |

Der Dienst prüft die Schlüssel beim Start und bricht mit klarer Meldung ab, wenn ein Eintrag unbrauchbar ist.

## Zugriffsstufen

| Stufe | Erlaubt | Nachweis |
|---|---|---|
| read | alles Lesende | ohne Schlüssel (solange `DOI_PUBLIC_READ=true`), sonst Leseschlüssel |
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

Regeln der Kette: 0,01 DOI Pfand je Name (verfällt bei Ablauf), Ablauf nach 36.000 Blöcken (rund 250 Tage,
Verlängerung durch erneutes `name_doi` des Inhabers), nur der Inhaber kann einen aktiven Namen ändern,
ein Nachweis ist erst nach der ersten Bestätigung endgültig, je Name nur eine unbestätigte Operation.
`GET /v1/poe/{hash}` liefert Blockhöhe, Blockzeit, Bestätigungen, Inhaber und Explorer-Link.

## Betrieb

| Was | Wie |
|---|---|
| Dienst | `systemctl status doichain-api`, `journalctl -u doichain-api -f`, Warnungen mit `-p warning` |
| nginx | `/etc/nginx/sites-available/doichain-api`, Logs `/var/log/nginx/doichain-api.*.log` |
| Update | Code nach `/root/doichain-api-src`, dann `bash deploy/install.sh` (oder `deploy/push-to-server.sh` vom Arbeitsplatz) |
| Überwachung | `GET /health` liefert 200 nur bei gesunder, synchroner Kette, sonst 503 mit `problems` |
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
deploy/
  install.sh                 idempotenter Installer (Benutzer, venv, Zertifikat, env, systemd, nginx)
  push-to-server.sh          Arbeitsverzeichnis hochladen und Installer ausführen
  doichain-api.service       systemd-Unit (gehärtet)
  nginx-doichain-api.conf    TLS, Ratenbegrenzung, Body-Grenzen, JSON-Fehlerseiten
  doichain-api.env.example   Vorlage der Umgebungsdatei
docs/
  Handbuch.md                ausführliches Handbuch (deutsch)
  doichain-api-selfsigned.crt  Übergangszertifikat der Produktivinstanz
CHANGELOG.md
```

## Sicherheit

- Schlüssel und RPC-Zugang liegen nur in der Umgebungsdatei (root:doiapi, 0640), nie im Repo.
- Das Node-Wallet ist ein Hot Wallet mit Betriebsguthaben. Der admin-Schlüssel erlaubt Auszahlungen.
- Der RPC-Durchgriff sperrt Schlüsselmaterial, Wallet-Dateien, Dateizugriff und Node-Steuerung (Liste plus Präfixregel für künftige Core-Releases).
- nginx: nur ECDHE-Verfahren, keine Versionsanzeige, keine Einbettung, Ratenbegrenzung, Body-Grenzen je Endpunkt.
- systemd: `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`, eigener Benutzer ohne Login.
- Zwei unabhängige Prüfrunden (Sicherheit, Korrektheit, Robustheit, Handbuch) mit 71 eingearbeiteten Befunden, siehe `CHANGELOG.md`.

## Dokumentation und Lizenz

- Ausführliches Handbuch: [`docs/Handbuch.md`](docs/Handbuch.md)
- OpenAPI-Beschreibung: `/openapi.json` der laufenden Instanz
- Doichain: [Core](https://github.com/Doichain/doichain-core), [ElectrumX-Fork](https://github.com/Doichain/electrumx), [Explorer](https://doi-explorer.le-space.de)

Lizenz noch nicht festgelegt (Repo privat). Bis dahin alle Rechte vorbehalten, DOI Labs AG.
Entwickelt von Ottmar Neuburger mit Claude (Anthropic), September 2026.

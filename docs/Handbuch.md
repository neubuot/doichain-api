# Doichain-API – Handbuch

> Kopie des Handbuchs aus dem Obsidian-Vault von DOI Labs (Stand 26.09.2026, Version 1.4.1 mit MCP-Server für KI-Agenten). Verweise auf interne Vault-Notizen sind als Klartext belassen.


# Doichain-API – Handbuch

↩️ MOC – Doichain · Einrichtung: Einrichtungsbericht 2026-09-25 – Doichain-API auf doi-btc-node · Offene Punkte: Wiedervorlage 29.09.2026

Stand: Version 1.4.1 vom 26.09.2026 (Version 1.2.0 nach zwei unabhängigen Prüfrunden mit 44 plus 27 eingearbeiteten Befunden, 1.3.0 ergänzt Verifile, Landingpage und den poe-Schlüssel, 1.4.0 den MCP-Server für KI-Agenten, Abschnitt 12, 1.4.1 die Nachbesserungen aus dessen Prüfrunde).

## 1. Was die API ist

Die Doichain-API ist eine Web-Schnittstelle vor der eigenen Doichain-Node auf dem Hetzner-Server **doi-btc-node**. Jedes Programm, das HTTP spricht (Browser, curl, Python, JavaScript, n8n, DocuSeal-Webhook), kann damit die Doichain nutzen, ohne selbst eine Node zu betreiben oder das JSON-RPC-Protokoll von Doichain Core zu kennen. Sie deckt alle Doichain-Funktionen ab:

- **Proof of Existence (PoE):** den SHA-256-Hash eines Dokuments mit einem Zeitstempel auf der Kette verankern, der sich nachträglich nicht ändern lässt, und später beweisen, dass das Dokument spätestens zu diesem Zeitpunkt existierte.
- **Namen:** die Namecoin-artigen Namen der Doichain lesen, durchsuchen und mit `name_doi` registrieren, ändern, verlängern oder übertragen.
- **Kette:** Blöcke, Transaktionen (inklusive dekodierter Namensoperationen), Mempool, Netzwerk.
- **Adressen:** Guthaben, Historie und unverbrauchte Outputs beliebiger Adressen.
- **Wallet:** das Wallet der Node (Guthaben, Adressen, Auszahlungen), nur mit Schlüssel.

| | |
|---|---|
| Landingpage | **https://doi-api.sendlabs.de/** mit Erklärung, Live-Status, Spielwiese für lesende Aufrufe und Codebeispielen (Quelle `web/api-site` im Repo) |
| Verifile (PoE-App) | **https://verifile.it/** (seit 26.09.2026, Let's Encrypt), zusätzlich unter https://doi-api.sendlabs.de/poe/ (Abschnitt 4) |
| MCP-Server (KI-Agenten) | **https://doi-api.sendlabs.de/mcp** seit 26.09.2026. Claude, ChatGPT, Cursor und andere Agenten binden die Doichain mit dieser Adresse ein, im Browser zeigt sie die Landingpage mit Anleitung (Abschnitt 12) |
| Interaktive Doku (Swagger) | **https://doi-api.sendlabs.de/docs** (alternativ `/redoc`), später zusätzlich https://api.doi.zone/docs |
| Basis-Adresse | `https://doi-api.sendlabs.de/v1/` |
| Maschinenlesbare Beschreibung | `https://doi-api.sendlabs.de/openapi.json` |
| Gesundheitscheck | `https://doi-api.sendlabs.de/health` |
| Zertifikat | **Let's Encrypt** für `doi-api.sendlabs.de` seit 25.09.2026 (certbot, automatische Erneuerung, HSTS aktiv). Kein `--cacert` und kein `-k` mehr nötig. Der Aufruf über die nackte IP-Adresse 136.243.155.62 funktioniert weiter, zeigt dann aber eine Zertifikatswarnung, weil das Zertifikat auf den Hostnamen lautet. Das frühere selbstsignierte Zertifikat (doichain-api-selfsigned.crt) wird nicht mehr ausgeliefert |
| Kette | Doichain Mainnet nach dem Sicherheits-Fork vom 11.09.2026, Node Doichain Core v31.1.6 |
| Explorer für Links | https://doi-explorer.le-space.de. Einzelabfragen zu Block, Transaktion, Adresse, Name und Nachweis enthalten fertige Explorer-Links |

Unter `/docs` lässt sich jeder Aufruf im Browser ausprobieren („Try it out"). Für Aufrufe mit Schlüssel oben rechts **Authorize** wählen und den Schlüssel unter `ApiKey` eintragen, er gilt dann für alle Aufrufe der Sitzung.

## 2. Schnellstart in fünf Minuten

Status der Node lesen (kein Schlüssel nötig):

```bash
curl https://doi-api.sendlabs.de/v1/status
```

Antwort (gekürzt): Blockhöhe, Zeit des letzten Blocks, ob die Fork-Prüfung stimmt (`fork_check.ok`), Mempool, ElectrumX und ob das Wallet Guthaben hat.

Einen Nachweis prüfen (Hash einer Datei berechnen und nachschlagen):

```bash
sha256sum vertrag.pdf
curl https://doi-api.sendlabs.de/v1/poe/<hash>
```

Einen Nachweis anlegen (braucht den write-Schlüssel und Guthaben im Wallet, Abschnitt 4):

```bash
curl -X POST https://doi-api.sendlabs.de/v1/poe/file \
  -H "X-API-Key: <write-schluessel>" \
  -F "file=@vertrag.pdf" -F "note=Mietvertrag Schulgasse 5"
```

Einen aktiven Namen lesen (`Ottmar` ist seit Block 432.344 registriert, `Lisa` ist ein abgelaufener Beispielname):

```bash
curl https://doi-api.sendlabs.de/v1/name/Ottmar
```

Python-Beispiel (nur `requests` nötig):

```python
import requests
api = "https://doi-api.sendlabs.de/v1"
print(requests.get(f"{api}/status").json()["chain"]["blocks"])
r = requests.get(f"{api}/poe/e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
print(r.json()["status"])   # unknown, pending, confirmed oder expired
```

Die Zertifikatsprüfung nie mit `-k` oder `verify=False` abschalten, sonst ginge der Schlüssel auch an einen Angreifer im Netzwerkpfad.

## 3. Zugriffsstufen und Schlüssel

| Stufe | Was geht | Schlüssel |
|---|---|---|
| **read** | alles Lesende: Status, Kette, Adressen, Namen lesen, PoE prüfen | ohne Schlüssel, solange `DOI_PUBLIC_READ=true` (Standard) |
| **poe** | nur Nachweise anlegen (`POST /v1/poe`, `POST /v1/poe/file`) und das Kontingent abfragen (`GET /v1/poe/quota`), mit Tageskontingent 10 je IP-Adresse und 200 insgesamt (UTC-Tag) | poe-Schlüssel, steckt in der Verifile-App und ist deshalb im Browser sichtbar |
| **write** | PoE anlegen, `name_doi`, `name_update`, `name_new`, `name_firstupdate`, Rohtransaktion senden, Wallet lesen, neue Empfangsadresse, Transaktion verwerfen | write-Schlüssel |
| **admin** | Auszahlungen (`/v1/wallet/send`), `sendtoname`, Nachricht signieren, generischer RPC-Durchgriff | admin-Schlüssel (darf auch alles der Stufe write) |

Der Schlüssel wird als Header mitgeschickt, entweder `X-API-Key: <schlüssel>` oder `Authorization: Bearer <schlüssel>`. Ohne Schlüssel antwortet die API mit 401, mit zu niedriger Stufe mit 403. Ein Schlüssel mit Tipp- oder Kopierfehler zählt als ungültig, nur gewöhnliche Leerzeichen am Rand werden verziehen. Für anonyme Aufrufer zeigt `/v1/status` vom Wallet nur, ob es Guthaben hat, Zahlen gibt es ab Stufe write. Beim Start prüft der Dienst die konfigurierten Schlüssel (nur ASCII, mindestens 16 Zeichen) und bricht mit klarer Meldung ab, wenn in der Umgebungsdatei ein Tippfehler steckt.

**Wo die Schlüssel liegen.** Ausschließlich in der Umgebungsdatei auf dem Server (`/etc/doichain-api/doichain-api.env`, lesbar für root und den Dienst) und in Vaultwarden (Einträge „Doichain API write" und „Doichain API admin"). Einmalig zum Übertragen nach Vaultwarden auf dem Server anzeigen:

```bash
ssh root@136.243.155.62 "grep -E '^DOI_API_KEYS_(WRITE|ADMIN)=' /etc/doichain-api/doichain-api.env"
```

Danach nur noch aus Vaultwarden verwenden. Wer den admin-Schlüssel hat, kann das Node-Wallet leeren, also sparsam weitergeben.

**Schlüssel ändern oder weitere anlegen.** In der Umgebungsdatei stehen die Schlüssel kommagetrennt (`DOI_API_KEYS_WRITE=abc,def`). Neuen Wert erzeugen mit `openssl rand -hex 24`, Datei bearbeiten, dann `systemctl restart doichain-api`. Mit `DOI_API_KEYS_READ=` lassen sich zusätzlich Leseschlüssel vergeben, sinnvoll, wenn `DOI_PUBLIC_READ=false` gesetzt wird und das Lesen nicht mehr öffentlich sein soll. Der poe-Schlüssel (`DOI_API_KEYS_POE`) wird nach einer Änderung mit `bash deploy/install.sh` neu in die `config.js` der Verifile-App geschrieben. Die Kontingente stehen in `DOI_POE_PUBLIC_PER_IP_DAY` und `DOI_POE_PUBLIC_PER_DAY`, die Zähler in `/var/lib/doichain-api/quota.db` (werden beim Tageswechsel UTC zurückgesetzt).

**Ratenbegrenzung.** nginx erlaubt 10 Anfragen pro Sekunde je IP-Adresse (Spitzen bis 30), auf den beiden Datei-Upload-Endpunkten 1 pro Sekunde (Spitzen bis 3). Darüber kommt HTTP 429 im JSON-Fehlerformat.

## 4. Proof of Existence (PoE)

### Wie es funktioniert

Die API berechnet den SHA-256-Hash einer Datei (oder nimmt einen fertigen Hash entgegen) und registriert auf der Doichain den Namen `poe/<hash>` per `name_doi`. Der Name ist damit im Block verankert, sein Blockzeitstempel beweist, dass der Hash (und damit das Dokument) spätestens zu diesem Zeitpunkt existierte. Das Dokument selbst verlässt den Server nie und landet nicht auf der Kette, nur der Hash.

Als Wert des Namens speichert die API ein kleines JSON:

```json
{"v":1,"alg":"sha256","hash":"<hash>","ts":"2026-09-25T19:12:03Z","file":"vertrag.pdf","note":"Mietvertrag Schulgasse 5"}
```

`file` (höchstens 80 Zeichen) und `note` (höchstens 160 Zeichen) sind optional und öffentlich lesbar, also keine personenbezogenen Daten hineinschreiben. Längere Angaben lehnt die API mit 422 ab. Umlaute sind erlaubt, die API übergibt Werte immer als UTF-8, dabei zählt ein Umlaut zwei Byte. Der gesamte Wert darf höchstens 520 Byte lang sein, bei Überschreitung antwortet die API mit 422 und nennt die tatsächliche Bytezahl, gekürzt wird nichts.

Regeln der Kette, die man kennen sollte:

- Jeder Name bindet **0,01 DOI** im Namens-Output, dazu rund 0,0002 bis 0,0005 DOI Gebühr. Die 0,01 DOI bleiben beim Namen und sind **mit dem Ablauf des Namens verloren** (die Node macht den Output dann unspendbar). Sie sind also Kosten und kein Pfand, das zurückfließt.
- Ein Name **läuft nach 36.000 Blöcken ab** (bei zehn Minuten je Block rund 250 Tage). Der Zeitstempel bleibt in der Kette und im Explorer sichtbar und beweiskräftig, aber der Name wird wieder frei und kann von jedem neu registriert werden, mit eigener Notiz und eigenem Inhaber. `GET /v1/poe/{hash}` nennt deshalb in `first_anchored` immer die erste Verankerung und zeigt eine spätere Neuregistrierung getrennt an (Abschnitt „Antwort beim Prüfen“).
- **Verlängern** kann einen noch aktiven Nachweis nur der Inhaber, und zwar über `POST /v1/name/doi` (write-Schlüssel) mit demselben Namen und dem bisherigen Wert. Der Ablauf beginnt dann neu. `POST /v1/poe` verlängert nicht: Für einen aktiven Hash antwortet es mit 409. Für einen abgelaufenen Hash ebenfalls mit 409, es sei denn, der Aufruf setzt ausdrücklich `reanchor: true`. Dann entsteht eine neue, spätere Registrierung (die Antwort enthält `reanchored_after_expiry: true`), der ursprüngliche Nachweis bleibt unverändert in der Historie und `first_anchored` verweist weiter auf ihn.
- Die über die API angelegten Namen `poe/<hash>` gehören dem Node-Wallet von DOI Labs, das die Gebühr und die 0,01 DOI bezahlt. Ein Nachweis zeigt deshalb, dass ein Dokument mit diesem Hash spätestens zu diesem Zeitpunkt existierte, nicht, wer es eingereicht hat.
- Solange ein Name aktiv ist, kann **nur der Inhaber** ihn ändern (das Wallet der Node, wenn der Eintrag über die API angelegt wurde). Fremde Versuche scheitern an der Node.
- Ein Nachweis ist **erst nach der ersten Bestätigung endgültig** (nächster Block, im Mittel zehn Minuten). Registrieren zwei Beteiligte denselben freien Namen fast gleichzeitig, gewinnt die zuerst bestätigte Transaktion, die andere wird ungültig. `GET /v1/poe/{hash}` zeigt immer den Kettenzustand, darauf verlassen, nicht auf die Antwort beim Anlegen. Für hohe Ansprüche zwölf Bestätigungen abwarten.
- Je Name ist nur **eine unbestätigte Operation** erlaubt. Eine zweite vor der Bestätigung meldet 409.

### Endpunkte

| Aufruf | Stufe | Zweck |
|---|---|---|
| `GET /v1/poe/{hash}` | read | Nachweis zu einem Hash prüfen |
| `POST /v1/poe/verify` mit `{"hash": "…"}` | read | dasselbe als POST |
| `POST /v1/poe/verify/file` (Multipart, Feld `file`) | read | Datei hochladen, Hash wird auf dem Server berechnet und geprüft |
| `POST /v1/poe` mit `{"hash": "…", "filename": "…", "note": "…", "reanchor": false}` | poe oder write | Nachweis anlegen, Hash lokal berechnet. Mit poe-Schlüssel zählt das Tageskontingent, die Antwort enthält dann `quota`. `reanchor` (Standard `false`) nur für abgelaufene Hashes, siehe „Antwort beim Anlegen“ |
| `POST /v1/poe/file` (Multipart, Felder `file`, optional `note` und `reanchor`) | poe oder write | Datei hochladen, Hash berechnen, Nachweis anlegen (bis 50 MB). `reanchor=true` wie bei `POST /v1/poe` |
| `GET /v1/poe/quota` | poe | verbleibendes Tageskontingent für die eigene IP-Adresse und insgesamt (`unlimited: true` mit write- oder admin-Schlüssel) |

### Verifile, die Web-App

Für Endnutzer gibt es die App **Verifile** unter **https://verifile.it/** (eigener nginx-vHost mit Let's Encrypt seit 26.09.2026, `www` leitet auf den Hauptnamen, zusätzlich erreichbar unter https://doi-api.sendlabs.de/poe/): Datei ins Feld ziehen, der Browser berechnet den SHA-256 (gestückelt über die selbst ausgelieferte Bibliothek hash-wasm, damit auch Gigabyte-Dateien gehen, Rückfall auf Web Crypto bis 1 GB), nichts wird hochgeladen. Auf die Kette gehen nur Hash, die optionale Notiz und, nur mit gesetztem Häkchen, der Dateiname. Öffentliche Nachweise pausieren automatisch, wenn das Node-Wallet unter 5 DOI fällt, und ein fehlgeschlagener Versuch kostet kein Kontingent. Die App fragt den Status ab, verankert auf Klick über den poe-Schlüssel, aktualisiert sich alle 30 Sekunden bis zur Bestätigung und liefert den Nachweis als JSON-Datei oder Druckansicht. Ein bekannter Hash lässt sich direkt eingeben oder als `#<hash>` an die Adresse hängen, so werden Nachweise verlinkbar. Sprache Deutsch und Englisch (Schalter oben rechts, Wahl bleibt im Browser gespeichert). Quellcode im Repo unter `web/verifile`, Konfiguration `config.js` erzeugt der Installer aus der Umgebungsdatei. Solange die App unter dem API-Host läuft, gelten die dortigen Sicherheits-Header, auf der eigenen Domain die Vorlage `deploy/nginx-verifile.conf` mit Content-Security-Policy.

Angezeigt, heruntergeladen (JSON) und gedruckt wird immer die erste Verankerung aus `first_anchored`: Blockzeit, Block, Transaktion, Bestätigungen, Explorer-Link sowie Zeitstempel, Notiz und Dateiname aus ihrem Wert. Weicht die aktuelle Transaktion davon ab, zeigt die App das in einer eigenen Zeile an. Wurde der Name nach Ablauf neu registriert, steht dort, dass Notiz und Inhaber der neuen Registrierung nicht zum ursprünglichen Nachweis gehören. Hat der Inhaber den Namen nur aktualisiert, sagt die Zeile das. Der JSON-Nachweis enthält dann zusätzlich das Objekt `latest_registration`. Bei einem abgelaufenen Nachweis erklärt die App, dass der ursprüngliche Nachweis gültig bleibt, und bietet „Neu verankern (späterer Zeitstempel)“ an. Nur dieser Knopf schickt `reanchor: true`.

### Antwort beim Prüfen

```json
{
  "hash": "9f86d081…",
  "name": "poe/9f86d081…",
  "exists": true,
  "pending": false,
  "status": "confirmed",
  "txid": "…", "vout": 0, "height": 433412,
  "block_hash": "…", "block_time": 1790360000, "block_time_iso": "2026-09-25T18:13:20Z",
  "confirmations": 5,
  "owner_address": "N…", "owned_by_this_wallet": true,
  "expired": false, "expires_in": 35995,
  "value": "{\"v\":1,…}", "value_json": {"v": 1, "alg": "sha256", "…": "…"},
  "explorer_tx": "https://doi-explorer.le-space.de/tx/…",
  "first_anchored": {
    "txid": "…", "height": 433412, "block_hash": "…",
    "block_time": 1790360000, "block_time_iso": "2026-09-25T18:13:20Z", "confirmations": 5,
    "value": "{\"v\":1,…}", "value_json": {"v": 1, "…": "…"}, "owner_address": "N…",
    "explorer_tx": "https://doi-explorer.le-space.de/tx/…", "registrations": 1
  },
  "reregistered_after_expiry": false,
  "current_registration_start": null
}
```

`status` ist `unknown` (nie registriert), `pending` (Registrierung oder Erneuerung wartet im Mempool, `pending_ops` nennt die Transaktion), `confirmed` (aktiv in der Kette) oder `expired` (abgelaufen, Beweis weiterhin in der Historie). Dieselben Felder liefern `POST /v1/poe/verify` und `POST /v1/poe/verify/file`.

Der Beweis für Dritte ist immer die **erste Verankerung** in `first_anchored`: `txid`, `height`, `block_hash` und `block_time_iso` sind im Explorer nachprüfbar, `value`, `value_json` und `owner_address` zeigen Wert und Inhaber zu diesem Zeitpunkt (`owner_address` ist `null`, wenn die Namenshistorie ihn nicht liefert). `registrations` zählt die Operationen des Namens. Ist es `null`, war die Namenshistorie nicht verfügbar, und `first_anchored` beschreibt nur die aktuelle Operation, die auch eine spätere Registrierung sein kann. Die Felder auf oberster Ebene beschreiben den aktuellen Eintrag des Namens. Hat ein Name nur eine Registrierung, stimmen beide überein.

Nach Ablauf kann jeder denselben Hash neu registrieren. Dann steht `reregistered_after_expiry: true`. Die Felder `owner_address`, `value` und `value_json` auf oberster Ebene gehören in diesem Fall zur neuen Registrierung und nicht zum Nachweis, `current_registration_start` nennt `txid`, `height`, `block_time_iso` und `explorer_tx` der Operation, mit der die neue Registrierung begann. Als Neuregistrierung zählt eine Operation, die mindestens 36.000 Blöcke nach der vorherigen Operation desselben Namens kam. Aktualisierungen oder Verlängerungen durch den Inhaber vor dem Ablauf zählen nicht, dann bleibt `reregistered_after_expiry` bei `false` und `current_registration_start` bei `null`.

### Antwort beim Anlegen

HTTP 201 mit `txid`, `name`, `value`, `fee`, `status: pending` und dem Explorer-Link. Die API prüft nach dem Aufruf, ob die Node die Transaktion tatsächlich in den Mempool übernommen hat. Hat sie das nicht (zum Beispiel weil der Name in derselben Minute von jemand anderem registriert wurde), verwirft die API die Transaktion im Wallet und meldet 409. Nach dem nächsten Block liefert `GET /v1/poe/{hash}` Blockhöhe und Zeitstempel. Wenn der Hash schon aktiv registriert ist, antwortet die API mit 409 und nennt Block und Zeit der ersten Verankerung, es entsteht kein Doppeleintrag. Wartet bereits eine Registrierung im Mempool, ebenfalls 409.

**Abgelaufene Nachweise.** Ist der Name des Hashes abgelaufen, antwortet die API ebenfalls mit 409. Der frühere Nachweis bleibt in der Kettenhistorie gültig, die Meldung nennt Block und Zeit der ersten Verankerung. Eine neue Registrierung würde nur einen späteren Zeitstempel hinzufügen und Notiz und Inhaber des Namens ersetzen. Wer das bewusst will, schickt `"reanchor": true` mit (bei `POST /v1/poe/file` als Formularfeld `reanchor=true`):

```bash
curl -X POST https://doi-api.sendlabs.de/v1/poe -H "X-API-Key: <write-schluessel>" \
  -H "content-type: application/json" -d '{"hash":"<hash>","reanchor":true}'
```

Die Antwort enthält dann `reanchored_after_expiry: true` und für ältere Clients weiterhin `renewed` mit demselben Wert. Auf aktive oder wartende Nachweise hat `reanchor` keine Wirkung, dort bleibt es bei 409. Einen aktiven Nachweis verlängert nur der Inhaber über `POST /v1/name/doi` (Abschnitt 5).

### Beispiel: Nachweis mit Python anlegen und später prüfen

```python
import hashlib, requests
API, KEY = "https://doi-api.sendlabs.de/v1", "<write-schluessel>"
h = hashlib.sha256(open("vertrag.pdf", "rb").read()).hexdigest()
r = requests.post(f"{API}/poe", json={"hash": h, "filename": "vertrag.pdf"}, headers={"X-API-Key": KEY})
print(r.status_code, r.json())          # 201 und txid, 409 wenn schon vorhanden (auch abgelaufen ohne reanchor), 402 wenn das Wallet leer ist
# später: Nachweiszeitpunkt ist die erste Verankerung
print(requests.get(f"{API}/poe/{h}").json()["first_anchored"]["block_time_iso"])
```

## 5. Namen und `name_doi`

Doichain erbt von Namecoin ein Namensregister: Jeder Name gehört einer Adresse, trägt einen Wert (Text bis 520 Byte) und ist Teil einer Transaktion. Die Doichain-eigene Operation `name_doi` registriert oder aktualisiert einen Namen in einem Schritt. Namen sind frei wählbar (bis 255 Byte, die API normalisiert sie nach Unicode NFC und übergibt sie als UTF-8). Übliche Präfixe: `e/` für Double-Opt-In-Einträge der dApp (Name ist dort ein zufälliger 64-stelliger Hex-Wert, diese Einträge sind heute alle abgelaufen), `poe/` für Nachweise dieser API, `id/` in den Beispielen von Doichain Core.

| Aufruf | Stufe | Zweck |
|---|---|---|
| `GET /v1/name/{name}` | read | aktueller Wert, Inhaberadresse, Höhe, Ablauf. Aktiv: 200 mit `expired: false`. Abgelaufen: 200 mit `expired: true` und negativem `expires_in`. Unbekannt: 404. `pending: true` zeigt eine wartende Operation im Mempool, auch bei bestehenden Namen (Erneuerung, Aktualisierung) |
| `GET /v1/name/{name}/history` | read | alle bisherigen Werte und Inhaber |
| `GET /v1/names?prefix=poe/&count=100` | read | Namen durchsuchen, optionale Parameter `after`, `start`, `regexp` (nur mit write-Schlüssel, höchstens 64 Zeichen), `min_conf`, `include_expired`, `value_encoding`, siehe Blättern unten |
| `GET /v1/names/pending?name=` | read | unbestätigte Namensoperationen im Mempool |
| `POST /v1/name/doi` mit `{"name": "…", "value": "…", "dest_address": "optional", "name_encoding": "…", "value_encoding": "…"}` | write | registrieren, als Inhaber aktualisieren oder verlängern |
| `POST /v1/name/update` mit `{"name": "…", "value": "…", "dest_address": "…", "value_encoding": "…"}` | write | Namecoin-Update, mit `dest_address` wird der Name an eine andere Adresse übertragen. `value` weglassen oder leer lässt den Wert unverändert (einen leeren Wert setzt `name_doi` mit `"value": ""`), ohne `value` und ohne `dest_address` kommt 422 |
| `POST /v1/name/new` und `POST /v1/name/firstupdate` | write | klassische zweistufige Registrierung (erst `name_new`, nach 12 Blöcken `firstupdate` mit `rand` und `txid` aus Schritt 1). Für Doichain normalerweise unnötig, `name_doi` reicht |
| `GET /v1/wallet/names` | write | Namen, die das Node-Wallet hält |
| `POST /v1/name/sendtoname` mit `{"name": "…", "amount": 1.5, "comment": "…"}` | admin | DOI an den Inhaber eines Namens senden |

Namen mit Schrägstrich funktionieren direkt im Pfad: `GET /v1/name/poe/9f86d0…` oder `GET /v1/name/e/AB12…`. `value_encoding` und `name_encoding` erlauben `ascii`, `utf8` (Standard) oder `hex` für Binärdaten, leer gelassene Felder gelten als Standard. Ein Name, der jemand anderem gehört und nicht abgelaufen ist, lässt sich nicht überschreiben, die Node lehnt die Transaktion ab (409 oder 400 mit der Meldung der Node). Alle schreibenden Aufrufe (auch `sendtoname` und die Auszahlung) prüfen wie beim PoE, ob die Transaktion im Mempool angekommen ist. Die Node selbst dekodiert Namen und Werte seit dem 25.09.2026 überall als UTF-8 (`nameencoding=utf8`, `valueencoding=utf8` in ihrer Konfiguration), deshalb erscheinen Umlaute auch in Transaktions- und Blockansichten lesbar.

**Blättern in `GET /v1/names`.** Die Kette enthält rund 57.000 Namen, fast alle abgelaufen. Die API liest deshalb bis zu 5.000 Einträge je Aufruf und liefert davon bis zu `count` aktive (oder mit `include_expired=true` alle). Die Antwort enthält `scanned` (gelesene Einträge), `exhausted` (true, wenn nichts mehr folgt) und `next_after`. Zum Weiterblättern `after=<next_after>` übergeben, dieser Name selbst wird ausgeschlossen. Die Reihenfolge ist die der Node: erst nach Namenslänge, dann nach Bytewert, also nicht alphabetisch. `start` (einschließlich) und `after` (ausschließlich) sind deshalb nur Cursor zum Weiterblättern mit vollständigen Namen aus `next_after`, zum Eingrenzen `prefix` verwenden. Ein leeres `names` mit `exhausted: false` heißt nur, dass in den ersten 5.000 Einträgen nichts Aktives war, dann mit `after` weiterlesen.

Beispiel:

```bash
curl -X POST https://doi-api.sendlabs.de/v1/name/doi -H "X-API-Key: <write>" \
  -H "content-type: application/json" \
  -d '{"name":"id/doi-labs","value":"{\"web\":\"https://doi-labs.li\"}"}'
```

## 6. Kette, Blöcke, Transaktionen

| Aufruf | Zweck |
|---|---|
| `GET /v1/status` | Gesamtbild: Node-Version, Blockhöhe, Zeit des letzten Blocks, Fork-Prüfung, Mempool, ElectrumX, Wallet |
| `GET /v1/chain/info` | rohes `getblockchaininfo` |
| `GET /v1/blocks?count=10` | die letzten Blöcke mit Zeit und Transaktionszahl, `count` höchstens 50, optional `start=433000` als Ausgangshöhe (rückwärts) |
| `GET /v1/block/{höhe oder hash}?verbosity=1` | ein Block, `verbosity=2` liefert alle Transaktionen dekodiert (mit `block_time_iso`, Rohdaten nur mit `include_hex=true`). Höhe jenseits der Spitze: 404 |
| `GET /v1/tx/{txid}?include_hex=false` | Transaktion dekodiert, zusätzlich `name_ops` (alle Namensoperationen darin), `is_name_transaction`, `block_time_iso` |
| `POST /v1/tx/decode` mit `{"hex": "…"}` | Rohtransaktion dekodieren, ohne sie zu senden. Kaputtes Hex: 400. Body bis 1 MB |
| `POST /v1/tx/send` mit `{"hex": "…"}` (write) | signierte Rohtransaktion ins Netz geben, etwa aus einem externen Wallet. Body bis 1 MB |
| `GET /v1/mempool?limit=100` | Mempool-Größe und Transaktions-IDs, `limit` höchstens 1000 |
| `GET /v1/network` | Peers, Versionen, Verbindungszahl |

Die Fork-Prüfung in `/v1/status` und `/health` vergleicht Block 431018 mit `71d50ff1…`. Steht dort `ok: false`, folgt die Node der falschen Kette, dann Abschnitt 11.

## 7. Adressen

| Aufruf | Zweck |
|---|---|
| `GET /v1/address/{adresse}?with_count=false` | Guthaben (bestätigt und unbestätigt), Adresstyp. `with_count=true` liefert zusätzlich die Anzahl Transaktionen, lädt dafür aber die komplette Historie (bei Pool-Adressen mehrere MB) |
| `GET /v1/address/{adresse}/history?limit=50&details=false` | Transaktionsliste (neueste zuerst) mit `total`, `limit` höchstens 500, `details=true` liefert die ersten 25 Transaktionen dekodiert. ElectrumX liefert immer die ganze Historie, `limit` kürzt nur die Antwort |
| `GET /v1/address/{adresse}/utxos?limit=500&offset=0` | unverbrauchte Outputs mit `total` und `total_value`, `limit` höchstens 5000, `offset` zum Blättern |
| `GET /v1/validate/{adresse}` | Adresse prüfen (`isvalid`, scriptPubKey) |

Unterstützt werden alle Doichain-Adressformate: `N…` (P2PKH), `6…` (P2SH) und `dc1q…` (Bech32, SegWit v0). Bitcoin-Adressen und Tippfehler werden mit 400 abgewiesen. Die Daten kommen aus dem lokalen ElectrumX-Index, Doichain Core selbst hat keinen Adressindex. Beträge sind Zeichenketten mit acht Nachkommastellen. Hinweis: Namens-Outputs (0,01 DOI je Name) zählen zum Guthaben, sind aber nur zusammen mit dem Namen ausgebbar.

## 8. Wallet der Node

Das Wallet `doichain` auf der Node bezahlt Gebühren und die 0,01 DOI je Name für alle schreibenden Aufrufe. Es ist ein **Hot Wallet** auf einem Server, also nur mit Betriebsguthaben füllen (20 bis 50 DOI reichen für Hunderte Nachweise), nie mit Vermögen.

| Aufruf | Stufe | Zweck |
|---|---|---|
| `GET /v1/wallet/funding-address` | read | Einzahlungsadresse (Label `api-funding`), derzeit `NGTRDaWzP5o4wky4Uyx2CM5gDQo3Qw3MMn` |
| `GET /v1/wallet` | write | Guthaben, Transaktionszahl, Anzahl gehaltener Namen, Verschlüsselungsstatus |
| `POST /v1/wallet/address` mit `{"label": "…", "address_type": "bech32"}` | write | neue Empfangsadresse (`legacy` = N…, `p2sh-segwit` = 6…, `bech32` = dc1q…) |
| `GET /v1/wallet/transactions?count=25` | write | letzte Wallet-Transaktionen, `count` höchstens 200 |
| `GET /v1/wallet/utxos?min_conf=0` | write | unverbrauchte Outputs des Wallets |
| `POST /v1/wallet/abandon` mit `{"txid": "…"}` | write | eine unbestätigte Transaktion verwerfen, die nicht mehr im Mempool ist (gibt die gebundenen Coins frei) |
| `POST /v1/wallet/send` mit `{"address": "…", "amount": 1.0, "comment": "…", "subtract_fee_from_amount": false, "fee_rate_sat_vb": 100}` | admin | DOI auszahlen, feste Gebührenrate (Standard 100 sat/vB) |

Ist das Wallet leer, scheitern PoE und `name_doi` mit HTTP 402 „Insufficient funds". Das Wallet ist unverschlüsselt (sonst müsste die API vor jedem Schreibvorgang entsperren). Schutz kommt aus dem geringen Guthaben, der Rechtevergabe auf dem Server und den API-Schlüsseln.

## 9. Werkzeuge

| Aufruf | Stufe | Zweck |
|---|---|---|
| `GET /v1/fee` | read | Gebührenempfehlung: 100 sat/vB (0,001 DOI/kvB). Auf Doichain gibt es keinen Gebührenmarkt, `estimatesmartfee` liefert nie eine Schätzung |
| `POST /v1/message/verify` mit `{"address", "signature", "message"}` | read | signierte Nachricht prüfen (Eigentumsnachweis einer Adresse) |
| `POST /v1/message/sign` mit `{"address", "message"}` | admin | Nachricht mit einer Wallet-Adresse signieren |
| `POST /v1/rpc` mit `{"method": "getblockchaininfo", "params": [], "wallet": false}` | admin | jeden RPC-Befehl von Doichain Core direkt aufrufen. `params` als Liste (Positionsparameter) oder Objekt (benannte Parameter, zum Beispiel `{"height": 431018}` für `getblockhash`). Body bis 1 MB. Gesperrt sind Befehle, die Schlüsselmaterial preisgeben, Wallet-Dateien laden, Dateien schreiben oder die Node steuern (`dumpprivkey`, `dumpwallet`, `gethdkeys`, `listdescriptors`, `importprivkey`, `loadwallet`, `dumptxoutset`, `exportasmap`, `stop`, `setnetworkactive`, `addnode`, `sendmsgtopeer` und weitere), dazu vorbeugend alle Methoden, deren Name mit `dump`, `import`, `export`, `backup`, `restore`, `load`, `unload`, `generate`, `wait`, `gethd`, `sethd`, `addhd`, `derivehd`, `sendmsg` oder `encrypt` beginnt |

Über `/v1/rpc` ist auch alles erreichbar, was die API nicht eigens abbildet, zum Beispiel `getblockstats`, `gettxoutsetinfo` oder `name_checkdb`. Die vollständige Befehlsliste liefert `{"method": "help"}`.

## 10. Fehlerformat

Alle Fehler haben dieselbe Form, auch die, die nginx selbst erzeugt (413, 429, 502, 504):

```json
{"error": {"type": "rpc", "code": -6, "message": "Insufficient funds (Das Node-Wallet braucht Guthaben, siehe GET /v1/wallet/funding-address)"}}
```

| HTTP | Bedeutung |
|---|---|
| 400 | Eingabe fehlerhaft (ungültiger Hash, ungültige Adresse, Wert zu lang, Rohtransaktion nicht dekodierbar) oder die Node lehnt die Transaktion ab |
| 401 / 403 | Schlüssel fehlt beziehungsweise Stufe zu niedrig |
| 402 | Wallet ohne Guthaben |
| 404 | Name, Transaktion, Block oder Pfad nicht vorhanden (auch Blockhöhe jenseits der Spitze) |
| 405 | HTTP-Methode für diesen Pfad nicht erlaubt (etwa GET statt POST) |
| 409 | Nachweis existiert schon (auch abgelaufen, solange `reanchor` fehlt), Name gehört jemand anderem, Operation wartet im Mempool, Transaktion vom Mempool abgelehnt |
| 413 | JSON-Anfrage über 64 KB, Rohtransaktion über 1 MB oder Datei über 50 MB (dann den Hash lokal berechnen und als JSON schicken) |
| 422 | JSON-Body oder Parameter passen nicht zum Schema (Feld fehlt, falscher Typ, Notiz zu lang, PoE-Wert über 520 Byte, `count` über dem Maximum, unbekannte Kodierung) |
| 423 | Wallet gesperrt |
| 429 | Ratenbegrenzung |
| 500 | interner Fehler der API, Details im Journal des Dienstes |
| 502 / 503 / 504 | unerwarteter Node-Fehler, Node oder ElectrumX nicht erreichbar, Node synchronisiert noch, Zeitüberschreitung |

`type` ist `rpc` (Meldung der Node mit ihrem Fehlercode), `http`, `validation`, `node`, `electrum` oder `internal`. Die OpenAPI-Beschreibung enthält dieses Schema für alle Fehlerantworten.

## 11. Betrieb auf dem Server

| Bestandteil | Ort oder Befehl |
|---|---|
| Server | doi-btc-node, `ssh root@136.243.155.62` (Schlüssel `claude-code-paperless` und Davids Schlüssel) |
| API-Dienst | `systemctl status doichain-api`, Neustart `systemctl restart doichain-api`, Log `journalctl -u doichain-api -f`, nur Warnungen `journalctl -u doichain-api -p warning` |
| Code | `/opt/doichain-api/app/doichain_api/` (`main.py` Endpunkte, `rpc.py` Node-Anbindung, `electrum.py` Adressindex, `auth.py` Schlüssel, `config.py` Einstellungen) |
| Konfiguration | `/etc/doichain-api/doichain-api.env`, nach Änderung Dienst neu starten |
| MCP-Dienst | `systemctl status doichain-mcp`, Log `journalctl -u doichain-mcp -f`, Code `/opt/doichain-mcp/app/doichain_mcp/server.py`, eigene venv `/opt/doichain-mcp/venv`, Umgebung `/etc/doichain-mcp/doichain-mcp.env` (erzeugt der Installer bei jedem Lauf, nur API-Adresse und öffentlicher poe-Schlüssel), Benutzer `doimcp`, Port 127.0.0.1:8081 |
| Landingpages | `/var/www/doichain-api-site` (API), `/var/www/verifile` (Verifile), `/var/www/doichain-mcp-site` (MCP) |
| nginx | `/etc/nginx/sites-available/doichain-api`, Logs `/var/log/nginx/doichain-api.access.log` und `.error.log`, prüfen mit `nginx -t`, neu laden mit `systemctl reload nginx` |
| Node | `systemctl status doichaind`, Befehle `doichain-cli -datadir=/home/doichain/.doichain <befehl>`, Log `/home/doichain/.doichain/debug.log`, Konfiguration `doichain.conf` daneben |
| ElectrumX | `systemctl status electrumx`, Konfiguration `/etc/electrumx.conf`, Port 50001 lokal |
| Quellcode | GitHub-Repo **https://github.com/neubuot/doichain-api** (privat, seit 25.09.2026), lokaler Klon `C:\Users\ottma\doichain-api`. Dort liegen auch `CHANGELOG.md`, die Vorlage der Umgebungsdatei und eine Kopie dieses Handbuchs |
| Update der API | im lokalen Klon `bash deploy/push-to-server.sh` (kopiert das Arbeitsverzeichnis nach `/root/doichain-api-src` und führt dort `deploy/install.sh` aus), alternativ auf dem Server den Quellcode nach `/root/doichain-api-src` laden und `bash /root/doichain-api-src/deploy/install.sh` starten. Das Skript legt auf einem frischen Server auch Benutzer, venv, Zertifikat, Umgebungsdatei und Einzahlungsadresse an. Sobald certbot die nginx-Datei angefasst hat, lässt das Skript sie unverändert und weist darauf hin, damit das echte Zertifikat nicht überschrieben wird. **Jede Codeänderung ist erst nach diesem Schritt aktiv** |
| Überwachung | Uptime Kuma Monitor 82 „Doichain API (doi-btc-node)" prüft `/health` auf `"ok":true`. `/health` liefert 503, wenn die Node noch synchronisiert, mehr als 6 Header vorausliegen, der letzte Block älter als drei Stunden ist oder die Fork-Prüfung scheitert. NOC-Eintrag „Doichain API", Checkmk-Host doi-btc-node (nur Ping) |
| Firewall | ufw: 22, 80, 443, 8333 (Bitcoin), 8338 (Doichain). Alles andere nur lokal |

Einstellungen in der Umgebungsdatei:

| Variable | Bedeutung | Standard |
|---|---|---|
| `DOI_RPC_URL`, `DOI_RPC_USER`, `DOI_RPC_PASSWORD`, `DOI_RPC_WALLET` | Zugang zur Node (nur 127.0.0.1) und Wallet-Name | `http://127.0.0.1:8339/`, `doichain` |
| `DOI_ELECTRUM_HOST`, `DOI_ELECTRUM_PORT` | lokaler ElectrumX für Adressabfragen | 127.0.0.1, 50001 |
| `DOI_EXPLORER_URL` | Basis der Explorer-Links | https://doi-explorer.le-space.de |
| `DOI_PUBLIC_READ` | Lesen ohne Schlüssel erlauben | true |
| `DOI_API_KEYS_READ`, `DOI_API_KEYS_POE`, `DOI_API_KEYS_WRITE`, `DOI_API_KEYS_ADMIN` | Schlüssel je Stufe, kommagetrennt | |
| `DOI_POE_PUBLIC_PER_IP_DAY`, `DOI_POE_PUBLIC_PER_DAY` | Tageskontingent des poe-Schlüssels je IP-Adresse und insgesamt | 10, 200 |
| `DOI_STATE_DIR` | Ablage der Kontingent-Datenbank (systemd `StateDirectory`) | `/var/lib/doichain-api` |
| `DOI_POE_PREFIX` | Namenspräfix der Nachweise | `poe/` (nicht mehr ändern, sobald Nachweise existieren) |
| `DOI_MAX_UPLOAD_BYTES` | Upload-Grenze der API (nginx erlaubt 52 MB) | 52428800 (50 MB) |

**Node aktualisieren** (nächstes Release): Assets von https://github.com/Doichain/doichain-core/releases laden, `sha256sum -c SHA256SUMS` und `gpg --verify SHA256SUMS.asc SHA256SUMS` (Schlüssel `52A2 1926 E3F2 74AA 1F2D 9CDA 9BA0 ED44 F14E 8118`, Nico Krause, auf dem Server bereits importiert), alte Binaries als `.bak-JJJJMMTT` sichern, `systemctl stop doichaind`, Binaries per `install -m 0755` nach `/usr/local/bin/`, `systemctl start doichaind`, danach `getblockhash 431018` prüfen. Die Release-Notes sagen, ob ein Reindex nötig ist (bei v31.1.5 und v31.1.6 nicht).

**Wenn etwas hakt:** `/health` liefert 503 mit `problems` → dort steht der Grund. Keine Antwort → `systemctl status doichain-api` und `journalctl -u doichain-api -n 50`. `/v1/status` meldet `initial_block_download: true` oder eine alte Blockhöhe → Node prüfen (`getblockchaininfo`, `getpeerinfo`, `debug.log`). `electrumx.reachable: false` → `systemctl status electrumx`. Adressabfragen liefern 503, obwohl die Node läuft → ElectrumX hängt hinter der Node, kurz warten oder Dienst neu starten. Eine Wallet-Transaktion hängt unbestätigt fest → `POST /v1/wallet/abandon`.

**Browser zeigt „Nicht sicher" trotz gültigem Zertifikat.** Wer bei einem früheren Zertifikatsfehler dieses Hosts (etwa dem selbstsignierten Übergangszertifikat vom 25.09.2026) auf „trotzdem fortfahren" geklickt hat, sieht in Chrome danach für die gesamte Laufzeit des Browserprozesses ein rotes „Nicht sicher", obwohl der Zertifikatsdialog „gültig" meldet. Chrome merkt sich je Hostname im Arbeitsspeicher, dass Skripte mit umgangenem Zertifikatsfehler liefen. Tab schließen, neues Fenster oder Browserdaten löschen helfen nicht, `chrome://restart` in der Adressleiste behebt es. Gegenprobe: im Inkognito-Fenster ist die Seite sofort „sicher".

## 12. KI-Agenten (MCP-Server)

Seit Version 1.4.0 gibt es die Doichain auch als Werkzeugkasten für KI-Agenten. Das **Model Context Protocol (MCP)** ist der offene Standard, über den Claude, ChatGPT, Cursor, VS Code und viele andere KI-Anwendungen externe Werkzeuge einbinden. Einmal eingetragen, entscheidet der Agent selbst, wann er welches Werkzeug nutzt. Man sagt ihm einfach „Verankere den Hash von angebot.pdf in der Doichain" oder „Läuft d/beispiel bald ab?".

**Adresse:** `https://doi-api.sendlabs.de/mcp` (Transport Streamable HTTP, keine Anmeldung). Wer dieselbe Adresse im Browser öffnet, bekommt die Landingpage mit Beispielen, Einbauanleitung für die gängigen Programme, Werkzeugliste, Sicherheitshinweisen und FAQ (Deutsch und Englisch).

### Einbinden

| Programm | So geht es |
|---|---|
| Claude Code | `claude mcp add --scope user --transport http doichain https://doi-api.sendlabs.de/mcp` (ohne `--scope user` nur im aktuellen Projekt), prüfen mit `claude mcp list` |
| Claude (Web und Desktop) | Anpassen → Konnektoren → + → Benutzerdefinierten Konnektor hinzufügen (englisch Customize → Connectors → Add custom connector), Name „Doichain“, URL eintragen. Auch im kostenlosen Tarif (ein eigener Konnektor), in Team und Enterprise richtet ihn ein Owner ein. Im Chat über + → Konnektoren einschalten |
| ChatGPT | Einstellungen → Sicherheit und Anmeldung → Entwicklermodus einschalten, dann unter Plugins mit + eine App mit der Adresse anlegen, Authentifizierung „Keine“ (nur Plus, Pro, Business, Enterprise, Education im Web) |
| Cursor | `~/.cursor/mcp.json`: `{"mcpServers": {"doichain": {"url": "https://doi-api.sendlabs.de/mcp"}}}` |
| VS Code | `.vscode/mcp.json`: `{"servers": {"doichain": {"type": "http", "url": "https://doi-api.sendlabs.de/mcp"}}}` |

### Die 13 Werkzeuge

| Werkzeug | Wofür |
|---|---|
| `anchor_proof` | Hash eines Dokuments verankern (einziges schreibendes Werkzeug). Ist der Hash schon verankert, kommt der bestehende Nachweis zurück. Einen abgelaufenen Hash verankert es nur mit `reanchor_expired: true` erneut, das fügt einen späteren Zeitstempel hinzu und lässt den ursprünglichen Nachweis unverändert |
| `check_proof` | Ist der Hash verankert, seit wann, in welchem Block. Nennt immer die erste Verankerung als Nachweiszeitpunkt und führt eine spätere Registrierung getrennt auf |
| `hash_text` | SHA-256 eines kurzen Textes (bis 40.000 Zeichen), um Aussagen oder Nachrichten zu verankern. Der Text geht an den Server, wird dort aber nicht gespeichert. Dateien hasht der Agent selbst, zum Beispiel mit `sha256sum`, dafür braucht er Dateizugriff (Claude Code, Cursor, VS Code). Im reinen Chat ist Verifile der einfachere Weg |
| `get_anchoring_quota` | verbleibende Nachweise des Tages |
| `lookup_name`, `get_name_history`, `search_names` | Namen lesen, ihre Historie, Suche nach Präfix (`search_names` mit `include_expired` auch abgelaufene Namen) |
| `check_name_expiry` | bis zu 25 Namen auf einmal: aktiv, läuft bald ab, abgelaufen oder frei. Für aktive Namen ein geschätztes Datum aus dem gemessenen Blockabstand (derzeit gut 9 Minuten), für abgelaufene das echte Ablaufdatum aus der Kette |
| `get_chain_status`, `get_block`, `get_transaction`, `get_address`, `verify_message` | Zustand der Kette, Blöcke, Transaktionen, Adressguthaben, signierte Nachrichten prüfen |

### Wie es gebaut ist

- Eigener Dienst `doichain-mcp` (Python, MCP-SDK 2.2) unter eigenem Benutzer `doimcp`. Er ruft ausschließlich die REST-API auf und hat keinen Zugriff auf RPC, Wallet oder die Schlüsseldatei der API. Es gibt keine Werkzeuge für Auszahlungen, Namensänderungen oder den RPC-Durchgriff.
- Verankern nutzt denselben öffentlichen poe-Schlüssel wie Verifile, also dasselbe Tageskontingent: **10 Nachweise am Tag je IP-Adresse, für alle zusammen höchstens 200 am Tag**. Gehostete Apps (Claude im Browser, ChatGPT) verbinden sich aus den Rechenzentren ihrer Anbieter, deren Nutzer teilen sich also das Kontingent dieser Adressen. Für regelmäßiges Verankern Claude Code, Cursor oder VS Code nutzen oder einen eigenen Schlüssel vergeben. `check_proof` nennt immer die erste Verankerung, auch wenn der Name nach seinem Ablauf später erneut registriert wurde. Inhaber und Notiz einer späteren Registrierung stehen getrennt davon. Die Namen gehören dem Wallet von DOI Labs, das die Verankerungen bezahlt. nginx gibt die Adresse des Aufrufers als `X-Real-IP` mit, der MCP-Server reicht sie an die API weiter. Wer einen eigenen write-Schlüssel im Header `X-API-Key` mitschickt, hat kein Kontingent. `Authorization: Bearer` wertet der MCP-Server nur aus, wenn der Betreiber `DOI_MCP_ACCEPT_BEARER=true` setzt (Standard aus), damit fremde Token von Clients und Gateways nicht an die API gehen.
- Namen und Werte, die Fremde in die Kette geschrieben haben, tragen in den Antworten die Endung `_untrusted` und einen Hinweis. So behandelt ein Agent sie als Daten und nicht als Anweisung (Schutz gegen Prompt-Injection über die Blockchain).
- Zustandslos mit JSON-Antworten, deshalb unproblematisch hinter nginx und mit zwei Workern. Unterstützt die Protokollversionen 2024-11-05 bis 2026-07-28, getestet mit den offiziellen Clients der SDK-Versionen 1.30 und 2.2. Keine JSON-RPC-Batches, keine Clients direkt im Browser (kein CORS). Höchstens sechs gleichzeitige Aufrufe an die REST-API je Worker, Namen fragt der Server eindeutig über `GET /v1/name?name=…` ab.
- Der Dienst darf nur lokale Verbindungen aufbauen und annehmen (`IPAddressDeny=any`, `IPAddressAllow=localhost`), dazu Systemaufruf-Filter und weitere systemd-Schutzoptionen.
- nginx: eigene Ratenzone (10 Anfragen je Sekunde und IP, Burst 40), Anfragen bis 256 KB, `GET /mcp` im Browser zeigt die Landingpage, sonst 405 mit `Allow: POST`, eigene Fehlermeldungen im JSON-RPC-Format für 405, 413 und 429, `/mcp/health` für die Überwachung (ebenfalls begrenzt). Der Server prüft zusätzlich Host und Origin (Schutz gegen DNS-Rebinding).
- Öffentliches Repo https://github.com/neubuot/doichain-mcp, Eintrag im offiziellen MCP-Verzeichnis `io.github.neubuot/doichain` seit 26.09.2026 (Abschnitt 13, Punkt 8).

## 13. Nächste Schritte

1. **Hostname und Zertifikat.** Erledigt am 25.09.2026 für `doi-api.sendlabs.de` (Let's Encrypt per certbot, automatische Erneuerung, HSTS). Offen ist nur `api.doi.zone`: Sobald David die Zone doi.zone umgezogen hat und der Name auf 136.243.155.62 zeigt, auf dem Server `certbot --nginx -d doi-api.sendlabs.de -d api.doi.zone --expand` ausführen. `api.doi.zone` steht bereits als `server_name` in der nginx-Datei, der MCP-Server erlaubt den Namen ebenfalls. Spätere API-Updates lassen die von certbot bearbeitete nginx-Datei in Ruhe (Abschnitt 11).
2. **Wallet füllen.** Erledigt am 25.09.2026 (50 DOI an `NGTRDaWzP5o4wky4Uyx2CM5gDQo3Qw3MMn`). Nachfüllen, wenn `GET /v1/wallet` unter etwa 5 DOI meldet, jeder Nachweis kostet rund 0,0105 DOI.
3. **Erster Nachweis.** Erledigt am 26.09.2026 (README.md und CHANGELOG.md des Repos per API, ein Testnachweis über die Verifile-App). Noch offen: einmal `POST /v1/wallet/send` mit einem Kleinstbetrag an eine eigene Adresse, damit auch die Auszahlung einmal geprüft ist.
4. **Verifile-Domain.** Erledigt am 26.09.2026: `verifile.it` und `www.verifile.it` zeigen auf 136.243.155.62, Zertifikat per certbot (Erneuerung automatisch), HSTS, www leitet auf verifile.it. Der Installer lässt die certbot-verwaltete nginx-Datei `/etc/nginx/sites-available/verifile` in Ruhe.
5. **Datenschutzhinweis** für Verifile und Landingpage (beide setzen keine Cookies und laden nichts von Dritten, ein kurzer Hinweis genügt). Das Impressum beider Seiten verlinkt seit 26.09.2026 auf https://www.doichain.org/en/imprint/, der DOI-Labs-Link auf https://www.doichain.org/en/.
6. **David informieren** (Gmail-Entwurf „doi-btc-node: Node auf v31.1.6 und neue REST-API" liegt bereit).
7. Optional: `DOI_PUBLIC_READ=false` setzen und Leseschlüssel vergeben, wenn die API nicht öffentlich lesbar sein soll.
8. **MCP-Server bekannt machen.** Erledigt am 26.09.2026: öffentliches Repo **https://github.com/neubuot/doichain-mcp** (MIT, README englisch und deutsch, Werkzeugreferenz, Anleitung zum Selbstbetrieb, 21 Offline-Tests, CI für Python 3.11 bis 3.13, 14 Themen-Tags, vertrauliche Sicherheitsmeldungen aktiv, Release v1.4.1) und Eintrag im offiziellen MCP-Verzeichnis als `io.github.neubuot/doichain` (Status aktiv). Neue Versionen: im öffentlichen Repo Version in `pyproject.toml`, `server.json`, `doichain_mcp/__init__.py` und `server.py` anheben, Tag `vX.Y.Z` pushen, der Workflow veröffentlicht per GitHub-OIDC ohne gespeicherten Schlüssel. Den Code gleicht `deploy/sync-public-mcp.sh` im privaten Repo ab. Optional später: Smithery, Glama, mcp.so (übernehmen Einträge teils automatisch) und das Konnektor-Verzeichnis von Anthropic (Antrag nötig).

## 14. Sicherheit in Kürze

- Schlüssel nur in der Umgebungsdatei und in Vaultwarden. Der admin-Schlüssel erlaubt Auszahlungen.
- Das Node-Wallet ist ein Hot Wallet mit Betriebsguthaben, nie mehr als nötig einzahlen.
- RPC der Node und ElectrumX sind nur lokal erreichbar, von außen gibt es nur nginx auf 443 (und 80 als Umleitung). nginx verrät keine Version, Einbettung in fremde Seiten ist unterbunden, TLS nur mit Forward-Secrecy-Verfahren (ECDHE), keine Sitzungs-Tickets.
- Ratenbegrenzung in nginx, JSON-Anfragen bis 64 KB, Rohtransaktionen bis 1 MB, Uploads bis 50 MB nur auf den zwei Datei-Endpunkten mit eigener engerer Begrenzung, reguläre Ausdrücke in der Namenssuche nur mit Schlüssel, Sperrliste plus Präfixregel im RPC-Durchgriff, gehärteter systemd-Dienst ohne Schreibrecht auf dem System.
- Let's-Encrypt-Zertifikat für `doi-api.sendlabs.de` seit 25.09.2026 mit HSTS, automatische Erneuerung durch certbot.
- Der MCP-Server läuft getrennt unter eigenem Benutzer, kennt nur den öffentlichen poe-Schlüssel und kann weder Coins senden noch Namen ändern. Ketteninhalte kennzeichnet er als nicht vertrauenswürdig.

## 15. Hintergrund

**Doichain in einem Absatz.** Doichain ist ein Namecoin-Fork der Bitcoin-Familie (UTXO, SegWit, Merged Mining mit Bitcoin). P2P-Port 8338, RPC-Port 8339, Adressen `N…`, `6…`, `dc1q…`, 8 Nachkommastellen. Am 11.09.2026 gab es bei Block 431017 einen Sicherheits-Fork (DigiShield v3, Prüfung der Difficulty, strikte Eigentümerschaft für `name_doi`), die Kette trennt sich bei 431018 (`71d50ff1…`). Details in der Integrationsspezifikation.

**Was die Doichain-dApp zusätzlich kann.** Auf demselben Server läuft Davids Installation der Meteor-basierten Doichain-dApp v0.0.9 (Port 3000, nur lokal). Sie setzt das eigentliche **Double-Opt-In-Protokoll für E-Mail-Einwilligungen** um (Sender-, Confirm- und Verify-dApp, DNS-TXT-Schlüssel, verschlüsselte Mailvorlagen, Bestätigungslinks, `blocknotify`/`walletnotify` der Node zeigen darauf). Ihre eigene JSON-API (`/api/v1/login`, `opt-in`, `opt-in/confirm/:hash`, `opt-in/verify`, `export`, `users`) ist in `/home/doichain/dapp/doc/en/json-rpc-api.md` beschrieben. Die REST-API dieses Handbuchs ersetzt die dApp nicht, sie deckt alles Übrige ab (Kette, Namen, PoE, Wallet). Wer das E-Mail-DOI-Protokoll nutzen will, braucht die dApp mit SMTP-Zugang und DNS-Einträgen, das ist ein eigenes Projekt.

**ElectrumX.** Der Doichain-Fork von ElectrumX (Version 2.0.0, mit Namensindex) liefert Adressguthaben und -historien. Er hört lokal auf 50001 (TCP) und 50002/50004 (TLS, selbstsigniert). Für Electrum-DOI-Wallets von außen wären die Ports zu öffnen und ein echtes Zertifikat einzubinden, das ist bewusst nicht geschehen.

## 16. Verwandt

- Einrichtungsbericht 2026-09-25 – Doichain-API auf doi-btc-node
- 2026-08-30 Hetzner-Serverbestellung – Doichain-Node-Server · Server-Gesamtübersicht
- Doichain Technische Integrationsspezifikation – DOI und wDOI (DE) · Konzept 2026-08-01 – Doichain-Integration in DocuSeal
- Doichain Core: https://github.com/Doichain/doichain-core · Explorer: https://doi-explorer.le-space.de

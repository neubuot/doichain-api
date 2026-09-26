# Changelog

Alle nennenswerten Änderungen der Doichain API. Datumsangaben im Format JJJJ-MM-TT.

## 1.4.1 (2026-09-26)

Kurze Prüfrunde des MCP-Servers (drei Prüfer, ein Gegenprüfer, 41 Meldungen, alle bestätigt, viele doppelt) eingearbeitet.

- REST-API: neue Namensabfragen per Query-Parameter `GET /v1/name?name=…` und `GET /v1/names/history?name=…`. Namen, die auf `/history` enden, landeten im Pfadformat bei der Historie des kürzeren Namens. Der MCP-Server nutzt nur noch die neuen Endpunkte.
- REST-API: `GET /v1/poe/{hash}` liefert `first_anchored` (erste Verankerung aus `name_history`). Wird ein abgelaufener Nachweis später erneut verankert, bleibt der erste Zeitpunkt der Nachweiszeitpunkt. MCP-Werkzeug `check_proof` und Verifile zeigen ihn an.
- REST-API: `/v1/status` meldet `wallet.public_poe_available` (Reserve von 5 DOI erreicht), `get_chain_status` und die Landingpage nutzen das Flag.
- MCP: echte Ablaufzeit für abgelaufene Namen (Block Höhe plus 36.000) statt einer Rückrechnung über den heutigen Blockabstand, Namen aus Suche und Transaktionen als `name_untrusted` gekennzeichnet, englische Fehlertexte mit dem deutschen Detail der API, Bearer-Token von Gateways werden ignoriert (Rückfall auf den öffentlichen Schlüssel), `hash_text` höchstens 40.000 Zeichen, `get_block` nimmt auch Zahlen, Transaktions-IDs mit `0x`, leere Präfixe abgewiesen, Adressen vorab geprüft, `verify_message` nennt die Beschränkung auf Legacy-Adressen.
- MCP: höchstens sechs gleichzeitige Aufrufe an die REST-API je Worker, Zwischenspeicher für Namens- und Blockabfragen, Ergebnis von `/mcp/health` 15 Sekunden gespeichert, ruhiges Journal ohne Zugriffsprotokoll (nginx protokolliert).
- nginx: eigene JSON-RPC-Fehlerseiten für 405 (mit `Allow: POST`), 413 und 429 (mit `Retry-After`) auf `/mcp`, Ratenzone 10 je Sekunde mit Burst 40, Ratenbegrenzung auch auf `/mcp/health`, CSP der Landingpage ohne Fremdquellen.
- systemd: `doichain-mcp` nur noch mit lokalen Verbindungen (`IPAddressDeny=any`, `IPAddressAllow=localhost`), Systemaufruf-Filter, keine Capabilities, weitere Schutzoptionen.
- Landingpage: aktuelle Menüpfade für Claude (Anpassen → Konnektoren, auch im kostenlosen Tarif) und ChatGPT (Entwicklermodus unter Sicherheit und Anmeldung, bezahlte Tarife), `claude mcp add --scope user`, ehrliche Angaben zu `hash_text`, Kontingent, Protokollen und Browser-Clients, neuer FAQ-Punkt zu gehosteten Apps, Reiter mit Tastatur und ARIA, Titel ohne Halbgeviertstrich.
- Alle drei Seiten (API, Verifile, MCP) ohne Google Fonts, sie nutzen Systemschriften.
- MCP-Server zusätzlich als öffentliches Repo https://github.com/neubuot/doichain-mcp (MIT) mit englischer README, Werkzeugreferenz, Anleitung zum Selbstbetrieb, Offline-Tests, CI und Veröffentlichung im offiziellen MCP-Verzeichnis (`io.github.neubuot/doichain`) per GitHub Actions. `server.json` liegt nur noch dort, Abgleich per `deploy/sync-public-mcp.sh`. Code-Kommentare in `server.py` auf Englisch.
- Bewusst belassen: Das SDK meldet leere Prompt- und Ressourcenlisten als Fähigkeiten an, und JSON-RPC-Batches lehnt es ab. Beides ist Standardverhalten des MCP-SDK 2.2 und für Clients unschädlich.

## 1.4.0 (2026-09-26)

MCP-Server für KI-Agenten.

- **Doichain MCP-Server** (`doichain_mcp/server.py`, MCP-SDK 2.2): 13 Werkzeuge für Agenten, `anchor_proof`, `check_proof`, `hash_text`, `get_anchoring_quota`, `lookup_name`, `get_name_history`, `check_name_expiry`, `search_names`, `get_chain_status`, `get_block`, `get_transaction`, `get_address`, `verify_message`. Streamable HTTP, zustandslos, JSON-Antworten, Protokolle 2024-11-05 bis 2026-07-28, Werkzeugannotationen (nur `anchor_proof` schreibt).
- Eigener Dienst `doichain-mcp` (Benutzer `doimcp`, 127.0.0.1:8081, eigene venv) ohne Zugriff auf RPC, Wallet und die Schlüsseldatei der API. Ruft ausschließlich die REST-API auf und reicht die Client-IP aus `X-Real-IP` als `X-Forwarded-For` weiter, damit das Tageskontingent je Aufrufer gilt. Eigener Schlüssel optional per `X-API-Key` oder `Authorization: Bearer`.
- Werte aus der Kette tragen die Endung `_untrusted` und einen Hinweis, damit Agenten sie nicht als Anweisung lesen. Bereits verankerte Hashes liefert `anchor_proof` als bestehenden Nachweis zurück, statt einen Fehler zu melden. Ablaufdaten schätzt `check_name_expiry` aus dem gemessenen Blockabstand der letzten 1000 Blöcke.
- nginx: `/mcp` für MCP-Clients (eigene Ratenzone 5/s, 256 KB), Browser bekommen unter derselben Adresse die Landingpage, `GET` ohne HTML ergibt 405, `/mcp/` leitet mit 308 um, `/mcp/health` für die Überwachung. Host- und Origin-Prüfung im Server (DNS-Rebinding-Schutz).
- **Landingpage des MCP-Servers** (`web/mcp-site`): Beispiele, Einbauanleitung für Claude Code, Claude, ChatGPT, Cursor, VS Code und andere Clients, Werkzeuge, Sicherheit, FAQ, Deutsch und Englisch, Live-Status, strenge Content-Security-Policy ohne Inline-Skripte.
- `server.json` für das offizielle MCP-Verzeichnis, API-Landingpage verlinkt den MCP-Server, Installer richtet Benutzer, venv, Umgebungsdatei, Dienst und Seite ein.
- Erster Nachweis über MCP am 26.09.2026 (Transaktion `a7af1851…`).

## 1.3.0 (2026-09-26)

Web-Oberflächen und öffentlicher Nachweis-Schlüssel.

- Neue Schlüsselstufe **poe** (`DOI_API_KEYS_POE`): darf nur Nachweise anlegen (`POST /v1/poe`, `POST /v1/poe/file`), mit Tageskontingent je IP-Adresse (`DOI_POE_PUBLIC_PER_IP_DAY`, Standard 10) und insgesamt (`DOI_POE_PUBLIC_PER_DAY`, Standard 200). Zähler in `/var/lib/doichain-api/quota.db` (systemd `StateDirectory`), Abfrage über `GET /v1/poe/quota`. write- und admin-Schlüssel bleiben ohne Kontingent.
- **Verifile** (`web/verifile`): PoE-Web-App. Datei per Drag-and-drop, SHA-256 im Browser (hash-wasm, gestückelt, beliebige Dateigröße, Rückfall auf Web Crypto), kein Upload, Status-Abfrage, Verankerung mit poe-Schlüssel, automatische Aktualisierung bis zur Bestätigung, Nachweis als JSON und Druckansicht, Prüfung per Hash-Eingabe oder `#<hash>` in der Adresse, Deutsch und Englisch. Konfiguration `config.js` wird vom Installer aus der Umgebungsdatei erzeugt.
- **Landingpage der API** (`web/api-site`): Erklärung, Live-Status, Spielwiese mit lesenden Aufrufen, Codebeispiele für curl, Python und JavaScript, Zugriffsstufen, Entwickler-Links. Ausgeliefert unter `/` des API-Hosts, die Verifile-App zusätzlich unter `/poe/`.
- nginx-Vorlage `deploy/nginx-verifile.conf` für verifile.app und verifile.it (Port 80 mit ACME-Pfad, Content-Security-Policy, certbot ergänzt 443).
- Erste echte Nachweise auf der Produktivinstanz (README.md und CHANGELOG.md dieses Repos, 26.09.2026).
- Verifile seit 26.09.2026 unter https://verifile.it/ (A-Records im 1blu-KSB, Let's Encrypt per certbot, HSTS, www leitet auf den Hauptnamen).
- Nachbesserung nach der dritten Prüfrunde (26.09.2026): hash-wasm wird selbst ausgeliefert (`web/verifile/vendor`, SHA-384 gegen die CDN-Fassung geprüft), CSP mit `'wasm-unsafe-eval'` und ohne CDN, Rückfall auf Web Crypto bei Bibliotheksfehlern, Dateiname geht nur noch mit gesetztem Häkchen auf die Kette, alle API-Werte in der Anzeige maskiert, Kontingent wird bei fehlgeschlagener Verankerung zurückgegeben, öffentliche Nachweise pausieren unter 5 DOI Wallet-Reserve, IPv6 je /64, atomare Zählung (`BEGIN IMMEDIATE`), `config.js` ohne Cache, `/poe` leitet auf `/poe/`, Fortschrittsanzeige sichtbar, leere Dateien abgewiesen, 409/429 sauber behandelt, Polling bis 6 Stunden, Live-Regionen für Screenreader. Hinweis: Die am 26.09. verankerten Hashes von README.md und CHANGELOG.md gehören zum Stand des ersten 1.3.0-Commits, spätere Änderungen an den Dateien ergeben andere Hashes.
- Nachtrag 26.09.2026: Impressum beider Seiten zeigt auf https://www.doichain.org/en/imprint/, der DOI-Labs-Link auf https://www.doichain.org/en/ (der frühere Verweis auf doi-labs.li ist entfallen).

## 1.2.0 (2026-09-25)

Zweite unabhängige Prüfrunde (27 bestätigte Befunde) eingearbeitet.

- RPC-Sperrliste um die Befehle aus Bitcoin Core 28 bis 31 erweitert (`gethdkeys`, `derivehdkey`, `addhdkey`, `createwalletdescriptor`, `exportwatchonlywallet`, `exportasmap`, `sendmsgtopeer`, `importprunedfunds`, `addconnection`) und Präfixregel (`dump`, `import`, `export`, `backup`, `restore`, `load`, `unload`, `generate`, `wait`, `gethd`, `sethd`, `addhd`, `derivehd`, `sendmsg`, `encrypt`) ergänzt.
- `regexp` in `GET /v1/names` nur noch mit write-Schlüssel und höchstens 64 Zeichen (Backtracking-Ausdrücke gegen die Node).
- 404 und 405 des Routers im API-Fehlerformat, OpenAPI um 402, 405, 413, 423, 500 und 504 ergänzt.
- Schlüsselvergleich auf Byte-Ebene, Startprüfung der konfigurierten Schlüssel (ASCII, mindestens 16 Zeichen), nur gewöhnliche Leerzeichen werden abgeschnitten.
- Fehlermeldung ungültiger Adressen enthält die Begründung der Node (Feld `error`).
- PoE-Werte über 520 Byte werden mit 422 abgelehnt statt still gekürzt.
- `POST /v1/name/update`: leerer Wert lässt den Wert unverändert, ohne `value` und `dest_address` kommt 422.
- Leere Kodierungs- und Filterparameter gelten als Standard, unbekannte Kodierung ergibt 422.
- `GET /v1/name/{name}` meldet `pending` auch bei bestehenden Namen.
- `GET /v1/block/{id}?verbosity=2` setzt `block_time_iso` je Transaktion und liefert Rohdaten nur mit `include_hex=true`.
- `sendtoname` und `POST /v1/wallet/send` prüfen die Mempool-Annahme wie die Namensoperationen.
- nginx: Rohtransaktionen und RPC-Durchgriff bis 1 MB, Upload-Pfade auch mit Schrägstrich, nur ECDHE-Cipher, keine Sitzungs-Tickets.
- install.sh lässt eine von certbot bearbeitete nginx-Datei unverändert, Zertifikat enthält `doi-api.sendlabs.de`.
- Beschreibung der Sortierung in `GET /v1/names` (Namenslänge, dann Bytewert).
- Node-Konfiguration der Produktivinstanz: `nameencoding=utf8`, `valueencoding=utf8`.

## 1.1.0 (2026-09-25)

Erste unabhängige Prüfrunde (44 bestätigte Befunde) und Quelltext-Recherche zu Doichain Core v31.1.6 eingearbeitet.

- Benannte RPC-Parameter (Auszahlungen, RPC-Durchgriff mit Objekt).
- Namens-RPCs immer mit UTF-8, Namen NFC-normalisiert.
- Nach jedem Schreibaufruf Prüfung per `getmempoolentry`, abgelehnte Transaktionen werden per `abandontransaction` verworfen, neuer Endpunkt `POST /v1/wallet/abandon`.
- Nicht-ASCII-Schlüssel gelten als ungültig statt 500, Auffang-Handler mit JSON-Antwort und Protokollierung.
- Base58-Längenprüfung, Überlauf als 400.
- Fehlercodes −22, −20, −10, −1000, „out of range" und −25 mit Namenskonflikten richtig abgebildet.
- `GET /v1/names` liest bis zu 5.000 Einträge je Aufruf, filtert abgelaufene Namen und liefert `next_after`, `scanned`, `exhausted`.
- `/health` liefert 503 bei IBD, fehlenden Headern, Block älter als drei Stunden oder Fork-Verstoß.
- Wallet-Guthaben in `/v1/status` nur mit Schlüssel, `funding-address` legt keine Adressen mehr an.
- `GET /v1/address/{a}` ohne Historie (`with_count` optional), UTXOs mit `limit` und `offset`.
- OpenAPI mit Sicherheitsschema (`ApiKey`, `Bearer`), Fehlerschema und Beschreibungen.
- nginx: JSON-Fehlerseiten für 413, 429, 502, 504, Body-Grenzen je Location, Upload-Ratenzone, Schutz-Header, keine Versionsanzeige.
- install.sh lauffähig auf einem frischen Server (Benutzer, venv, Zertifikat, Umgebungsdatei, Einzahlungsadresse).

## 1.0.0 (2026-09-25)

Erste Fassung auf doi-btc-node: 39 Endpunkte für Status, Kette, Adressen, Namen, Proof of Existence, Wallet und Werkzeuge. Node vorher von v31.1.0 auf Doichain Core v31.1.6 gehoben.

# Changelog

Alle nennenswerten Änderungen der Doichain API. Datumsangaben im Format JJJJ-MM-TT.

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

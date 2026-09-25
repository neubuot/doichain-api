/* Verifile: Proof of Existence auf der Doichain. Datei wird nie hochgeladen, der SHA-256 entsteht im Browser. */
(function () {
  "use strict";

  const cfg = Object.assign({ apiBase: "https://doi-api.sendlabs.de", poeKey: "", explorer: "https://doi-explorer.le-space.de" }, window.VERIFILE_CONFIG || {});
  const API = cfg.apiBase.replace(/\/$/, "") + "/v1";
  const HASH_RE = /^[0-9a-f]{64}$/;

  const I18N = {
    de: {
      "nav.how": "So funktioniert es", "nav.verify": "Nachweis prüfen",
      "hero.eyebrow": "Proof of Existence auf der Doichain",
      "hero.title": "Beweisen Sie, dass eine Datei heute existiert.",
      "hero.lead": "Ihr Dokument bleibt auf Ihrem Rechner. Der Browser berechnet einen Fingerabdruck (SHA-256), Verifile verankert ihn in der Doichain. Ab dann kann jeder prüfen, dass genau diese Datei zu diesem Zeitpunkt existierte.",
      "drop.title": "Datei hierher ziehen oder klicken", "drop.sub": "Jede Dateiart, jede Größe. Es wird nichts hochgeladen.",
      "btn.copy": "Kopieren", "btn.download": "Nachweis herunterladen (JSON)", "btn.print": "Nachweis drucken", "btn.explorer": "Im Explorer ansehen",
      "create.note": "Notiz (optional, öffentlich sichtbar, höchstens 160 Zeichen)", "create.btn": "Jetzt in der Doichain verankern", "create.sendname": "Dateinamen öffentlich mit verankern",
      "faq.a1": "Nein. Der Hash wird im Browser berechnet, die Bibliothek dafür liefert Verifile selbst aus. An den Doichain-Server gehen nur die 64 Zeichen des Hashes, dazu Ihre Notiz und, nur wenn Sie das Häkchen setzen, der Dateiname. Alles drei ist danach öffentlich in der Doichain lesbar, aus dem Hash lässt sich die Datei nicht rekonstruieren.",
      "err.empty": "Die Datei ist leer, dafür gibt es keinen sinnvollen Nachweis.", "err.polling": "Die Bestätigung dauert ungewöhnlich lange. Seite später neu laden oder den Hash unten erneut prüfen.",
      "err.quota": "Tageskontingent erschöpft. Morgen wieder, oder mit eigenem API-Schlüssel über die Doichain API.",
      "how.title": "So funktioniert es",
      "how.s1t": "Fingerabdruck im Browser", "how.s1": "Aus Ihrer Datei berechnet der Browser einen SHA-256-Hash, 64 Zeichen, die nur zu genau dieser Datei passen. Ein einziges geändertes Bit ergibt einen anderen Hash.",
      "how.s2t": "Verankerung in der Doichain", "how.s2": "Der Hash wird als Name in der Doichain registriert. Der Block, der ihn enthält, trägt einen Zeitstempel, den niemand nachträglich ändern kann.",
      "how.s3t": "Nachweis für jeden", "how.s3": "Wer die Datei besitzt, berechnet den Hash erneut und findet den Eintrag samt Blockzeit. Dazu genügt diese Seite oder jeder Doichain-Explorer.",
      "verify.title": "Nachweis prüfen", "verify.lead": "Datei oben ablegen, oder einen bekannten Hash direkt eingeben.", "verify.btn": "Prüfen",
      "faq.q1": "Wird meine Datei hochgeladen?", "faq.a1": "Nein. Der Hash wird mit der Web-Crypto-Funktion Ihres Browsers berechnet. Nur die 64 Zeichen des Hashes werden an den Doichain-Server übertragen. Aus dem Hash lässt sich die Datei nicht rekonstruieren.",
      "faq.q2": "Was kostet das?", "faq.a2": "Für Sie nichts. Die Doichain-Gebühr und das Namenspfand trägt DOI Labs. Damit das so bleibt, gibt es ein Tageskontingent je Nutzer.",
      "faq.q3": "Wann ist der Nachweis gültig?", "faq.a3": "Nach der ersten Bestätigung, im Mittel etwa zehn Minuten nach dem Verankern. Die Seite zeigt den Stand automatisch an. Der Eintrag bleibt 36.000 Blöcke (rund 250 Tage) aktiv und danach dauerhaft in der Kettenhistorie sichtbar. Ein erneutes Verankern verlängert ihn.",
      "faq.q4": "Wie beweise ich das später einem Dritten?", "faq.a4": "Übergeben Sie die Datei und den heruntergeladenen Nachweis (JSON). Der Dritte berechnet den Hash der Datei, vergleicht ihn mit dem Nachweis und schaut den Eintrag im Doichain-Explorer nach. Beides geht ohne Verifile.",
      "faq.q5": "Was ist die Doichain?", "faq.a5": "Eine öffentliche Blockchain der Bitcoin-Familie, die per Merged Mining von Bitcoins Rechenleistung gesichert wird. Sie ist auf fälschungssichere Nachweise ausgelegt, personenbezogene Daten gehören nie auf die Kette.",
      "foot.by": "Ein Dienst der DOI Labs AG auf Basis der", "foot.privacy": "Keine Cookies, kein Tracking, keine Uploads.", "foot.imprint": "Impressum",
      "st.hashing": "Fingerabdruck wird berechnet …", "st.checking": "Doichain wird abgefragt …",
      "st.unknown": "Noch nicht verankert", "st.pending": "Wartet auf Bestätigung", "st.confirmed": "In der Doichain verankert", "st.expired": "Eintrag abgelaufen",
      "msg.unknown": "Für diese Datei gibt es noch keinen Eintrag. Mit einem Klick verankern Sie den Fingerabdruck jetzt.",
      "msg.pending": "Die Transaktion ist unterwegs. Sobald der nächste Block sie enthält (im Mittel zehn Minuten), wird der Nachweis endgültig. Diese Seite aktualisiert sich von selbst.",
      "msg.confirmed": "Diese Datei existierte nachweislich spätestens am <strong>{time}</strong> (Block {height}, {conf} Bestätigungen).",
      "msg.expired": "Der Eintrag vom {time} ist abgelaufen, bleibt aber in der Kettenhistorie beweisbar. Ein erneutes Verankern verlängert ihn um rund 250 Tage.",
      "kv.time": "Blockzeit (UTC)", "kv.height": "Block", "kv.txid": "Transaktion", "kv.conf": "Bestätigungen", "kv.name": "Name in der Doichain", "kv.note": "Notiz", "kv.created": "Verankert am",
      "quota.left": "Heute noch {ip} Nachweise für Sie möglich ({total} insgesamt).", "quota.unlimited": "",
      "err.hash": "Bitte einen gültigen SHA-256-Hash eingeben (64 Hex-Zeichen).", "err.net": "Der Doichain-Server ist gerade nicht erreichbar. Bitte später erneut versuchen.",
      "err.generic": "Das hat nicht geklappt: {msg}", "err.big": "Die Datei ist sehr groß, die Berechnung kann eine Weile dauern.",
      "err.toobig": "Ohne WebAssembly kann dieser Browser nur Dateien bis 1 GB verarbeiten. Bitte einen aktuellen Browser verwenden oder den Hash lokal berechnen und unten eingeben.",
      "btn.renew": "Erneut verankern (verlängern)", "copied": "Kopiert",
      "print.status.confirmed": "Bestätigt / confirmed", "print.status.pending": "Ausstehend / pending", "print.status.expired": "Abgelaufen / expired",
    },
    en: {
      "nav.how": "How it works", "nav.verify": "Verify a proof",
      "hero.eyebrow": "Proof of existence on the Doichain",
      "hero.title": "Prove that a file exists today.",
      "hero.lead": "Your document stays on your device. The browser computes a fingerprint (SHA-256) and Verifile anchors it in the Doichain. From then on anyone can verify that exactly this file existed at that moment.",
      "drop.title": "Drop a file here or click", "drop.sub": "Any file type, any size. Nothing is uploaded.",
      "btn.copy": "Copy", "btn.download": "Download proof (JSON)", "btn.print": "Print proof", "btn.explorer": "Open in explorer",
      "create.note": "Note (optional, publicly visible, up to 160 characters)", "create.btn": "Anchor it in the Doichain now", "create.sendname": "Also anchor the file name publicly",
      "faq.a1": "No. The hash is computed in your browser, Verifile ships the library itself. Only the 64 characters of the hash go to the Doichain server, plus your note and, only if you tick the box, the file name. All three become publicly readable in the Doichain, the file cannot be reconstructed from the hash.",
      "err.empty": "The file is empty, there is nothing meaningful to prove.", "err.polling": "Confirmation is taking unusually long. Reload the page later or verify the hash below again.",
      "err.quota": "Daily allowance exhausted. Try again tomorrow, or use your own API key with the Doichain API.",
      "how.title": "How it works",
      "how.s1t": "Fingerprint in your browser", "how.s1": "Your browser computes a SHA-256 hash of the file: 64 characters that match only this exact file. A single changed bit yields a different hash.",
      "how.s2t": "Anchored in the Doichain", "how.s2": "The hash is registered as a name in the Doichain. The block containing it carries a timestamp nobody can change afterwards.",
      "how.s3t": "Proof for everyone", "how.s3": "Anyone holding the file recomputes the hash and finds the entry with its block time, on this page or in any Doichain explorer.",
      "verify.title": "Verify a proof", "verify.lead": "Drop the file above, or enter a known hash directly.", "verify.btn": "Verify",
      "faq.q1": "Is my file uploaded?", "faq.a1": "No. The hash is computed with your browser's Web Crypto functions. Only the 64 characters of the hash are sent to the Doichain server. The file cannot be reconstructed from the hash.",
      "faq.q2": "What does it cost?", "faq.a2": "Nothing for you. DOI Labs covers the Doichain fee and the name deposit. To keep it that way there is a daily allowance per user.",
      "faq.q3": "When is the proof valid?", "faq.a3": "After the first confirmation, on average about ten minutes after anchoring. This page updates automatically. The entry stays active for 36,000 blocks (about 250 days) and remains visible in the chain history afterwards. Anchoring again renews it.",
      "faq.q4": "How do I prove it to a third party later?", "faq.a4": "Hand over the file and the downloaded proof (JSON). The third party computes the file's hash, compares it with the proof and looks up the entry in a Doichain explorer. Neither step needs Verifile.",
      "faq.q5": "What is the Doichain?", "faq.a5": "A public blockchain of the Bitcoin family, secured by Bitcoin's hash power through merged mining. It is built for tamper-proof proofs, personal data never belongs on chain.",
      "foot.by": "A service by DOI Labs AG built on the", "foot.privacy": "No cookies, no tracking, no uploads.", "foot.imprint": "Legal notice",
      "st.hashing": "Computing fingerprint …", "st.checking": "Querying the Doichain …",
      "st.unknown": "Not anchored yet", "st.pending": "Awaiting confirmation", "st.confirmed": "Anchored in the Doichain", "st.expired": "Entry expired",
      "msg.unknown": "There is no entry for this file yet. One click anchors the fingerprint now.",
      "msg.pending": "The transaction is on its way. Once the next block includes it (about ten minutes on average) the proof becomes final. This page refreshes by itself.",
      "msg.confirmed": "This file provably existed no later than <strong>{time}</strong> (block {height}, {conf} confirmations).",
      "msg.expired": "The entry from {time} has expired but remains provable in the chain history. Anchoring again renews it for about 250 days.",
      "kv.time": "Block time (UTC)", "kv.height": "Block", "kv.txid": "Transaction", "kv.conf": "Confirmations", "kv.name": "Name in the Doichain", "kv.note": "Note", "kv.created": "Anchored at",
      "quota.left": "{ip} more proofs available for you today ({total} overall).", "quota.unlimited": "",
      "err.hash": "Please enter a valid SHA-256 hash (64 hex characters).", "err.net": "The Doichain server is not reachable right now. Please try again later.",
      "err.generic": "That did not work: {msg}", "err.big": "The file is very large, computing may take a while.",
      "err.toobig": "Without WebAssembly this browser can only handle files up to 1 GB. Please use a current browser or compute the hash locally and enter it below.",
      "btn.renew": "Anchor again (renew)", "copied": "Copied",
      "print.status.confirmed": "Confirmed", "print.status.pending": "Pending", "print.status.expired": "Expired",
    },
  };
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* Speicher gesperrt */ } } };
  let lang = (store.get("verifile.lang") || (navigator.language || "de").slice(0, 2)) === "en" ? "en" : "de";
  const t = (key, vars) => {
    let s = (I18N[lang] && I18N[lang][key]) || I18N.de[key] || key;
    Object.entries(vars || {}).forEach(([k, v]) => { s = s.replace(new RegExp("\\{" + k + "\\}", "g"), String(v)); });
    return s;
  };
  function applyLang() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.innerHTML = t(el.getAttribute("data-i18n")); });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.getAttribute("data-i18n-title")); });
    $("langToggle").textContent = lang === "de" ? "EN" : "DE";
    if (state.hash) render();
  }

  const $ = (id) => document.getElementById(id);
  const state = { file: null, hash: null, info: null, busy: false, pollTimer: null, quota: null };

  // ---------------------------------------------------------------- Hashing (nur im Browser)
  async function sha256File(file, onProgress) {
    const chunk = 4 * 1024 * 1024;
    if (window.hashwasm && typeof window.hashwasm.createSHA256 === "function") {
      try {
        const hasher = await window.hashwasm.createSHA256();
        hasher.init();
        let offset = 0;
        while (offset < file.size) {
          const buf = await file.slice(offset, offset + chunk).arrayBuffer();
          hasher.update(new Uint8Array(buf));
          offset += buf.byteLength;
          onProgress(Math.min(1, offset / file.size));
          await new Promise((r) => setTimeout(r, 0));
        }
        return hasher.digest("hex");
      } catch (e) {
        // Bibliothek nicht nutzbar (etwa WebAssembly durch eine Richtlinie gesperrt): Rueckfall auf Web Crypto.
        console.warn("Verifile: hash-wasm nicht nutzbar, Rueckfall auf Web Crypto", e);
      }
    }
    // Rueckfall ohne Bibliothek: Web Crypto braucht die ganze Datei im Speicher.
    if (file.size > 1024 * 1024 * 1024) throw new Error(t("err.toobig"));
    const buf = await file.arrayBuffer();
    onProgress(0.9);
    const digest = await crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ---------------------------------------------------------------- API
  async function api(path, opts) {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    if (opts && opts.key) headers["X-API-Key"] = cfg.poeKey;
    let res;
    try {
      res = await fetch(API + path, { method: (opts && opts.method) || "GET", headers, body: opts && opts.body });
    } catch (e) {
      throw new Error(t("err.net"));
    }
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && data.error && data.error.message) || (res.status + " " + res.statusText);
      const err = new Error(msg); err.status = res.status; err.data = data; throw err;
    }
    return data;
  }
  const getStatus = (hash) => api("/poe/" + hash);
  const getQuota = () => cfg.poeKey ? api("/poe/quota", { key: true }).catch(() => null) : Promise.resolve(null);
  const createProof = (hash, filename, note) => api("/poe", { method: "POST", key: true, headers: { "content-type": "application/json" }, body: JSON.stringify({ hash, filename: filename || undefined, note: note || undefined }) });

  // ---------------------------------------------------------------- Darstellung
  const fmtSize = (n) => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " KB" : n < 1073741824 ? (n / 1048576).toFixed(1) + " MB" : (n / 1073741824).toFixed(2) + " GB";
  const fmtTime = (iso) => iso ? iso.replace("T", " ").replace("Z", " UTC") : "";
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function setBadge(cls, text) { const b = $("badge"); b.className = "badge " + cls; b.textContent = text; }
  function showError(msg) { const e = $("error"); e.textContent = msg; e.hidden = !msg; }

  function render() {
    const info = state.info;
    $("result").hidden = false;
    $("fileName").textContent = state.file ? state.file.name : t("kv.name");
    $("fileSize").textContent = state.file ? fmtSize(state.file.size) : "";
    $("hashOut").textContent = state.hash || "";
    const box = $("statusBox");
    $("createBox").hidden = true; $("doneBox").hidden = true;
    if (!info) return;
    const st = info.status;
    setBadge(st, t("st." + st));
    let html = "";
    if (st === "unknown") {
      html = "<p class='msg'>" + t("msg.unknown") + "</p>";
      $("createBox").hidden = false; $("createBtn").textContent = t("create.btn");
    } else {
      let v = info.value_json || null;
      if (!v && info.pending_ops && info.pending_ops[0] && info.pending_ops[0].value) v = safeJson(info.pending_ops[0].value);
      v = v || {};
      if (st === "pending") html = "<p class='msg'>" + t("msg.pending") + "</p>";
      if (st === "confirmed") html = "<p class='msg'>" + t("msg.confirmed", { time: esc(fmtTime(info.block_time_iso)), height: esc(info.height), conf: esc(info.confirmations) }) + "</p>";
      if (st === "expired") html = "<p class='msg'>" + t("msg.expired", { time: esc(fmtTime(info.block_time_iso)) }) + "</p>";
      const rows = [];
      if (info.block_time_iso) rows.push([t("kv.time"), esc(fmtTime(info.block_time_iso))]);
      if (info.height) rows.push([t("kv.height"), esc(info.height)]);
      if (info.confirmations != null && st !== "pending") rows.push([t("kv.conf"), esc(info.confirmations)]);
      const txid = info.txid || (info.pending_ops && info.pending_ops[0] && info.pending_ops[0].txid);
      if (txid) rows.push([t("kv.txid"), "<span class='mono'>" + esc(txid) + "</span>"]);
      rows.push([t("kv.name"), "<span class='mono'>" + esc(info.name) + "</span>"]);
      if (v.ts) rows.push([t("kv.created"), esc(fmtTime(v.ts))]);
      if (v.note) rows.push([t("kv.note"), esc(v.note)]);
      html += "<dl class='kv'>" + rows.map(([k, val]) => "<dt>" + k + "</dt><dd>" + val + "</dd>").join("") + "</dl>";
      $("doneBox").hidden = false;
      const link = info.explorer_tx || (txid ? cfg.explorer + "/tx/" + txid : cfg.explorer);
      $("explorerLink").href = link;
      if (st === "expired") { $("createBox").hidden = false; $("createBtn").textContent = t("btn.renew"); }
    }
    box.innerHTML = html;
    renderQuota();
  }

  function renderQuota() {
    const q = state.quota; const el = $("quota");
    if (!q || q.unlimited) { el.textContent = ""; return; }
    el.textContent = t("quota.left", { ip: q.remaining_ip, total: q.remaining_total });
    $("createBtn").disabled = q.remaining_ip <= 0 || q.remaining_total <= 0;
  }

  // ---------------------------------------------------------------- Ablauf
  async function handleFile(file) {
    if (state.busy || !file) return;
    if (file.size === 0) { $("result").hidden = false; showError(t("err.empty")); return; }
    stopPolling();
    state.busy = true; state.file = file; state.hash = null; state.info = null;
    showError("");
    const drop = $("drop"); drop.classList.add("busy");
    $("progress").hidden = false; $("bar").style.width = "0%"; $("progressText").textContent = "";
    render(); setBadge("busy", t("st.hashing"));
    if (file.size > 512 * 1024 * 1024) $("progressText").textContent = t("err.big");
    try {
      state.hash = await sha256File(file, (p) => { $("bar").style.width = Math.round(p * 100) + "%"; $("progressText").textContent = Math.round(p * 100) + " %"; });
      $("hashOut").textContent = state.hash;
      $("hashInput").value = state.hash;
      await refreshStatus();
    } catch (e) {
      showError(t("err.generic", { msg: e.message }));
    } finally {
      state.busy = false; drop.classList.remove("busy"); $("progress").hidden = true;
    }
  }

  async function checkHash(hash) {
    if (state.busy) return;
    stopPolling();
    state.file = null; state.hash = hash; state.info = null; showError("");
    render();
    await refreshStatus();
  }

  async function refreshStatus() {
    setBadge("busy", t("st.checking"));
    try {
      const [info, q] = await Promise.all([getStatus(state.hash), getQuota()]);
      state.info = info; state.quota = q;
      render();
      if (info.status === "pending") startPolling();
    } catch (e) {
      setBadge("unknown", "?"); showError(t("err.generic", { msg: e.message }));
    }
  }

  async function create() {
    if (!state.hash || state.busy) return;
    const btn = $("createBtn"); btn.disabled = true; showError(""); state.busy = true;
    const hashAtStart = state.hash;
    setBadge("busy", t("st.checking"));
    try {
      const filename = state.file && $("sendName").checked ? state.file.name : null;
      const res = await createProof(hashAtStart, filename, $("note").value.trim());
      if (state.hash !== hashAtStart) return;
      if (res.quota) state.quota = res.quota;
      state.info = Object.assign({}, state.info, { status: "pending", pending: true, pending_ops: [{ txid: res.txid, value: res.value }], txid: null, explorer_tx: res.explorer, name: res.name, value_json: safeJson(res.value) });
      $("note").value = "";
      render();
      startPolling();
    } catch (e) {
      if (state.hash !== hashAtStart) return;
      if (e.status === 409) { await refreshStatus(); return; }
      if (e.status === 429) { showError(t("err.quota")); state.quota = await getQuota(); render(); return; }
      showError(t("err.generic", { msg: e.message }));
      render();
    } finally { state.busy = false; btn.disabled = false; renderQuota(); }
  }
  const safeJson = (s) => { try { return JSON.parse(s); } catch (e) { return null; } };

  function startPolling() {
    stopPolling();
    let tries = 0;
    state.pollTimer = setInterval(async () => {
      tries++;
      try {
        const info = await getStatus(state.hash);
        if (info.status !== "pending") { state.info = info; render(); stopPolling(); }
      } catch (e) { /* naechster Versuch */ }
      if (tries > 720) { stopPolling(); showError(t("err.polling")); }
    }, 30000);
  }
  function stopPolling() { if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; } }

  // ---------------------------------------------------------------- Nachweis exportieren
  function proofDocument() {
    const info = state.info || {};
    return {
      verifile: "Proof of Existence on the Doichain",
      generated_at: new Date().toISOString(),
      file: state.file ? { name: state.file.name, size: state.file.size } : null,
      sha256: state.hash,
      status: info.status,
      name: info.name,
      txid: info.txid || null,
      block_height: info.height || null,
      block_hash: info.block_hash || null,
      block_time_utc: info.block_time_iso || null,
      value: info.value || null,
      explorer: info.explorer_tx || null,
      verify_api: cfg.apiBase.replace(/\/$/, "") + "/v1/poe/" + state.hash,
      how_to_verify: "Compute the SHA-256 of the file, compare with sha256, look up the entry via verify_api or the explorer. Block time is the proof of existence.",
    };
  }
  function download() {
    const blob = new Blob([JSON.stringify(proofDocument(), null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "verifile-proof-" + state.hash.slice(0, 12) + ".json"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function print() {
    const info = state.info || {};
    document.querySelectorAll(".print-sheet").forEach((n) => n.remove());
    const node = $("printTemplate").content.cloneNode(true);
    const set = (cls, val) => { node.querySelector("." + cls).textContent = val || "–"; };
    set("p-file", state.file ? state.file.name + " (" + fmtSize(state.file.size) + ")" : "");
    set("p-hash", state.hash);
    set("p-status", t("print.status." + info.status) || info.status);
    set("p-height", info.height);
    set("p-time", fmtTime(info.block_time_iso));
    set("p-txid", info.txid);
    set("p-name", info.name);
    set("p-explorer", info.explorer_tx);
    set("print-date", "Verifile · " + new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC");
    document.body.appendChild(node);
    window.print();
  }

  // ---------------------------------------------------------------- Ereignisse
  const drop = $("drop"), input = $("fileInput");
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { if (input.files[0]) handleFile(input.files[0]); input.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]; if (f) handleFile(f); });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => e.preventDefault());

  $("createBtn").addEventListener("click", create);
  $("downloadBtn").addEventListener("click", download);
  $("printBtn").addEventListener("click", print);
  $("copyHash").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(state.hash || ""); const b = $("copyHash"); b.classList.add("done"); b.title = t("copied"); setTimeout(() => { b.classList.remove("done"); b.title = t("btn.copy"); }, 1500); } catch (e) { /* ignorieren */ }
  });
  $("verifyForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const h = $("hashInput").value.trim().toLowerCase();
    if (!HASH_RE.test(h)) { showError(t("err.hash")); $("result").hidden = false; $("result").scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    checkHash(h); $("result").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("langToggle").addEventListener("click", () => { lang = lang === "de" ? "en" : "de"; store.set("verifile.lang", lang); applyLang(); });

  // Hash aus der Adresse (#<hash>) direkt pruefen, damit Nachweise verlinkbar sind.
  const fromUrl = (location.hash || "").replace("#", "").toLowerCase();
  applyLang();
  if (HASH_RE.test(fromUrl)) { $("hashInput").value = fromUrl; checkHash(fromUrl); }

  // Hinweis auf fehlende Konfiguration nur fuer Betreiber in der Konsole.
  if (!cfg.poeKey) console.warn("Verifile: kein poe-Schluessel in config.js, Nachweise koennen nur geprueft, nicht angelegt werden.");
  window.verifile = { handleFile, checkHash, state };
})();

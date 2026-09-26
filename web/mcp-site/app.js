/* Doichain MCP Landingpage: Sprache, Reiter, Kopieren, Live-Status. Alle Texte hier sind statisch. */
(function () {
  "use strict";

  var EN = {
    "nav.demo": "Examples", "nav.connect": "Connect", "nav.tools": "Tools", "nav.trust": "Security",
    "hero.eyebrow": "Model Context Protocol · Doichain",
    "hero.title": 'Turn your AI agent into a <span class="g">blockchain notary</span>.',
    "hero.lead": "One link is all it takes: Claude, ChatGPT, Cursor or any other MCP-capable agent anchors documents tamper-proof on the Doichain, checks proofs and reads names and blocks. No account, no key, no installation.",
    "hero.endpoint": "MCP address", "hero.cta1": "Connect in 30 seconds", "hero.cta2": "See the 13 tools",
    "copy": "Copy", "copied": "Copied",
    "status.loading": "Querying the Doichain …",
    "demo.title": "Just tell your agent", "demo.sub": "No code, no commands. The agent picks the right tool by itself.",
    "demo.q1": "Anchor the hash of offer-2026.pdf on the Doichain.",
    "demo.a1": "Done. I computed the SHA-256 locally and anchored it. Transaction <code>8067f0df…</code>, confirmed with the next block (usually under 10 minutes). Anyone can verify it at <code>verifile.it/#3f9a…c21e</code>.",
    "demo.q2": "Did this document already exist before October 1?",
    "demo.a2": "Yes. Exactly this file was anchored on 25 Sep 2026 at 23:21 UTC in block 433,335. Changing a single character would produce a different hash.",
    "demo.q3": "Are d/example or id/alice about to expire?",
    "demo.a3": "<strong>d/example</strong> stays active for about 228 more days (until around 12 May 2027). <strong>id/alice</strong> is not registered, the name is free.",
    "demo.q4": "How is the Doichain doing right now?",
    "demo.a4": "Synced at block 433,427, last block 7 minutes ago, 9 minutes average block interval, fork check fine, 15 connections.",
    "how.title": "How a proof comes about", "how.sub": "The document never leaves your computer. Only its digital fingerprint goes on chain.",
    "how.s1t": "Compute the fingerprint", "how.s1": "The agent computes the file's SHA-256 locally, for example with <code>sha256sum</code>. For short texts there is <code>hash_text</code>.",
    "how.s2t": "Anchor it on the Doichain", "how.s2": "<code>anchor_proof</code> writes the name <code>poe/&lt;hash&gt;</code> to the blockchain. With the next block the point in time is fixed tamper-proof.",
    "how.s3t": "Verify any time", "how.s3": 'Later anyone can show with <code>check_proof</code> or on <a href="https://verifile.it/">verifile.it</a> that exactly this document existed at that time.',
    "connect.title": "Connected in 30 seconds", "connect.sub": "Transport Streamable HTTP, no sign-in needed. Add the address and you are done.",
    "connect.other": "Other",
    "connect.cc": "Run once in your terminal, then the server is available in every session:",
    "connect.cc2": "Check with <code>claude mcp list</code>. With your own key and no daily quota, append <code>--header \"X-API-Key: …\"</code>.",
    "connect.ca1": "In Claude open <strong>Settings → Connectors</strong>.",
    "connect.ca2": "Choose <strong>Add custom connector</strong>.",
    "connect.ca3": "Name <strong>Doichain</strong>, paste the MCP address as URL and save.",
    "connect.ca4": "Enable \"Doichain\" in the chat's tools menu and start.",
    "connect.ca5": "Custom connectors are available on paid Claude plans. On Team and Enterprise your organization enables them.",
    "connect.gp1": "In ChatGPT open <strong>Settings → Apps and connectors → Advanced</strong> and turn on <strong>developer mode</strong>.",
    "connect.gp2": "Under connectors choose <strong>Create</strong>, name <strong>Doichain</strong>, paste the MCP address, authentication <strong>None</strong>.",
    "connect.gp3": "Select the connector in the chat.",
    "connect.gp4": "Menu names may differ depending on version and plan.",
    "connect.cu": "In <code>~/.cursor/mcp.json</code> (all projects) or <code>.cursor/mcp.json</code> (this project only):",
    "connect.vs": "In the project's <code>.vscode/mcp.json</code>, then use it in Copilot chat in agent mode:",
    "connect.ot": "Any client with Streamable HTTP works. The usual settings:",
    "connect.k1": "Address", "connect.k2": "Transport", "connect.k2b": "stateless, JSON responses", "connect.k3": "Sign-in",
    "connect.k3b": "none. Optionally your own key in the <code>X-API-Key</code> or <code>Authorization: Bearer</code> header",
    "connect.k4": "Protocol", "connect.k4b": "to",
    "tools.title": "13 tools for your agent", "tools.sub": "Reading is free. Only anchoring writes to the chain, free of charge within a daily quota.",
    "tools.write": "writes", "tools.read": "reads", "tools.local": "local",
    "tools.anchor": "Anchor the hash of a document as proof. Already anchored hashes are detected.",
    "tools.check": "Is this hash anchored, since when, in which block?",
    "tools.hash": "Compute the SHA-256 of a text to anchor statements or messages.",
    "tools.quota": "How many proofs are still free today?",
    "tools.lookup": "Value, owner and expiry of a name like <code>d/…</code> or <code>id/…</code>.",
    "tools.expiry": "Up to 25 names at once: active, expiring soon, expired or free, with an estimated date.",
    "tools.history": "Every registration and change of a name, newest first.",
    "tools.search": "List names by prefix, for example all <code>poe/</code> proofs.",
    "tools.status": "Block height, sync state, last block, fork check, block interval.",
    "tools.block": "A block by height or hash with time and transactions.",
    "tools.tx": "A transaction with outputs, addresses and name operations.",
    "tools.address": "Balance of an address, optionally with its latest transactions.",
    "tools.verify": "Check whether a message was really signed by the holder of an address.",
    "trust.title": "Security and privacy", "trust.sub": "Built for public operation with any agent.",
    "trust.c1t": "Hashes only, no files", "trust.c1": "The server accepts no documents. A SHA-256 cannot be turned back into the content.",
    "trust.c2t": "Free, with a quota", "trust.c2": "Anchoring is free: 10 proofs per day and internet connection, 200 in total. More with your own key.",
    "trust.c3t": "No wallet functions", "trust.c3": "The MCP server cannot send coins and never sees keys. It runs as a separate service without wallet access.",
    "trust.c4t": "Prompt injection protection", "trust.c4": "Values that strangers wrote to the chain are marked <code>_untrusted</code>. The agent treats them as data, never as instructions.",
    "trust.c5t": "Own node", "trust.c5": "Behind it runs a full Doichain Core node v31.1.6 with fork check, operated by DOI Labs.",
    "trust.c6t": "No cookies, no tracking", "trust.c6": "Neither this page nor the server sets cookies or stores content. The IP address only counts toward the daily quota.",
    "faq.title": "Frequently asked questions",
    "faq.q1": "What is MCP?", "faq.a1": "The Model Context Protocol is an open standard that lets AI applications connect tools and data. Once added, your agent can use the Doichain tools on its own.",
    "faq.q2": "What does it cost?", "faq.a2": "Nothing for users. Each anchoring costs a small fee in DOI that DOI Labs covers. That is why there is a daily quota per connection.",
    "faq.q3": "How long is a proof valid?", "faq.a3": "Forever. The name <code>poe/&lt;hash&gt;</code> stays active for about 36,000 blocks (roughly seven months), but the transaction with its timestamp remains in the blockchain for good. <code>check_proof</code> then reports <code>expired</code> and the proof stays valid.",
    "faq.q4": "Do I need DOI or a wallet?", "faq.a4": "No. The server anchors through the DOI Labs node. If you want to own names yourself, use the REST API with your own key or your own wallet.",
    "faq.q5": "What does the public see?", "faq.a5": "The hash, the point in time and an optional note or file name if you explicitly want that. No content, no personal data.",
    "faq.q6": "Is there a way without AI?", "faq.a6": '<a href="https://verifile.it/">Verifile</a> is the drag-and-drop web app, the <a href="/">Doichain REST API</a> the interface for your own programs.',
    "links.api": "The interface behind this server, with a playground", "links.docs": "Try every REST API endpoint",
    "links.verifile": "Proofs by drag and drop in the browser", "links.mcp": "Specification and clients of the protocol",
    "foot.imprint": "Legal notice", "foot.by": "A DOI Labs service built on the Doichain. No cookies, no tracking."
  };
  var DE = { "copy": "Kopieren", "copied": "Kopiert" };

  var lang = "de";
  var nodes = Array.prototype.slice.call(document.querySelectorAll("[data-i18n]"));
  nodes.forEach(function (el) { el.setAttribute("data-de", el.innerHTML); });
  var lastStatus = null;

  function t(key) { return (lang === "en" ? EN[key] : DE[key]) || EN[key] || key; }

  function store(k, v) { try { if (v === undefined) { return localStorage.getItem(k); } localStorage.setItem(k, v); } catch (e) { return null; } return null; }

  function applyLang(next) {
    lang = next;
    document.documentElement.lang = lang;
    nodes.forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      el.innerHTML = lang === "en" && EN[key] ? EN[key] : el.getAttribute("data-de");
    });
    document.getElementById("langBtn").textContent = lang === "en" ? "DE" : "EN";
    document.title = lang === "en" ? "Doichain MCP – Turn your AI agent into a blockchain notary" : "Doichain MCP – Ihr KI-Agent als Blockchain-Notar";
    renderStatus();
    store("doichain-mcp-lang", lang);
  }

  document.getElementById("langBtn").addEventListener("click", function () { applyLang(lang === "en" ? "de" : "en"); });

  // Reiter der Einbau-Anleitung
  var tabs = document.querySelectorAll("#connectTabs .tab");
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("click", function () {
      var target = tab.getAttribute("data-t");
      Array.prototype.forEach.call(tabs, function (x) { x.classList.toggle("on", x === tab); x.setAttribute("aria-selected", x === tab ? "true" : "false"); });
      Array.prototype.forEach.call(document.querySelectorAll(".pane"), function (p) { p.classList.toggle("on", p.getAttribute("data-p") === target); });
    });
  });

  // Kopieren
  function copyText(text, btn) {
    var done = function () {
      btn.textContent = t("copied"); btn.classList.add("done");
      setTimeout(function () { btn.textContent = t("copy"); btn.classList.remove("done"); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(text); done(); });
    } else { fallback(text); done(); }
  }
  function fallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch (e) { /* nichts */ }
    document.body.removeChild(ta);
  }
  Array.prototype.forEach.call(document.querySelectorAll(".copy"), function (btn) {
    btn.addEventListener("click", function () {
      var src = document.getElementById(btn.getAttribute("data-copy"));
      if (src) { copyText(src.textContent.trim(), btn); }
    });
  });

  // Live-Status der Node (gleiche Origin, REST-API)
  function fmt(n) { return typeof n === "number" ? n.toLocaleString(lang === "en" ? "en-US" : "de-DE") : String(n); }
  function renderStatus() {
    var dot = document.getElementById("dot"), text = document.getElementById("statusText");
    if (!lastStatus) { return; }
    if (lastStatus.error) {
      dot.className = "dot bad";
      text.textContent = lang === "en" ? "Doichain node not reachable right now" : "Doichain-Node gerade nicht erreichbar";
      return;
    }
    var s = lastStatus, chain = s.chain || {};
    var ok = chain.fork_check && chain.fork_check.ok && !chain.initial_block_download;
    var mins = chain.best_block_time ? Math.max(0, Math.round((Date.now() / 1000 - chain.best_block_time) / 60)) : null;
    dot.className = "dot " + (ok ? "ok" : "bad");
    if (lang === "en") {
      text.textContent = (ok ? "Live: " : "Check: ") + "block " + fmt(chain.blocks) + (mins !== null ? (mins < 1 ? ", last block just now" : ", last block " + mins + " min ago") : "") + (s.wallet && s.wallet.funded ? ", anchoring available" : "");
    } else {
      text.textContent = (ok ? "Live: " : "Prüfen: ") + "Block " + fmt(chain.blocks) + (mins !== null ? (mins < 1 ? ", letzter Block gerade eben" : ", letzter Block vor " + mins + " Min.") : "") + (s.wallet && s.wallet.funded ? ", Verankern verfügbar" : "");
    }
  }
  function loadStatus() {
    fetch("/v1/status", { headers: { "Accept": "application/json" } })
      .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); })
      .then(function (data) { lastStatus = data; renderStatus(); })
      .catch(function () { lastStatus = { error: true }; renderStatus(); });
  }

  var saved = store("doichain-mcp-lang");
  var initial = saved === "en" || saved === "de" ? saved : ((navigator.language || "de").toLowerCase().indexOf("de") === 0 ? "de" : "en");
  if (initial === "en") { applyLang("en"); }
  loadStatus();
  setInterval(loadStatus, 60000);
})();

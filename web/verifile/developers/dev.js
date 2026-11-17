/* Verifile, Seite für Entwickler: Sprachumschaltung, Kopierknöpfe und die Live-Abfrage. Die deutschen Texte
   stehen im HTML, die englischen hier. */
(function () {
  "use strict";

  const EN = {
    "nav.rules": "Limits and rules", "nav.app": "Open the app",
    "hero.eyebrow": "For developers and AI agents",
    "hero.title": "Build Verifile into your own software.",
    "hero.lead": "Everything the Verifile page does is also available as a REST API and as an MCP server for AI agents: anchor the fingerprint of a file in the Doichain and verify it later. No account, no sign-in.",
    "fact.1t": "No account needed", "fact.1": "Verifying is free. Anchoring works without a key within a daily allowance.",
    "fact.2t": "Your file stays with you", "fact.2": "Only the SHA-256 goes to the server, 64 characters. There are deliberately no file uploads here.",
    "fact.3t": "Two ways in", "fact.3": "The API for your own code, the MCP server for Claude, ChatGPT, Cursor and other agents.",
    "api.title": "REST API", "api.base": "Base URL",
    "api.lead": "Responses are JSON. Errors always come as <code>{\"error\": {\"type\": \"…\", \"code\": n, \"message\": \"…\"}}</code>, with German messages. Calls from the browser are allowed from any site (CORS).",
    "api.s1": "1. Compute the fingerprint", "api.s1p": "The SHA-256 is computed on your machine. A single changed bit gives a different value.",
    "api.s2": "2. Verify a proof",
    "api.st.h": "Meaning",
    "api.st.unknown": "There is no entry for this hash.",
    "api.st.pending": "The transaction is waiting for the next block, about ten minutes on average.",
    "api.st.confirmed": "Anchored. The document existed no later than the block time in <code>first_anchored</code>.",
    "api.st.expired": "The name has expired, the proof in <code>first_anchored</code> stays valid.",
    "api.s2p": "<code>first_anchored</code>, the first anchoring, is always what counts. The top-level fields describe the current state of the name and may come from a later registration after an expiry.",
    "try.btn": "Query live",
    "api.s3": "3. Create a proof",
    "api.s3p": "Response <code>201</code> with <code>txid</code>, <code>status: pending</code> and the remaining allowance in <code>quota</code>. <code>note</code> (up to 160 characters) and <code>filename</code> (up to 80 characters) are optional and public forever afterwards. If the hash is already anchored you get <code>409</code> and no second entry is created. The proof is final with the next block, after that the verify call returns block height and time.",
    "api.s4": "All calls", "api.t.call": "Call", "api.t.key": "Key", "api.t.what": "Purpose", "api.t.none": "none",
    "api.t.1": "Verify a proof", "api.t.2": "The same with <code>{\"hash\": \"…\"}</code> in the body",
    "api.t.3": "Create a proof, 3 per day and IP address", "api.t.4": "Remaining allowance without a key",
    "api.t.5": "Create a proof with your own key and its own allowance", "api.t.6": "Remaining allowance of the key",
    "api.t.7": "State of the chain. <code>wallet.public_poe_available</code> tells whether anchoring is possible right now",
    "api.openapi": "Machine-readable as OpenAPI:",
    "api.link": "Link to a proof with <code>https://verifile.it/#&lt;sha256&gt;</code>. The page then shows it ready to read, also when it was created through the API.",
    "mcp.title": "MCP server for AI agents", "mcp.addr": "Address",
    "mcp.lead": "The Model Context Protocol is the open standard AI applications use to connect external tools. Once added, the agent decides on its own when to use which tool. You simply tell it what you want. Transport Streamable HTTP, no sign-in.",
    "mcp.t.tool": "Tool", "mcp.t.what": "What for",
    "mcp.t.1": "Anchor the hash of a document. If it is already anchored, the existing proof is returned.",
    "mcp.t.2": "Whether the hash is anchored, since when and in which block.",
    "mcp.t.3": "SHA-256 of a short text, to anchor statements or messages. Files are hashed by the agent itself on your machine.",
    "mcp.t.4": "Remaining proofs for today.",
    "mcp.setup": "Setup", "mcp.claude.h": "Claude in the browser and as a desktop app",
    "mcp.claude": "Customize, then Connectors, then “Add custom connector”. Name “Verifile”, the address above as URL. Switch it on in the chat via the plus sign.",
    "mcp.chatgpt": "Turn on developer mode in the settings, then create an app with the address above, authentication “None”. Available on the Plus, Pro, Business, Enterprise and Education plans.",
    "mcp.say": "What you can say then",
    "mcp.say1": "“Anchor the hash of offer.pdf in the Doichain.”",
    "mcp.say2": "“Check whether this file is already anchored, and since when.”",
    "mcp.say3": "“Anchor this text as a proof: …”",
    "mcp.note": "An agent with file access (Claude Code, Cursor, VS Code) computes the hash itself. In a plain chat without file access, drop the file on <a href=\"../\">verifile.it</a> and give the agent the hash.",
    "rules.title": "Limits and rules",
    "rules.q1": "How many proofs are free?",
    "rules.a1": "Through the API without a key 3 per day and IP address, through the MCP server 10 per day and IP address. On top there is a daily limit for all users together. The day rolls over at 00:00 UTC. Users of hosted chat apps share the allowance of their provider's servers. Verifying is not limited, only throttled to 10 requests per second.",
    "rules.q2": "I need more. What then?",
    "rules.a2": "On request DOI Labs issues a key of your own with its own daily allowance. It is sent in the <code>X-API-Key</code> header, with the API to <code>POST /v1/poe</code>, with the MCP server as a header of the connector. The contact address is in the legal notice.",
    "rules.q3": "What becomes public?",
    "rules.a3": "The hash, the note and the file name, if you send them. All three are then permanently readable by anyone in the Doichain. So never put personal data or secrets into them. The file cannot be reconstructed from the hash.",
    "rules.q4": "What does a proof show, and what not?",
    "rules.a4": "It shows that a document with exactly this hash existed no later than the block time. It does not show who submitted it. The entries belong to the wallet of DOI Labs, which pays the fee.",
    "rules.q5": "How long is a proof valid?",
    "rules.a5": "The timestamp stays in the chain history permanently. The name of the entry is active for 36,000 blocks, around 250 days. After that someone could register it again. That is why the API always reports the first anchoring in <code>first_anchored</code>. An expired hash is only registered again when you explicitly ask for it.",
    "rules.q6": "What if nothing can be anchored right now?",
    "rules.a6": "When the operating balance falls below a reserve, anchoring pauses and the API answers with <code>503</code>. Verifying always works. A failed attempt does not cost allowance.",
    "rules.more": "Verifile is the proof-of-existence part of the <a href=\"https://doi-api.sendlabs.de/\" target=\"_blank\" rel=\"noopener\">Doichain API</a>. There you also get names, blocks, transactions and addresses, a playground at <a href=\"https://doi-api.sendlabs.de/docs\" target=\"_blank\" rel=\"noopener\">/docs</a> and the <a href=\"https://doi-api.sendlabs.de/mcp\" target=\"_blank\" rel=\"noopener\">Doichain MCP server</a> with all 13 tools.",
    "foot.by": "A service by DOI Labs AG built on the", "foot.privacy": "No cookies, no tracking, no uploads.", "foot.imprint": "Legal notice",
  };
  const UI = {
    de: { copy: "Kopieren", copied: "Kopiert", badHash: "Bitte einen SHA-256 mit 64 Hex-Zeichen eingeben.", net: "Der Server ist gerade nicht erreichbar.", loading: "Abfrage läuft …", title: "Verifile für Entwickler: API und MCP-Server" },
    en: { copy: "Copy", copied: "Copied", badHash: "Please enter a SHA-256 with 64 hex characters.", net: "The server is not reachable right now.", loading: "Querying …", title: "Verifile for developers: API and MCP server" },
  };

  const $ = (id) => document.getElementById(id);
  const store = { get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* Speicher gesperrt */ } } };
  let lang = (store.get("verifile.lang") || (navigator.language || "de").slice(0, 2)) === "en" ? "en" : "de";

  // Die deutschen Texte einmal aus dem HTML merken, damit der Schalter zurück wechseln kann.
  const DE = {};
  document.querySelectorAll("[data-i18n]").forEach((el) => { const key = el.getAttribute("data-i18n"); if (!(key in DE)) DE[key] = el.innerHTML; });

  function applyLang() {
    document.documentElement.lang = lang;
    document.title = UI[lang].title;
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      el.innerHTML = (lang === "en" && EN[key]) || DE[key];
    });
    document.querySelectorAll(".code .copy").forEach((btn) => { btn.textContent = UI[lang].copy; });
    $("langToggle").textContent = lang === "de" ? "EN" : "DE";
  }

  // Kopierknopf an jedem Codeblock, außer an der Ausgabe der Live-Abfrage.
  document.querySelectorAll("pre.code:not(.out)").forEach((pre) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy";
    btn.addEventListener("click", () => {
      const text = pre.querySelector("code").textContent;
      const done = () => { btn.classList.add("done"); btn.textContent = UI[lang].copied; setTimeout(() => { btn.classList.remove("done"); btn.textContent = UI[lang].copy; }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => {});
    });
    pre.appendChild(btn);
  });

  // Live-Abfrage. Unter verifile.it liegt die API unter /api, unter dem API-Host (dort /poe/developers/) direkt
  // an der Wurzel.
  const API = location.pathname.indexOf("/poe/") === 0 ? location.origin : location.origin + "/api";
  const out = $("tryOut");
  const show = (text, isError) => { out.hidden = false; out.classList.toggle("err", !!isError); out.querySelector("code").textContent = text; };
  $("tryForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const hash = $("tryHash").value.trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(hash)) { show(UI[lang].badHash, true); return; }
    show(UI[lang].loading, false);
    try {
      const res = await fetch(API + "/v1/poe/" + hash, { headers: { Accept: "application/json" } });
      show(JSON.stringify(await res.json(), null, 2), !res.ok);
    } catch (e) {
      show(UI[lang].net, true);
    }
  });

  $("langToggle").addEventListener("click", () => { lang = lang === "de" ? "en" : "de"; store.set("verifile.lang", lang); applyLang(); });
  applyLang();
})();

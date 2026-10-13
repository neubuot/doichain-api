"""Doichain Seal: Siegel fuer Software-Releases.

Eine GitHub Action verankert den SHA-256 eines Release-Artefakts als poe/<hash> in der Doichain. Dieses
Modul haelt dazu einen kleinen Index (SQLite im StateDirectory), der Repository, Tag, Commit und Datei zu
jedem Siegel kennt, damit Abzeichen und Pruefseite je Repository funktionieren. Der Index ist nur eine
Bequemlichkeit: Der Beweis ist der Name auf der Kette, dessen Wert Repository, Ref und Commit traegt.

Dazu die Darstellung: SVG-Abzeichen im Stil von shields.io und die HTML-Pruefseite mit Open-Graph-Karte.
Texte auf Englisch, weil Entwickler weltweit die Zielgruppe sind."""

import html
import os
import sqlite3
import threading
from datetime import datetime, timezone

from .config import settings

_lock = threading.Lock()

ACTION_URL = "https://github.com/neubuot/doichain-seal"


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(settings.state_dir, exist_ok=True)
    conn = sqlite3.connect(os.path.join(settings.state_dir, "seals.db"), timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "create table if not exists seals ("
        " id integer primary key autoincrement,"
        " hash text not null,"
        " repo text not null,"
        " repo_lc text not null,"
        " ref text not null,"
        " tag text not null,"
        " sha text not null,"
        " file text,"
        " size integer,"
        " txid text,"
        " run_id text,"
        " anchored_here integer not null default 1,"
        " created text not null)"
    )
    # repo: owner/name wie im OIDC-Token, repo_lc kleingeschrieben fuer die Suche, ref: refs/tags/v1.2.3,
    # tag: v1.2.3 (oder Branch), anchored_here 0: der Hash war schon vor diesem Lauf verankert.
    conn.execute("create index if not exists seals_repo on seals (repo_lc, id)")
    conn.execute("create index if not exists seals_hash on seals (hash)")
    return conn


def _now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add(*, hash_hex: str, repo: str, ref: str, tag: str, sha: str, file: str | None, size: int | None,
        txid: str | None, run_id: str, anchored_here: bool) -> dict:
    with _lock, _connect() as conn:
        # Derselbe Hash aus demselben Lauf (Wiederholung des Workflows) wird nicht doppelt eingetragen.
        row = conn.execute("select * from seals where hash = ? and repo_lc = ? and run_id = ?", (hash_hex, repo.lower(), run_id)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "insert into seals (hash, repo, repo_lc, ref, tag, sha, file, size, txid, run_id, anchored_here, created) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (hash_hex, repo, repo.lower(), ref, tag, sha, file, size, txid, run_id, 1 if anchored_here else 0, _now()),
        )
        row = conn.execute("select * from seals where id = last_insert_rowid()").fetchone()
        return dict(row)


def for_repo(repo: str, limit: int = 50) -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute("select * from seals where repo_lc = ? order by id desc limit ?", (repo.lower(), limit)).fetchall()
    return [dict(r) for r in rows]


def for_hash(hash_hex: str) -> list[dict]:
    with _lock, _connect() as conn:
        rows = conn.execute("select * from seals where hash = ? order by id asc", (hash_hex,)).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with _lock, _connect() as conn:
        total = conn.execute("select count(*) from seals").fetchone()[0]
        repos = conn.execute("select count(distinct repo_lc) from seals").fetchone()[0]
        today = conn.execute("select count(*) from seals where created >= ?", (datetime.now(tz=timezone.utc).date().isoformat(),)).fetchone()[0]
        latest = conn.execute("select repo, tag, hash, created from seals order by id desc limit 10").fetchall()
    return {"seals": int(total), "repositories": int(repos), "seals_today_utc": int(today), "latest": [dict(r) for r in latest]}


def public_row(row: dict) -> dict:
    """Indexzeile ohne interne Spalten, mit Links."""
    return {
        "hash": row["hash"],
        "repository": row["repo"],
        "ref": row["ref"],
        "tag": row["tag"],
        "sha": row["sha"],
        "file": row.get("file"),
        "size": row.get("size"),
        "txid": row.get("txid"),
        "run_url": f"https://github.com/{row['repo']}/actions/runs/{row['run_id']}" if row.get("run_id") else None,
        "anchored_by_this_run": bool(row.get("anchored_here")),
        "recorded_at": row["created"],
        "proof_url": f"{settings.public_url}/seal/{row['hash']}",
    }


# ---------------------------------------------------------------------------
# Abzeichen (SVG)
# ---------------------------------------------------------------------------

COLORS = {"green": "#1f9d55", "yellow": "#b7950b", "grey": "#6b7280"}

# Zeichenbreiten in Verdana 11 px, grob, damit das Abzeichen ohne Schriftmessung passt. Mit textLength
# erzwingt das SVG die berechnete Breite, so stimmt das Layout in jedem Betrachter.
_NARROW = set("iljtfI.,:;'| ")
_WIDE = set("mwMW@")


def _text_width(text: str) -> int:
    width = 0.0
    for c in text:
        if c in _NARROW:
            width += 3.8
        elif c in _WIDE:
            width += 10.0
        elif c.isupper() or c.isdigit():
            width += 7.3
        else:
            width += 6.4
    return int(round(width))


def badge_svg(label: str, message: str, color: str) -> str:
    """Flaches Abzeichen mit Doichain-Ring links, Text ist XML-sicher."""
    fill = COLORS.get(color, color)
    logo_w = 18
    pad = 6
    lw = _text_width(label)
    mw = _text_width(message)
    left = logo_w + pad + lw + pad
    right = pad + mw + pad
    total = left + right
    lbl = html.escape(label, quote=True)
    msg = html.escape(message, quote=True)
    lx = logo_w + pad + lw / 2
    mx = left + right / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{lbl}: {msg}">'
        f"<title>{lbl}: {msg}</title>"
        '<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{left}" height="20" fill="#101736"/><rect x="{left}" width="{right}" height="20" fill="{fill}"/><rect width="{total}" height="20" fill="url(#s)"/></g>'
        '<g transform="translate(5,3)"><circle cx="7" cy="7" r="5" fill="none" stroke="#60a5fa" stroke-width="2.2"/><circle cx="7" cy="7" r="1.8" fill="#34d399"/></g>'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{lx}" y="15" fill="#010101" fill-opacity=".3" textLength="{lw}">{lbl}</text><text x="{lx}" y="14" textLength="{lw}">{lbl}</text>'
        f'<text x="{mx}" y="15" fill="#010101" fill-opacity=".3" textLength="{mw}">{msg}</text><text x="{mx}" y="14" textLength="{mw}">{msg}</text>'
        "</g></svg>"
    )


def seal_svg(title: str, line: str, detail: str, color: str) -> str:
    """Grosses Siegel-Abzeichen (Karte mit Emblem) fuer READMEs und Release-Seiten.
    title: Tag oder kurzer Name, line: Status (sealed in block 436044, pending, no seal), detail: Datum oder Hinweis."""
    palette = {"green": "#34d399", "yellow": "#fbbf24", "grey": "#9aa5c4"}
    accent = palette.get(color, palette["grey"])
    t, l, d = (html.escape(x, quote=True) for x in (title, line, detail))
    # Breiten grob schaetzen (Verdana-Faktoren mit Schriftgroesse skaliert) und die Karte daran anpassen.
    tw = int(_text_width(title) * 15 / 11 * 1.08)
    lw = int(_text_width(line) * 10.5 / 11)
    dw = int(_text_width(detail) * 10.5 / 11)
    width = max(250, 76 + max(tw, lw + dw + 16, 108) + 44)
    h = 64
    x = width - 24
    if color == "green":
        mark = f'<circle cx="{x}" cy="32" r="9" fill="{accent}" opacity=".16"/><path d="M{x - 4.5} 32.5l3.2 3.2 6.2-6.6" fill="none" stroke="{accent}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
    elif color == "yellow":
        mark = f'<circle cx="{x}" cy="32" r="9" fill="{accent}" opacity=".16"/><circle cx="{x}" cy="32" r="5" fill="none" stroke="{accent}" stroke-width="2"/><path d="M{x} 29.5v3l2 1.5" fill="none" stroke="{accent}" stroke-width="1.8" stroke-linecap="round"/>'
    else:
        mark = f'<circle cx="{x}" cy="32" r="9" fill="{accent}" opacity=".16"/><path d="M{x - 4} 32h8" stroke="{accent}" stroke-width="2.2" stroke-linecap="round"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img" aria-label="Doichain seal: {t}, {l}, {d}">'
        f"<title>Doichain seal: {t}, {l}, {d}</title>"
        '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#172044"/><stop offset="1" stop-color="#0b1020"/></linearGradient>'
        f'<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#60a5fa"/><stop offset="1" stop-color="{accent}"/></linearGradient></defs>'
        f'<rect x=".5" y=".5" width="{width - 1}" height="{h - 1}" rx="14" fill="url(#bg)" stroke="#2b3a6b"/>'
        f'<rect x="1.5" y="1.5" width="{width - 3}" height="{h - 3}" rx="13" fill="none" stroke="#ffffff" stroke-opacity=".06"/>'
        '<g transform="translate(34,32)">'
        '<circle r="23" fill="#101736" stroke="#2b3a6b"/>'
        '<circle r="19.5" fill="none" stroke="url(#ring)" stroke-width="1.6" stroke-dasharray="2.2 2.4" opacity=".9"/>'
        '<circle r="11" fill="none" stroke="#60a5fa" stroke-width="4.5"/>'
        f'<circle r="3.6" fill="{accent}"/>'
        "</g>"
        '<g font-family="Verdana,Geneva,DejaVu Sans,sans-serif">'
        '<text x="68" y="20" font-size="9" letter-spacing="1.6" fill="#9aa5c4">DOICHAIN SEAL</text>'
        f'<text x="68" y="38" font-size="15" font-weight="bold" fill="#e8ecf8">{t}</text>'
        f'<text x="68" y="54" font-size="10.5" fill="{accent}">{l}</text>'
        f'<text x="{width - 44}" y="54" font-size="10.5" fill="#9aa5c4" text-anchor="end">{d}</text>'
        "</g>"
        f"{mark}"
        "</svg>"
    )


def seal_for_status(status: dict | None, tag: str | None = None) -> tuple[str, str, str, str, int]:
    """Titel, Statuszeile, Detail, Farbe und Cache-Dauer fuer das Siegel-Abzeichen."""
    if not status or status.get("status") == "unknown":
        return (tag or "not sealed", "no seal on chain" if tag else "no seal found", "doi-api.sendlabs.de/seal", "grey", 300)
    first = status.get("first_anchored") or {}
    height = first.get("height") or status.get("height")
    when = (first.get("block_time_iso") or status.get("block_time_iso") or "")[:10]
    hash_hex = status.get("hash") or ""
    title = tag or (hash_hex[:12] + "…" if hash_hex else "sealed file")
    if status.get("status") == "pending":
        return (title, "pending · next block", "anchoring", "yellow", 60)
    detail = when or "anchored"
    if status.get("status") == "expired":
        return (title, f"block {height} · name expired", detail, "green", 3600)
    return (title, f"sealed in block {height}", detail, "green", 3600)


def badge_for_status(status: dict | None, tag: str | None = None) -> tuple[str, str, int]:
    """Text, Farbe und Cache-Dauer (Sekunden) des Abzeichens aus einem PoE-Status."""
    if not status or status.get("status") == "unknown":
        return (f"{tag} · not sealed" if tag else "not sealed", "grey", 300)
    first = status.get("first_anchored") or {}
    height = first.get("height") or status.get("height")
    if status.get("status") == "pending":
        return (f"{tag} · pending" if tag else "pending", "yellow", 60)
    text = f"block {height}" if height else "sealed"
    if status.get("status") == "expired":
        text = f"block {height} (name expired)" if height else "sealed (name expired)"
    return (f"{tag} · {text}" if tag else text, "green", 3600)


# ---------------------------------------------------------------------------
# HTML-Pruefseite
# ---------------------------------------------------------------------------

def _e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


_PAGE_CSS = """
:root{--bg:#0b1020;--card:rgba(255,255,255,.06);--border:rgba(255,255,255,.12);--text:#e8ecf8;--muted:#9aa5c4;--accent:#34d399;--blue:#60a5fa;--warn:#fbbf24;--font:"Inter","Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,"Cascadia Code","SF Mono","JetBrains Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#1b2550 0%,var(--bg) 55%);color:var(--text);font-family:var(--font);line-height:1.5}
a{color:var(--blue)}main{max-width:900px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;color:var(--text);text-decoration:none;font-size:18px}
nav a{color:var(--muted);text-decoration:none;margin-left:16px;font-size:14px}nav a:hover{color:var(--text)}
h1{font-size:28px;margin:28px 0 6px;word-break:break-word}h1 a{color:var(--text);text-decoration:none}h2{font-size:18px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px 20px;margin:14px 0}
.status{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;font-weight:600;font-size:14px}
.ok{background:rgba(52,211,153,.15);color:var(--accent)}.pending{background:rgba(251,191,36,.15);color:var(--warn)}.none{background:rgba(154,165,196,.15);color:var(--muted)}
dl{display:grid;grid-template-columns:max-content 1fr;gap:8px 18px;margin:14px 0 0}dt{color:var(--muted)}dd{margin:0;word-break:break-all}
code,pre{font-family:var(--mono);font-size:13px}pre{background:rgba(0,0,0,.35);border:1px solid var(--border);border-radius:10px;padding:12px 14px;overflow:auto}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--border);vertical-align:top}th{color:var(--muted);font-weight:600}
.muted{color:var(--muted)}.small{font-size:13px}.badge{vertical-align:middle}
footer{margin-top:40px;color:var(--muted);font-size:13px}footer a{color:var(--muted)}
@media (max-width:600px){dl{grid-template-columns:1fr}dt{margin-top:6px}}
"""

_LOGO = '<svg viewBox="0 0 64 64" width="28" height="28" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#101736"/><circle cx="32" cy="32" r="13" fill="none" stroke="#60a5fa" stroke-width="6"/><circle cx="32" cy="32" r="4" fill="#34d399"/></svg>'

FAVICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#101736"/><circle cx="32" cy="32" r="13" fill="none" stroke="#60a5fa" stroke-width="6"/><circle cx="32" cy="32" r="4" fill="#34d399"/></svg>'


def _layout(*, title: str, description: str, canonical: str, body: str) -> str:
    base = settings.public_url
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_e(title)}</title><meta name="description" content="{_e(description)}">'
        f'<link rel="canonical" href="{_e(canonical)}">'
        '<meta property="og:type" content="website"><meta property="og:site_name" content="Doichain Seal">'
        f'<meta property="og:title" content="{_e(title)}"><meta property="og:description" content="{_e(description)}">'
        f'<meta property="og:url" content="{_e(canonical)}"><meta property="og:image" content="{base}/seal/og.png">'
        '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
        f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{_e(title)}">'
        f'<meta name="twitter:description" content="{_e(description)}"><meta name="twitter:image" content="{base}/seal/og.png">'
        '<link rel="icon" href="/seal/favicon.svg" type="image/svg+xml">'
        f"<style>{_PAGE_CSS}</style></head><body><main>"
        f'<header><a class="brand" href="/seal">{_LOGO}Doichain Seal</a>'
        f'<nav><a href="/seal#how">How it works</a><a href="{ACTION_URL}">GitHub Action</a><a href="https://verifile.it/">Verifile</a><a href="/docs">API</a></nav></header>'
        f"{body}"
        '<footer>Doichain Seal is a free service by <a href="https://doilabs.org/">DOI Labs</a>. The proof is the name <code>poe/&lt;sha256&gt;</code> on the public Doichain blockchain, '
        'this page only reads it. Anyone can verify a seal without this service, see <a href="/docs">the API</a> or <a href="https://verifile.it/">Verifile</a>.</footer>'
        "</main></body></html>"
    )


def _status_pill(status: dict | None) -> str:
    if not status or status.get("status") == "unknown":
        return '<span class="status none">Not sealed</span>'
    if status.get("status") == "pending":
        return '<span class="status pending">Pending: waiting for the next block</span>'
    first = status.get("first_anchored") or {}
    height = first.get("height") or status.get("height")
    note = " (name expired, the proof stays in the chain history)" if status.get("status") == "expired" else ""
    return f'<span class="status ok">Sealed in block {_e(height)}{note}</span>'


def _ts(value) -> str:
    return _e(value).replace("T", " ").replace("Z", " UTC") if value else ""


def origin_of(status: dict | None) -> dict | None:
    """Herkunft (gh-Feld) aus dem Kettenwert der ersten Verankerung, nicht aus dem Index."""
    if not status:
        return None
    first = status.get("first_anchored") or {}
    value = first.get("value_json") or status.get("value_json") or {}
    gh = value.get("gh") if isinstance(value, dict) else None
    return gh if isinstance(gh, dict) else None


def _value_of(status: dict) -> dict:
    first = status.get("first_anchored") or {}
    value = first.get("value_json") or status.get("value_json") or {}
    return value if isinstance(value, dict) else {}


def _verify_block(hash_hex: str, file: str | None) -> str:
    name = file or "<file>"
    return (
        '<h2 id="verify">Verify it yourself</h2><div class="card"><p>Download the release file, compute its SHA-256 and compare it with the hash above. '
        "Then read the name from the chain: with this API, with any Doichain node (<code>name_show</code>) or via the MCP server.</p>"
        f"<pre>sha256sum {_e(name)}\n# must print {_e(hash_hex)}\n\ncurl {settings.public_url}/v1/poe/{_e(hash_hex)}</pre>"
        f'<p class="small muted">Independent check: <a href="https://verifile.it/#{_e(hash_hex)}">Verifile</a> · '
        f'<a href="/v1/poe/{_e(hash_hex)}">JSON</a> · Merkle inclusion proof via <code>GET /v1/tx/&lt;txid&gt;/proof</code></p></div>'
    )


def _details(status: dict, row: dict | None) -> str:
    first = status.get("first_anchored") or {}
    gh = origin_of(status)
    txid = first.get("txid") or status.get("txid")
    value = _value_of(status)
    parts = ["<dl>"]
    parts.append(f'<dt>SHA-256</dt><dd><code>{_e(status.get("hash"))}</code></dd>')
    if not gh and row and status.get("status") == "pending":
        # Noch nicht im Block: Herkunft vorlaeufig aus dem Index zeigen, die Kette bestaetigt sie mit dem naechsten Block.
        gh = {"repo": row.get("repo"), "ref": row.get("tag"), "sha": (row.get("sha") or "")[:12], "_index": True}
    if gh:
        repo = gh.get("repo", "")
        parts.append(f'<dt>Repository</dt><dd><a href="https://github.com/{_e(repo)}">{_e(repo)}</a></dd>')
        if gh.get("ref"):
            parts.append(f'<dt>Release / ref</dt><dd><a href="https://github.com/{_e(repo)}/releases/tag/{_e(gh.get("ref"))}">{_e(gh.get("ref"))}</a></dd>')
        if gh.get("sha"):
            parts.append(f'<dt>Commit</dt><dd><a href="https://github.com/{_e(repo)}/commit/{_e(gh.get("sha"))}"><code>{_e(gh.get("sha"))}</code></a></dd>')
    if value.get("file"):
        size = f" · {row['size']} bytes" if row and row.get("size") else ""
        parts.append(f'<dt>File</dt><dd><code>{_e(value.get("file"))}</code>{_e(size)}</dd>')
    if status.get("status") != "pending":
        parts.append(f'<dt>Block</dt><dd>{_e(first.get("height") or status.get("height"))} · {_ts(first.get("block_time_iso") or status.get("block_time_iso"))}</dd>')
        parts.append(f'<dt>Confirmations</dt><dd>{_e(status.get("confirmations"))}</dd>')
    if txid:
        parts.append(f'<dt>Transaction</dt><dd><a href="{_e(first.get("explorer_tx") or status.get("explorer_tx"))}"><code>{_e(txid)}</code></a></dd>')
    parts.append(f'<dt>Name on chain</dt><dd><code>{_e(status.get("name"))}</code></dd>')
    if gh and gh.get("_index"):
        parts.append('<dt>Origin</dt><dd class="muted">Recorded by the seal service from a verified GitHub Actions OIDC token. The chain entry appears with the next block.</dd>')
    elif status.get("owned_by_this_wallet") and gh:
        parts.append("<dt>Origin</dt><dd>Written by the DOI Labs API after verifying a GitHub Actions OIDC token for this repository and commit.</dd>")
    elif gh:
        parts.append('<dt>Origin</dt><dd class="muted">The name carries GitHub data, but it was not written by this API. Treat the repository claim as unverified.</dd>')
    if row and row.get("run_id"):
        parts.append(f'<dt>Workflow run</dt><dd><a href="https://github.com/{_e(row.get("repo"))}/actions/runs/{_e(row.get("run_id"))}">{_e(row.get("run_id"))}</a></dd>')
    if status.get("reregistered_after_expiry"):
        parts.append('<dt>Note</dt><dd class="muted">The name was registered again after it expired. The seal time above is the first anchoring, the later registration may belong to someone else.</dd>')
    parts.append("</dl>")
    return "".join(parts)


def page_hash(hash_hex: str, status: dict, rows: list[dict]) -> str:
    gh = origin_of(status)
    row = rows[-1] if rows else None
    first = status.get("first_anchored") or {}
    if gh and gh.get("repo"):
        title = f"{gh.get('repo')} {gh.get('ref') or ''}".strip() + " · Doichain Seal"
        heading = _e(gh.get("repo")) + (" · " + _e(gh.get("ref")) if gh.get("ref") else "")
    else:
        title = f"Proof {hash_hex[:12]}… · Doichain Seal"
        heading = "Release proof"
    if status.get("status") in ("confirmed", "expired"):
        description = f"SHA-256 {hash_hex[:16]}… was anchored in Doichain block {first.get('height') or status.get('height')} on {(first.get('block_time_iso') or status.get('block_time_iso') or '')[:10]}."
    elif status.get("status") == "pending":
        description = f"SHA-256 {hash_hex[:16]}… is being anchored in the Doichain, waiting for the next block."
    else:
        description = f"No Doichain seal found for SHA-256 {hash_hex[:16]}…"
    canonical = f"{settings.public_url}/seal/{hash_hex}"
    body = f'<h1>{heading}</h1><p class="sub">Tamper-evident timestamp on the Doichain blockchain</p>'
    body += f'<div class="card">{_status_pill(status)}'
    if status.get("status") != "unknown":
        body += _details(status, row)
    else:
        body += (
            f'<dl><dt>SHA-256</dt><dd><code>{_e(hash_hex)}</code></dd></dl><p class="muted">Nothing with this hash has been anchored yet. '
            f'Seal a release with the <a href="{ACTION_URL}">Doichain Seal GitHub Action</a> or any file with <a href="https://verifile.it/">Verifile</a>.</p>'
        )
    body += "</div>"
    body += (
        f'<h2>Badges for this file</h2><div class="card"><p><img class="badge" src="/seal/{_e(hash_hex)}/seal.svg" alt="Doichain seal"></p>'
        f'<pre>[![Doichain Seal]({settings.public_url}/seal/{_e(hash_hex)}/seal.svg)]({settings.public_url}/seal/{_e(hash_hex)})</pre>'
        f'<p><img class="badge" src="/seal/{_e(hash_hex)}/badge.svg" alt="Doichain seal badge"> <span class="small muted">compact: <code>{settings.public_url}/seal/{_e(hash_hex)}/badge.svg</code></span></p></div>'
    )
    body += _verify_block(hash_hex, _value_of(status).get("file"))
    return _layout(title=title, description=description, canonical=canonical, body=body)


def page_repo(owner: str, name: str, rows: list[dict], statuses: dict[str, dict]) -> str:
    repo = f"{owner}/{name}"
    canonical = f"{settings.public_url}/seal/github/{owner}/{name}"
    latest = rows[0] if rows else None
    latest_status = statuses.get(latest["hash"]) if latest else None
    if latest and latest_status and latest_status.get("status") in ("confirmed", "expired"):
        first = latest_status.get("first_anchored") or {}
        description = f"Latest release {latest['tag']} of {repo} was sealed in Doichain block {first.get('height') or latest_status.get('height')}. {len(rows)} sealed file(s) in total."
    elif latest:
        description = f"Latest release {latest['tag']} of {repo} is being sealed in the Doichain."
    else:
        description = f"No Doichain seals yet for {repo}."
    title = f"{repo} · Doichain Seal"
    body = f'<h1><a href="https://github.com/{_e(repo)}">{_e(repo)}</a></h1><p class="sub">Release seals on the Doichain blockchain</p>'
    if latest:
        body += f'<div class="card"><div class="small muted">Latest seal · {_e(latest["tag"])}</div>{_status_pill(latest_status)}'
        if latest_status and latest_status.get("status") != "unknown":
            body += _details(latest_status, latest)
        body += f'<p class="small"><a href="/seal/{_e(latest["hash"])}">Open the proof page of this file</a></p></div>'
    else:
        body += (
            '<div class="card"><span class="status none">No seals yet</span><p class="muted">This repository has not sealed a release yet. '
            f'Add the <a href="{ACTION_URL}">Doichain Seal GitHub Action</a> to its release workflow.</p></div>'
        )
    body += (
        f'<h2>Badges for the README</h2><div class="card"><p><img class="badge" src="/seal/github/{_e(owner)}/{_e(name)}/seal.svg" alt="Doichain seal"></p>'
        f'<pre>[![Doichain Seal]({settings.public_url}/seal/github/{_e(owner)}/{_e(name)}/seal.svg)]({_e(canonical)})</pre>'
        f'<p><img class="badge" src="/seal/github/{_e(owner)}/{_e(name)}/badge.svg" alt="Doichain seal badge"> <span class="small muted">compact variant:</span></p>'
        f'<pre>[![Doichain Seal]({settings.public_url}/seal/github/{_e(owner)}/{_e(name)}/badge.svg)]({_e(canonical)})</pre></div>'
    )
    if rows:
        body += '<h2>All sealed files</h2><div class="card"><table><thead><tr><th>Release</th><th>File</th><th>Sealed</th><th>Status</th></tr></thead><tbody>'
        for r in rows:
            st = statuses.get(r["hash"])
            if st and st.get("status") in ("confirmed", "expired"):
                first = st.get("first_anchored") or {}
                cell = f'block {_e(first.get("height") or st.get("height"))}'
            elif st and st.get("status") == "pending":
                cell = "pending"
            elif st:
                cell = "not found on chain"
            else:
                cell = "open proof"
            body += (
                f'<tr><td><a href="https://github.com/{_e(repo)}/releases/tag/{_e(r["tag"])}">{_e(r["tag"])}</a><div class="small muted"><code>{_e(r["sha"][:12])}</code></div></td>'
                f'<td><code>{_e(r.get("file") or "")}</code></td><td class="small">{_ts(r["created"])}</td>'
                f'<td><a href="/seal/{_e(r["hash"])}">{cell}</a></td></tr>'
            )
        body += "</tbody></table></div>"
    if latest:
        body += _verify_block(latest["hash"], latest.get("file"))
    return _layout(title=title, description=description, canonical=canonical, body=body)


def page_index(stat: dict) -> str:
    canonical = f"{settings.public_url}/seal"
    base = settings.public_url
    body = (
        '<h1>Doichain Seal</h1><p class="sub">A free, tamper-evident timestamp for every software release. No account, no wallet, no secrets.</p>'
        f'<div class="card"><p>The <a href="{ACTION_URL}">Doichain Seal GitHub Action</a> computes the SHA-256 of your release files and anchors it in the '
        '<a href="https://doilabs.org/">Doichain</a> blockchain. The job proves its identity with a GitHub OIDC token, so the seal carries repository, tag and commit. '
        "Anyone can later check that a download is exactly the file you published, and since when it exists.</p>"
        f'<dl><dt>Seals</dt><dd>{stat["seals"]}</dd><dt>Repositories</dt><dd>{stat["repositories"]}</dd><dt>Today (UTC)</dt><dd>{stat["seals_today_utc"]}</dd></dl></div>'
        '<h2 id="how">Add it to a release workflow</h2>'
        "<pre>permissions:\n  contents: read\n  id-token: write   # lets the job prove its identity to the seal service\n\nsteps:\n  - uses: actions/checkout@v4\n  - run: ./build.sh            # produces dist/*\n"
        "  - uses: neubuot/doichain-seal@v1\n    with:\n      files: dist/*</pre>"
        "<p>Then put the seal into your README (the large seal, or the compact badge with <code>badge.svg</code>):</p>"
        '<p><img class="badge" src="/seal/github/neubuot/doichain-seal/seal.svg" alt="Doichain seal"> <img class="badge" src="/seal/github/neubuot/doichain-seal/badge.svg" alt="Doichain seal badge"></p>'
        f"<pre>[![Doichain Seal]({base}/seal/github/OWNER/REPO/seal.svg)]({base}/seal/github/OWNER/REPO)</pre>"
        '<h2>What the seal proves</h2><div class="card"><ul>'
        "<li><strong>Existence and time:</strong> a file with exactly this SHA-256 existed no later than the block time.</li>"
        "<li><strong>Origin:</strong> the name value carries repository, ref and commit from the verified GitHub OIDC token and is written by the DOI Labs wallet.</li>"
        "<li><strong>Independence:</strong> the proof lives on a public blockchain. It can be checked with any Doichain node, with this API, with Verifile or via the MCP server. If this service disappears, the proof stays.</li>"
        f'</ul><p class="small muted">Limits: {settings.seal_per_repo_day} seals per repository and day, {settings.seal_per_day} per day for everyone. Names expire after 36,000 blocks (about 250 days), the timestamp stays in the chain history forever. '
        "Repository, tag, commit and file name are public on the chain.</p></div>"
    )
    if stat.get("latest"):
        body += '<h2>Latest seals</h2><div class="card"><table><thead><tr><th>Repository</th><th>Release</th><th>When</th></tr></thead><tbody>'
        for r in stat["latest"]:
            owner, _, name = r["repo"].partition("/")
            body += f'<tr><td><a href="/seal/github/{_e(owner)}/{_e(name)}">{_e(r["repo"])}</a></td><td><a href="/seal/{_e(r["hash"])}">{_e(r["tag"])}</a></td><td class="small">{_ts(r["created"])}</td></tr>'
        body += "</tbody></table></div>"
    return _layout(
        title="Doichain Seal: timestamps for software releases",
        description="Free tamper-evident timestamps for software releases on the Doichain blockchain, via a GitHub Action with OIDC. No account, no wallet.",
        canonical=canonical,
        body=body,
    )

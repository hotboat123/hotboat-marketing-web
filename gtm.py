"""Google Tag Manager: snippet oficial + marcadores en HTML.

Variable de entorno: GTM_CONTAINER_ID (formato GTM-XXXXXXX).
Mismo patrón que meta_pixel.py — id desde env, inyectado al servir la
página, dos marcadores porque GTM necesita un bloque en <head> y otro
justo después de <body> (noscript).
"""
from __future__ import annotations

import os
import re

_HEAD_PLACEHOLDER = "<!--GTM_HEAD-->"
_BODY_PLACEHOLDER = "<!--GTM_BODY-->"

_ID_RE = re.compile(r"^GTM-[A-Z0-9]+$")


def sanitize_container_id(raw: str | None) -> str:
    if not raw:
        return ""
    candidate = raw.strip().upper()
    return candidate if _ID_RE.match(candidate) else ""


def get_gtm_container_id() -> str:
    return sanitize_container_id(os.environ.get("GTM_CONTAINER_ID", ""))


def is_gtm_enabled() -> bool:
    return bool(get_gtm_container_id())


def gtm_head_html(container_id: str) -> str:
    """Snippet oficial de Google para <head>."""
    if not container_id:
        return ""
    return f"""<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','{container_id}');</script>
<!-- End Google Tag Manager -->"""


def gtm_body_html(container_id: str) -> str:
    """Snippet oficial de Google para justo después de <body> (noscript)."""
    if not container_id:
        return ""
    return f"""<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={container_id}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->"""


def apply_gtm_placeholders(html: str, container_id: str) -> str:
    cid = sanitize_container_id(container_id) if container_id else ""
    if _HEAD_PLACEHOLDER in html:
        html = html.replace(_HEAD_PLACEHOLDER, gtm_head_html(cid), 1)
    if _BODY_PLACEHOLDER in html:
        html = html.replace(_BODY_PLACEHOLDER, gtm_body_html(cid), 1)
    return html


def gtm_startup_message() -> str:
    cid = get_gtm_container_id()
    if cid:
        return f"[GTM] enabled (GTM_CONTAINER_ID={cid})"
    return "[GTM] disabled - set GTM_CONTAINER_ID (formato GTM-XXXXXXX)"

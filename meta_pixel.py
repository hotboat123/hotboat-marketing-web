"""Meta (Facebook) Pixel: snippet oficial + marcador en HTML.

Variables de entorno: META_PIXEL_ID, FACEBOOK_PIXEL_ID o FB_PIXEL_ID (solo dígitos).
"""
from __future__ import annotations

import os

_PLACEHOLDER = "<!--META_PIXEL_HEAD-->"


def sanitize_pixel_id(raw: str | None) -> str:
    if not raw:
        return ""
    return "".join(c for c in raw.strip() if c.isdigit())


def get_meta_pixel_id() -> str:
    for key in ("META_PIXEL_ID", "FACEBOOK_PIXEL_ID", "FB_PIXEL_ID"):
        v = os.environ.get(key, "")
        if v:
            return sanitize_pixel_id(v)
    return ""


def is_meta_pixel_enabled() -> bool:
    return bool(get_meta_pixel_id())


def meta_pixel_head_html(pixel_id: str) -> str:
    """Base code + PageView + noscript (plantilla oficial Meta)."""
    if not pixel_id:
        return ""
    return f"""<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '{pixel_id}');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->"""


def apply_meta_pixel_placeholder(html: str, pixel_id: str) -> str:
    pid = sanitize_pixel_id(pixel_id) if pixel_id else ""
    snippet = meta_pixel_head_html(pid)
    if _PLACEHOLDER in html:
        return html.replace(_PLACEHOLDER, snippet, 1)
    return html


def meta_pixel_startup_message() -> str:
    pid = get_meta_pixel_id()
    if pid:
        return f"[Meta Pixel] enabled (META_PIXEL_ID ok, {len(pid)} digits)"
    return "[Meta Pixel] disabled - set META_PIXEL_ID (or FACEBOOK_PIXEL_ID / FB_PIXEL_ID)"

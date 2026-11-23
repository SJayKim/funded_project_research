"""Read-only, bounded comparison of IRIS public detail routes."""
from collections import Counter
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import re
from time import monotonic
from urllib.parse import urlencode

from funded_project_research.adapters.base import http_get, http_post
from funded_project_research.adapters.iris import LIST_URL, VIEW_URL, parse_detail, parse_rows
from funded_project_research.status import utc_now

TARGETS = ("019508", "024799")
TIMEOUT = 10


class Identity(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = {}

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            attrs = dict(attrs)
            key = attrs.get("name") or attrs.get("id")
            if key in ("ancmId", "bsnsYy", "sorgnBsnsCd", "bsnsAncmSn"):
                self.inputs[key] = attrs.get("value")


def request(label, fetch, *args):
    started = monotonic()
    attempted = utc_now()
    try:
        text = fetch(*args, timeout=TIMEOUT).decode("utf-8")
    except Exception as error:
        reason = getattr(error, "reason", None)
        print(json.dumps({"route": label, "attempted": attempted, "elapsed": round(monotonic() - started, 2),
                          "error": type(error).__name__, "reason_type": type(reason).__name__,
                          "http_status": getattr(error, "code", None)}), flush=True)
        return ""
    print(json.dumps({"route": label, "attempted": attempted, "elapsed": round(monotonic() - started, 2),
                      "chars": len(text)}), flush=True)
    return text


def compact(text):
    return re.sub(r"\s+", "", unescape(text))


def detail_result(label, html, notice_id, expected):
    if not html:
        return
    parser = Identity()
    parser.feed(html)
    info = parse_detail(html)
    body = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>", "", html, flags=re.I | re.S)
    visible = compact(re.sub(r"<[^>]+>", " ", body))
    title = compact(expected.get("ancmTl", ""))
    fields = ("ancmId", "bsnsYy", "sorgnBsnsCd", "bsnsAncmSn")
    print(json.dumps({"result": label, "identity_match": parser.inputs.get("ancmId") == notice_id,
                      "fields_checked": sorted(parser.inputs),
                      "identity_fields_match": all(parser.inputs.get(field) == expected.get(field)
                                                   for field in fields) if title else None,
                      "title_match": title in visible if title else None,
                      "notice_number": bool(info["ancmNo"]), "attachment_marker": bool(info["attachments"]),
                      "detail_hash": sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()[:12]
                      if any(info.values()) else None}), flush=True)


rows = []
for page in (1, 2):
    html = request(f"list_post_{page}", http_post, LIST_URL, {"pageIndex": page})
    parsed = parse_rows(html)
    rows.extend(parsed)
    print(json.dumps({"list_page": page, "rows": len(parsed),
                      "target_ids": [row["ancmId"] for row in parsed if row["ancmId"] in TARGETS]}), flush=True)
counts = Counter(tuple(row[key] for key in ("ancmId", "bsnsYy", "sorgnBsnsCd", "bsnsAncmSn")) for row in rows)
print(json.dumps({"listing_rows": len(rows), "unique_detail_requests": len(counts),
                  "targets_with_exact_duplicates": sorted({key[0] for key, count in counts.items()
                                                           if count > 1 and key[0] in TARGETS})}), flush=True)
for notice_id in TARGETS:
    expected = next((row for row in rows if row["ancmId"] == notice_id), {})
    label = "get_id_" + notice_id
    html = request(label, http_get, f"{VIEW_URL}?{urlencode({'ancmId': notice_id})}")
    detail_result(label, html, notice_id, expected)
    if expected:
        fields = {key: expected[key] for key in ("ancmId", "bsnsYy", "sorgnBsnsCd", "bsnsAncmSn")}
        fields["bsnsYyDetail"] = expected["bsnsYy"]
        label = "get_full_" + notice_id
        html = request(label, http_get, f"{VIEW_URL}?{urlencode(fields)}")
        detail_result(label, html, notice_id, expected)
        if notice_id == TARGETS[0]:
            label = "post_full_" + notice_id
            html = request(label, http_post, VIEW_URL, fields)
            detail_result(label, html, notice_id, expected)

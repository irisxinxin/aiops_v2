#!/usr/bin/env python3
import re
import hashlib


_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]+")


def _slug(s: str) -> str:
    s = _NON_ALNUM.sub("-", s.strip()).strip("-")
    s = re.sub(r"-+", "-", s)
    return s.lower()


def build_incident_key_from_alert(alert: dict) -> str:
    """从 alert 生成规范化 incident_key: service_category_severity_region[_title|name][_group]"""
    metadata = alert.get("metadata", {})

    parts = [
        _slug(str(alert.get("service", ""))),
        _slug(str(alert.get("category", ""))),
        _slug(str(alert.get("severity", ""))),
        _slug(str(alert.get("region", ""))),
    ]

    title = str(alert.get("title", "") or metadata.get("title", "")).strip()
    fallback_name = str(
        alert.get("name", "")
        or alert.get("alertname", "")
        or metadata.get("name", "")
        or metadata.get("alertname", "")
    ).strip()
    group_id = str(metadata.get("group_id", "") or alert.get("group_id", "") or alert.get("group", "")).strip()

    if title:
        parts.append(_slug(title))
    elif fallback_name:
        parts.append(_slug(fallback_name))
    if group_id:
        parts.append(_slug(group_id))

    base = "_".join([p for p in parts if p])
    return base or ""


def sop_id_from_incident_key(incident_key: str) -> str:
    """根据 incident_key 生成 6 位数字 sop_id（非后缀，纯数字）。"""
    import zlib
    base = (incident_key or "").strip().lower()
    code = zlib.crc32(base.encode("utf-8")) % 1_000_000
    return f"{code:06d}"


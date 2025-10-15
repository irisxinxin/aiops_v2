#!/usr/bin/env python3
import re
import hashlib


_NON_ALNUM = re.compile(r"[^a-zA-Z0-9]+")


def _slug(s: str) -> str:
    s = _NON_ALNUM.sub("-", s.strip()).strip("-")
    s = re.sub(r"-+", "-", s)
    return s.lower()


def build_incident_key_from_alert(alert: dict) -> str:
    """从 alert 生成规范化 incident_key: service_category_severity_region[_title|name][_group]
    再追加 6 位 sha1 后缀，保证简短唯一。
    """
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
    if not base:
        return hashlib.sha1(b"empty").hexdigest()[:6]
    suffix6 = hashlib.sha1(base.encode()).hexdigest()[:6]
    return f"{base}-{suffix6}"


def sop_id_from_incident_key(incident_key: str) -> str:
    """根据 incident_key 生成短 sop_id：slug(incident_key) + '-' + 6位sha1。"""
    base = _slug(incident_key)
    suffix6 = hashlib.sha1(base.encode()).hexdigest()[:6]
    return f"{base}-{suffix6}" if base else suffix6


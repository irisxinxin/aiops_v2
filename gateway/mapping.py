#!/usr/bin/env python3
import hashlib


def build_incident_key_from_alert(alert: dict) -> str:
    """从 alert 生成标准 incident_key: service_category_severity_region[_name][_group]
    并追加 10位 sha1 后缀避免冲突。
    """
    # 从metadata中获取更准确的信息
    metadata = alert.get("metadata", {})
    
    service = str(alert.get("service", "")).strip()
    category = str(alert.get("category", "")).strip()
    severity = str(alert.get("severity", "")).strip()
    region = str(alert.get("region", "")).strip()
    
    # 优先从metadata获取alertname
    name = str(metadata.get("alertname", "") or alert.get("alertname", "") or alert.get("name", "")).strip()
    group_id = str(metadata.get("group_id", "") or alert.get("group_id", "") or alert.get("group", "")).strip()

    base = "_".join([x for x in [service, category, severity, region] if x])
    if name:
        base += f"_{name}"
    if group_id:
        base += f"_{group_id}"

    # hash 后缀（稳定且避免冲突）
    suffix = hashlib.sha1(base.encode()).hexdigest()[:10]
    return f"{base}-{suffix}" if base else suffix


def sop_id_from_incident_key(incident_key: str) -> str:
    """将 incident_key 规范化为 sop_id（同名即可）。"""
    return incident_key.replace(" ", "-").replace("/", "-").lower()


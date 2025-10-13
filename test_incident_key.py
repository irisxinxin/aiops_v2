#!/usr/bin/env python3
import json
import sys
sys.path.append('.')

from gateway.mapping import build_incident_key_from_alert, sop_id_from_incident_key

# 加载sdn5_cpu.json
with open('sdn5_cpu.json', 'r') as f:
    alert_data = json.load(f)

print("=== 测试 incident_key 生成 ===")
print(f"原始alert数据: {json.dumps(alert_data, indent=2, ensure_ascii=False)}")

# 生成incident_key
incident_key = build_incident_key_from_alert(alert_data)
print(f"\n生成的incident_key: {incident_key}")

# 生成sop_id
sop_id = sop_id_from_incident_key(incident_key)
print(f"生成的sop_id: {sop_id}")

# 测试payload处理
payload = {
    "text": "分析这个CPU告警并提供解决方案",
    "alert": alert_data
}

from gateway.app import resolve_sop_id
resolved_sop_id = resolve_sop_id(payload)
print(f"resolve_sop_id结果: {resolved_sop_id}")
print(f"payload中的incident_key: {payload.get('incident_key', 'N/A')}")

print("\n=== 测试完成 ===")

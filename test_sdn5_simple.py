#!/usr/bin/env python3

import json
import requests
from datetime import datetime

def test_sdn5_simple():
    """测试简化的sdn5告警"""
    
    # 简化的告警数据
    alert_data = {
        "status": "firing",
        "service": "sdn5",
        "category": "cpu",
        "severity": "critical",
        "title": "sdn5 container CPU usage is too high"
    }
    
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "分析这个CPU告警",
        "alert": alert_data
    }
    
    print(f"🚀 简化sdn5测试: {datetime.now()}")
    print(f"📊 告警: {alert_data.get('title')}")
    print("-" * 50)
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        
        print(f"📡 状态码: {response.status_code}")
        print(f"📏 响应大小: {len(response.text)} 字节")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 响应结构:")
            print(f"   - 成功: {result.get('success', False)}")
            print(f"   - 时延: {result.get('elapsed_time', 0)} 秒")
            print(f"   - 历史加载: {result.get('conversation_loaded', False)}")
            
            if result.get('success'):
                print(f"\n🔍 根因分析: {result.get('root_cause', '无')}")
                
                actions = result.get('suggested_actions', [])
                if actions:
                    print(f"\n💡 建议措施:")
                    for i, action in enumerate(actions[:3], 1):
                        print(f"   {i}. {action}")
                
                print(f"\n🎯 置信度: {result.get('confidence', '无')}")
            else:
                print(f"\n❌ 错误: {result.get('error', '未知')}")
            
            # 保存响应
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sdn5_simple_response_{timestamp}.json"
            with open(filename, 'w') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n💾 响应已保存到: {filename}")
        else:
            print(f"❌ 错误响应: {response.text}")
            
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    test_sdn5_simple()

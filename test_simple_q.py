#!/usr/bin/env python3

import json
import requests
from datetime import datetime

def test_simple_q():
    """测试简单的Q CLI响应"""
    
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "hello, 你好吗？"
    }
    
    print(f"🚀 简单测试: {datetime.now()}")
    print("-" * 40)
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        print(f"📡 状态码: {response.status_code}")
        print(f"📏 响应大小: {len(response.text)} 字节")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 响应内容:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 错误响应: {response.text}")
            
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    test_simple_q()

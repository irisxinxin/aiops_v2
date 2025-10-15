#!/usr/bin/env python3
import json
import requests
import time

def test_simple_request():
    """测试简单请求"""
    
    request_data = {
        "text": "hello world",
        "alert": {"service": "test", "category": "test"}
    }
    
    print("🚀 发送简单测试请求...")
    start_time = time.time()
    
    try:
        response = requests.post(
            "http://127.0.0.1:8081/ask_json",
            json=request_data,
            timeout=20
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️  请求耗时: {elapsed:.2f}秒")
        print(f"📊 状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 请求成功")
            print(f"📝 结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        else:
            print(f"❌ 请求失败: {response.text}")
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"⏰ 请求超时 ({elapsed:.2f}秒)")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 请求异常 ({elapsed:.2f}秒): {e}")

if __name__ == "__main__":
    test_simple_request()

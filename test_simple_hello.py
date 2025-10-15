#!/usr/bin/env python3
import json
import requests
import time

def test_simple_hello():
    """测试简单的hello请求"""
    
    request_data = {
        "text": "Hello, please respond with just 'OK'",
        "alert": {"service": "test", "category": "test"}
    }
    
    print("🚀 发送简单hello请求...")
    start_time = time.time()
    
    try:
        response = requests.post(
            "http://127.0.0.1:8081/ask_json",
            json=request_data,
            timeout=120
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️  请求耗时: {elapsed:.2f}秒")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 请求成功")
            print(f"📝 SOP ID: {result.get('sop_id', 'N/A')}")
            print(f"📈 分析状态: {'✅' if result.get('ok', False) else '❌'}")
            
            output = result.get('output', '')
            if output:
                print("\n📋 输出内容:")
                print("=" * 40)
                print(output)
                print("=" * 40)
            
            # 保存响应
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            with open(f"hello_response_{timestamp}.json", "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"💾 响应已保存到: hello_response_{timestamp}.json")
            
        else:
            print(f"❌ 请求失败: HTTP {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"⏰ 请求超时 ({elapsed:.2f}秒)")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 请求异常 ({elapsed:.2f}秒): {e}")

if __name__ == "__main__":
    test_simple_hello()

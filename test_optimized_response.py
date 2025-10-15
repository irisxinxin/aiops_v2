#!/usr/bin/env python3
import json
import requests
import time

def test_optimized_response():
    print("=== 测试优化后的Response格式 ===")
    print(f"时间: {time.strftime('%H:%M:%S')}")
    
    # 检查连接池
    health = requests.get('http://localhost:8081/healthz').json()
    pool = health['connection_pool']
    print(f"连接池: {pool['active_connections']}/{pool['max_connections']}")
    
    payload = {
        "text": "测试优化后的response格式，分析sdn5 CPU告警",
        "alert": {
            "status": "firing",
            "service": "sdn5",
            "category": "cpu", 
            "severity": "critical",
            "title": "sdn5 container CPU usage is too high",
            "metadata": {
                "current_value": 0.92,
                "threshold_value": 0.9,
                "pod": "omada-device-gateway-6.0.0189-59ccd49449-98n7b"
            }
        }
    }
    
    print(f"\n📝 发送的Prompt: {payload['text']}")
    
    start_time = time.time()
    
    try:
        response = requests.post(
            'http://localhost:8081/ask',
            json=payload,
            stream=True,
            timeout=45
        )
        
        if response.status_code != 200:
            print(f"❌ HTTP错误: {response.status_code}")
            return
        
        print(f"\n📥 优化后的Response:")
        print("-" * 60)
        
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])
                    
                    if data.get('type') == 'analysis_complete':
                        print("✅ 分析完成!")
                        analysis = data.get('analysis', {})
                        summary = data.get('summary', '')
                        
                        print(f"\n📊 结构化分析结果:")
                        if 'root_cause' in analysis:
                            print(f"根因: {analysis['root_cause'][:150]}...")
                        
                        print(f"\n📋 格式化摘要:")
                        print(summary)
                        break
                        
                    elif data.get('type') == 'analysis_partial':
                        summary = data.get('summary', '')
                        if summary and summary != "正在分析中...":
                            print(f"部分结果: {summary[:200]}...")
                        
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        print(f"\n⏱️ 总用时: {end_time - start_time:.2f}秒")
        
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时")
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    test_optimized_response()

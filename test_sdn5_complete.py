#!/usr/bin/env python3
"""
测试 sdn5_cpu.json 完整分析功能
"""
import requests
import json
import time
from pathlib import Path

BASE_URL = "http://127.0.0.1:8081"

def load_sdn5_alert():
    """加载 sdn5_cpu.json 告警数据"""
    alert_file = Path("sdn5_cpu.json")
    if not alert_file.exists():
        raise FileNotFoundError("sdn5_cpu.json not found")
    
    with open(alert_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_sdn5_analysis():
    """测试 sdn5 CPU 告警分析"""
    print("=== 测试 sdn5 CPU 告警分析 ===\n")
    
    # 加载告警数据
    alert_data = load_sdn5_alert()
    print(f"告警数据加载成功: {alert_data.get('title', 'Unknown')}")
    
    # 测试请求
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data,
        "sop_id": "sdn5_cpu_analysis"
    }
    
    print(f"发送分析请求...")
    start_time = time.time()
    
    try:
        response = requests.post(f"{BASE_URL}/ask_json", json=payload, timeout=60)
        elapsed = time.time() - start_time
        
        print(f"响应状态码: {response.status_code}")
        print(f"响应时间: {elapsed:.2f}s")
        
        if response.status_code == 200:
            result = response.json()
            print(f"分析状态: {result.get('status')}")
            print(f"对话加载: {result.get('conversation_loaded')}")
            print(f"服务器耗时: {result.get('elapsed_time')}s")
            
            print("\n=== 完整响应 ===")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
            # 检查分析结果
            if result.get('status') == 'success':
                analysis = result.get('analysis', {})
                if analysis:
                    print(f"\n=== 分析结果摘要 ===")
                    print(f"根因: {analysis.get('root_cause', 'N/A')}")
                    print(f"建议措施: {analysis.get('suggested_actions', [])}")
                    print(f"置信度: {analysis.get('confidence', 'N/A')}")
            
        else:
            print(f"请求失败: {response.text}")
            
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        print(f"请求超时 ({elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"请求异常 ({elapsed:.2f}s): {e}")

def test_conversation_persistence():
    """测试对话持久化"""
    print("\n=== 测试对话持久化 ===\n")
    
    # 第一次请求
    payload1 = {
        "text": "你好，我是测试用户",
        "sop_id": "persistence_test"
    }
    
    print("发送第一次请求...")
    response1 = requests.post(f"{BASE_URL}/ask_json", json=payload1, timeout=30)
    if response1.status_code == 200:
        result1 = response1.json()
        print(f"第一次对话加载: {result1.get('conversation_loaded')}")
    
    # 第二次请求 - 应该加载历史对话
    payload2 = {
        "text": "还记得我刚才说的话吗？",
        "sop_id": "persistence_test"
    }
    
    print("发送第二次请求...")
    response2 = requests.post(f"{BASE_URL}/ask_json", json=payload2, timeout=30)
    if response2.status_code == 200:
        result2 = response2.json()
        print(f"第二次对话加载: {result2.get('conversation_loaded')}")
        print(f"应该为 True，表示成功加载了历史对话")

if __name__ == "__main__":
    try:
        # 检查服务健康状态
        health_response = requests.get(f"{BASE_URL}/healthz", timeout=5)
        if health_response.status_code != 200:
            print("服务不健康，退出测试")
            exit(1)
        
        print("服务健康检查通过\n")
        
        # 执行测试
        test_sdn5_analysis()
        test_conversation_persistence()
        
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到服务，请确保服务已启动")
    except Exception as e:
        print(f"测试出错: {e}")

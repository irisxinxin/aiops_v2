#!/usr/bin/env python3
"""
测试斜杠命令功能
"""
import requests
import json
import time

BASE_URL = "http://127.0.0.1:8081"

def test_slash_commands():
    """测试斜杠命令"""
    print("=== 测试斜杠命令功能 ===\n")
    
    # 测试 /usage 命令
    print("1. 测试 /usage 命令")
    response = requests.post(f"{BASE_URL}/ask", json={
        "text": "/usage",
        "sop_id": "test_session"
    })
    
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    print()
    
    # 测试 /save 命令
    print("2. 测试 /save 命令")
    response = requests.post(f"{BASE_URL}/ask", json={
        "text": "/save test_conv.json",
        "sop_id": "test_session"
    })
    
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    print()
    
    # 测试 /load 命令
    print("3. 测试 /load 命令")
    response = requests.post(f"{BASE_URL}/ask", json={
        "text": "/load test_conv.json",
        "sop_id": "test_session"
    })
    
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    print()

def test_normal_analysis():
    """测试正常分析功能"""
    print("=== 测试正常分析功能 ===\n")
    
    response = requests.post(f"{BASE_URL}/ask", json={
        "text": "你好，请简单介绍一下你的功能",
        "sop_id": "test_session"
    })
    
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"成功: {result.get('success')}")
        print(f"耗时: {result.get('elapsed_time')}s")
        print(f"对话已加载: {result.get('conversation_loaded')}")
        if result.get('analysis_summary'):
            print(f"分析摘要: {result.get('analysis_summary')[:200]}...")
    else:
        print(f"错误: {response.text}")

def test_healthz():
    """测试健康检查"""
    print("=== 测试健康检查 ===\n")
    
    response = requests.get(f"{BASE_URL}/healthz")
    print(f"状态码: {response.status_code}")
    result = response.json()
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    print()

if __name__ == "__main__":
    try:
        test_healthz()
        test_slash_commands()
        test_normal_analysis()
    except requests.exceptions.ConnectionError:
        print("错误: 无法连接到服务，请确保服务已启动")
    except Exception as e:
        print(f"测试出错: {e}")

#!/usr/bin/env python3

import json
import time
import requests
from datetime import datetime

def test_sdn5_final():
    """最终测试sdn5_cpu.json，等待Q CLI完全初始化"""
    
    # 加载测试数据
    with open('sdn5_cpu.json', 'r') as f:
        alert_data = json.load(f)
    
    # 准备请求
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print(f"🚀 最终测试: {datetime.now()}")
    print(f"📊 告警: {alert_data.get('title', 'Unknown')}")
    print(f"🔧 服务: {alert_data.get('service', 'Unknown')}")
    print("⏳ 等待Q CLI完全初始化（可能需要1-2分钟）...")
    print("-" * 60)
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=180  # 3分钟超时，给Q CLI足够时间初始化
        )
        
        end_time = time.time()
        latency = end_time - start_time
        
        print(f"⏱️  总时延: {latency:.2f} 秒")
        print(f"📡 状态码: {response.status_code}")
        print(f"📏 响应大小: {len(response.text)} 字节")
        print("-" * 60)
        
        if response.status_code == 200:
            try:
                result = response.json()
                print("✅ JSON响应结构:")
                print(f"   - 成功: {result.get('success', False)}")
                print(f"   - 历史加载: {result.get('conversation_loaded', False)}")
                print(f"   - 服务器时延: {result.get('elapsed_time', 0)} 秒")
                
                # 显示状态消息
                status_messages = result.get('status_messages', [])
                if status_messages:
                    print(f"\n📋 状态消息 ({len(status_messages)} 条):")
                    for i, msg in enumerate(status_messages, 1):
                        print(f"   {i}. {msg}")
                
                # 显示分析结果
                if result.get('success'):
                    print(f"\n🔍 根因分析:")
                    root_cause = result.get('root_cause', '无')
                    print(f"   {root_cause}")
                    
                    suggested_actions = result.get('suggested_actions', [])
                    if suggested_actions:
                        print(f"\n💡 建议措施 ({len(suggested_actions)} 条):")
                        for i, action in enumerate(suggested_actions, 1):
                            print(f"   {i}. {action}")
                    
                    confidence = result.get('confidence', '无')
                    print(f"\n🎯 置信度: {confidence}")
                    
                    analysis_summary = result.get('analysis_summary', '')
                    if analysis_summary:
                        print(f"\n📋 分析摘要:")
                        # 显示前300字符
                        summary_preview = analysis_summary[:300]
                        if len(analysis_summary) > 300:
                            summary_preview += "..."
                        print(f"   {summary_preview}")
                    
                    tool_calls = result.get('tool_calls', [])
                    if tool_calls:
                        print(f"\n🔧 工具调用 ({len(tool_calls)} 次):")
                        for i, call in enumerate(tool_calls, 1):
                            tool_name = call.get('tool', 'Unknown') if isinstance(call, dict) else str(call)
                            print(f"   {i}. {tool_name}")
                    
                    evidence = result.get('evidence', [])
                    if evidence:
                        print(f"\n📄 证据 ({len(evidence)} 项):")
                        for i, ev in enumerate(evidence[:3], 1):  # 只显示前3项
                            evidence_text = ev if isinstance(ev, str) else str(ev)
                            print(f"   {i}. {evidence_text[:100]}...")
                else:
                    print(f"\n❌ 分析失败:")
                    print(f"   错误: {result.get('error', '未知错误')}")
                    
                    raw_content = result.get('raw_content', '')
                    if raw_content:
                        print(f"   原始内容片段: {raw_content[:200]}...")
                
                # 保存完整响应
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"sdn5_final_response_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"\n💾 完整响应已保存到: {filename}")
                
                return True, latency, result
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析错误: {e}")
                print(f"原始响应: {response.text[:500]}...")
                return False, latency, response.text
        else:
            print(f"❌ 请求失败: {response.text}")
            return False, latency, response.text
            
    except requests.exceptions.Timeout:
        print("⏰ 请求超时 (3分钟)")
        return False, 180, "Timeout"
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False, 0, str(e)

if __name__ == "__main__":
    success, latency, response = test_sdn5_final()
    
    print("\n" + "=" * 60)
    print(f"📊 最终测试总结:")
    print(f"   成功: {'✅' if success else '❌'}")
    print(f"   总时延: {latency:.2f}s")
    print(f"   时间: {datetime.now()}")
    
    # 简单的性能评估
    if success and latency < 30:
        print(f"   性能: 🟢 优秀 (< 30s)")
    elif success and latency < 60:
        print(f"   性能: 🟡 良好 (< 60s)")
    elif success:
        print(f"   性能: 🟠 可接受 (> 60s)")
    else:
        print(f"   性能: 🔴 失败")
    
    print("=" * 60)

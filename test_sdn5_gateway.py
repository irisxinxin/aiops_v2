#!/usr/bin/env python3
import json
import time
import requests
from pathlib import Path

def test_sdn5_analysis():
    """测试sdn5_cpu告警分析"""
    
    # 加载测试数据
    sdn5_path = Path("sdn5_cpu.json")
    if not sdn5_path.exists():
        print("❌ sdn5_cpu.json not found")
        return
    
    with open(sdn5_path) as f:
        alert_data = json.load(f)
    
    # 构建请求
    request_data = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print("🚀 开始测试sdn5_cpu告警分析...")
    print(f"📊 告警数据: {alert_data.get('service', 'unknown')}/{alert_data.get('category', 'unknown')}")
    
    start_time = time.time()
    
    try:
        # 发送请求，设置30秒超时
        response = requests.post(
            "http://127.0.0.1:8081/ask_json",
            json=request_data,
            timeout=120  # 增加到120秒
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️  请求耗时: {elapsed:.2f}秒")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 请求成功")
            print(f"📝 SOP ID: {result.get('sop_id', 'N/A')}")
            print(f"🔄 历史对话加载: {'✅' if result.get('loaded', False) else '❌'}")
            print(f"💾 对话保存: {'✅' if result.get('saved', False) else '❌'}")
            print(f"📈 分析状态: {'✅' if result.get('ok', False) else '❌'}")
            
            # 显示输出内容
            output = result.get('output', '')
            if output:
                print("\n📋 分析结果:")
                print("=" * 60)
                print(output[:2000])  # 显示前2000字符
                if len(output) > 2000:
                    print(f"\n... (还有 {len(output) - 2000} 字符)")
                print("=" * 60)
            
            # 显示事件
            events = result.get('events', [])
            if events:
                print(f"\n🔧 工具调用事件: {len(events)}个")
                for i, event in enumerate(events[:3]):  # 显示前3个事件
                    print(f"  {i+1}. {event.get('type', 'unknown')}: {str(event)[:100]}...")
            
            # 保存完整响应
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_file = f"sdn5_response_{timestamp}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n💾 完整响应已保存到: {output_file}")
            
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
    test_sdn5_analysis()

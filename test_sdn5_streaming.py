#!/usr/bin/env python3

import json
import time
import requests
from datetime import datetime

def test_sdn5_streaming():
    """Test sdn5_cpu.json with streaming response handling"""
    
    # Load test data
    with open('sdn5_cpu.json', 'r') as f:
        alert_data = json.load(f)
    
    # Prepare request
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print(f"🚀 Starting streaming test at {datetime.now()}")
    print(f"📊 Alert: {alert_data.get('title', 'Unknown')}")
    print(f"🔧 Service: {alert_data.get('service', 'Unknown')}")
    print("-" * 60)
    
    start_time = time.time()
    final_result = None
    status_messages = []
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=300
        )
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code} - {response.text}")
            return False, 0, None
        
        print("📡 Receiving streaming response...")
        
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    
                    if data.get('type') == 'status':
                        status_msg = data.get('message', '')
                        status_messages.append(status_msg)
                        print(f"📋 Status: {status_msg}")
                    
                    elif data.get('type') == 'analysis_result':
                        final_result = data
                        print("✅ Final analysis result received!")
                        break
                        
                    elif data.get('type') == 'analysis_partial':
                        print(f"🔄 Partial: {data.get('summary', '')}")
                        
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        latency = end_time - start_time
        
        print(f"\n⏱️  Total Latency: {latency:.2f} seconds")
        print(f"📏 Status Messages: {len(status_messages)}")
        print("-" * 60)
        
        if final_result:
            print("✅ Final Analysis Result:")
            
            # Display structured result
            if 'root_cause' in final_result:
                print(f"\n🔍 Root Cause:")
                print(f"   {final_result['root_cause']}")
            
            if 'suggested_actions' in final_result:
                print(f"\n💡 Suggested Actions:")
                actions = final_result['suggested_actions']
                if isinstance(actions, list):
                    for i, action in enumerate(actions, 1):
                        print(f"   {i}. {action}")
                else:
                    print(f"   {actions}")
            
            if 'confidence' in final_result:
                print(f"\n🎯 Confidence: {final_result['confidence']}")
            
            if 'analysis_summary' in final_result:
                print(f"\n📋 Summary:")
                print(f"   {final_result['analysis_summary']}")
            
            # Check for conversation history loading
            history_loaded = any("加载对话上下文" in msg for msg in status_messages)
            print(f"\n💬 History Loading: {'✅ Success' if history_loaded else '❌ Not detected'}")
            
            # Save results
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = f"sdn5_streaming_result_{timestamp}.json"
            
            with open(result_file, 'w') as f:
                json.dump({
                    'final_result': final_result,
                    'status_messages': status_messages,
                    'latency': latency,
                    'timestamp': timestamp
                }, f, indent=2, ensure_ascii=False)
            
            print(f"\n💾 Results saved to: {result_file}")
            return True, latency, final_result
        else:
            print("❌ No final result received")
            return False, latency, None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0, str(e)

if __name__ == "__main__":
    success, latency, result = test_sdn5_streaming()
    
    print("\n" + "=" * 60)
    print(f"📊 Test Summary:")
    print(f"   Success: {'✅' if success else '❌'}")
    print(f"   Latency: {latency:.2f}s")
    print(f"   Timestamp: {datetime.now()}")
    print("=" * 60)

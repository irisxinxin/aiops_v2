#!/usr/bin/env python3

import json
import time
import requests
from datetime import datetime

def test_sdn5_cpu():
    """Test sdn5_cpu.json with performance measurement"""
    
    # Load test data
    with open('sdn5_cpu.json', 'r') as f:
        alert_data = json.load(f)
    
    # Prepare request
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print(f"🚀 Starting test at {datetime.now()}")
    print(f"📊 Alert: {alert_data.get('title', 'Unknown')}")
    print(f"🔧 Service: {alert_data.get('service', 'Unknown')}")
    print("-" * 60)
    
    # Measure request time
    start_time = time.time()
    
    try:
        response = requests.post(
            url, 
            json=payload, 
            headers={"Content-Type": "application/json"},
            timeout=300  # 5 minutes timeout
        )
        
        end_time = time.time()
        latency = end_time - start_time
        
        print(f"⏱️  Total Latency: {latency:.2f} seconds")
        print(f"📡 Status Code: {response.status_code}")
        print(f"📏 Response Size: {len(response.text)} bytes")
        print("-" * 60)
        
        if response.status_code == 200:
            try:
                result = response.json()
                print("✅ Response JSON Structure:")
                print(f"   - Keys: {list(result.keys())}")
                
                # Display key parts of response
                if 'root_cause' in result:
                    print(f"\n🔍 Root Cause:")
                    print(f"   {result['root_cause']}")
                
                if 'suggested_actions' in result:
                    print(f"\n💡 Suggested Actions:")
                    for i, action in enumerate(result['suggested_actions'], 1):
                        print(f"   {i}. {action}")
                
                if 'confidence' in result:
                    print(f"\n🎯 Confidence: {result['confidence']}")
                
                if 'analysis_summary' in result:
                    print(f"\n📋 Summary:")
                    print(f"   {result['analysis_summary']}")
                
                # Save full response for inspection
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"sdn5_test_response_{timestamp}.json"
                with open(filename, 'w') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"\n💾 Full response saved to: {filename}")
                
                return True, latency, result
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"Raw response: {response.text[:500]}...")
                return False, latency, response.text
        else:
            print(f"❌ Request failed: {response.text}")
            return False, latency, response.text
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 5 minutes")
        return False, 300, "Timeout"
    except Exception as e:
        print(f"❌ Error: {e}")
        return False, 0, str(e)

if __name__ == "__main__":
    success, latency, response = test_sdn5_cpu()
    
    print("\n" + "=" * 60)
    print(f"📊 Test Summary:")
    print(f"   Success: {'✅' if success else '❌'}")
    print(f"   Latency: {latency:.2f}s")
    print(f"   Timestamp: {datetime.now()}")
    print("=" * 60)

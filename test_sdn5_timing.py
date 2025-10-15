#!/usr/bin/env python3

import json
import time
import requests
from datetime import datetime

def test_sdn5_cpu():
    # Load test data
    with open('sdn5_cpu.json', 'r') as f:
        alert_data = json.load(f)
    
    # Prepare request
    url = "http://127.0.0.1:8081/ask"
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print(f"=== SDN5 CPU Alert Analysis Test ===")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"URL: {url}")
    print(f"Alert: {alert_data['title']}")
    print(f"Current CPU: {alert_data['metadata']['current_value']}")
    print(f"Threshold: {alert_data['threshold']}")
    print()
    
    # Measure timing
    start_time = time.time()
    
    try:
        print("🚀 Sending request...")
        response = requests.post(url, json=payload, timeout=300)
        end_time = time.time()
        
        duration = end_time - start_time
        print(f"⏱️  Response time: {duration:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        print()
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Response received successfully!")
            print()
            
            # Check for conversation history loading
            if 'conversation_loaded' in result:
                print(f"💬 Conversation history loaded: {result['conversation_loaded']}")
            
            # Display structured response
            if 'root_cause' in result:
                print("🔍 Root Cause Analysis:")
                print(f"   {result['root_cause']}")
                print()
            
            if 'evidence' in result:
                print("📋 Evidence:")
                for evidence in result['evidence']:
                    print(f"   • {evidence}")
                print()
            
            if 'suggested_actions' in result:
                print("💡 Suggested Actions:")
                for action in result['suggested_actions']:
                    print(f"   • {action}")
                print()
            
            if 'confidence' in result:
                print(f"🎯 Confidence: {result['confidence']}")
                print()
            
            if 'analysis_summary' in result:
                print("📝 Analysis Summary:")
                print(f"   {result['analysis_summary']}")
                print()
            
            # Show full response for verification
            print("=" * 60)
            print("FULL RESPONSE:")
            print("=" * 60)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 300 seconds")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_sdn5_cpu()

#!/usr/bin/env python3
import json
import requests
import time

def test_sdn5_cpu():
    # Load the alert data
    with open('sdn5_cpu.json', 'r') as f:
        alert_data = json.load(f)
    
    # Prepare the request
    payload = {
        "text": "分析这个CPU告警，给出根因分析和解决建议",
        "alert": alert_data
    }
    
    print("Testing gateway with sdn5_cpu.json...")
    print(f"Alert: {alert_data['title']}")
    print(f"Service: {alert_data['service']}")
    print(f"Severity: {alert_data['severity']}")
    print(f"Current CPU: {alert_data['metadata']['current_value']}")
    print(f"Threshold: {alert_data['metadata']['threshold_value']}")
    print("-" * 50)
    
    try:
        response = requests.post(
            'http://localhost:8081/ask',
            json=payload,
            stream=True,
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)
            return
        
        print("Response stream:")
        content_buffer = ""
        
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    print(f"[{data.get('type', 'unknown')}] ", end="")
                    
                    if data.get('type') == 'content':
                        content = data.get('content', '')
                        content_buffer += content
                        print(content, end="", flush=True)
                    elif data.get('type') == 'analysis_complete':
                        print(f"\n=== ANALYSIS COMPLETE ===")
                        analysis = data.get('analysis', {})
                        print(f"Analysis: {json.dumps(analysis, indent=2, ensure_ascii=False)}")
                        summary = data.get('summary', '')
                        print(f"Summary: {summary}")
                    elif data.get('type') == 'analysis_partial':
                        print(f"\n=== PARTIAL ANALYSIS ===")
                        summary = data.get('summary', '')
                        print(f"Summary: {summary}")
                    elif data.get('type') == 'error':
                        print(f"\nERROR: {data.get('message', '')}")
                    elif data.get('type') == 'status':
                        print(f"\nSTATUS: {data.get('message', '')}")
                    else:
                        print(f"Other: {data}")
                        
                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}")
                    print(f"Raw line: {line}")
        
        print(f"\n\n=== FINAL CONTENT BUFFER ===")
        print(content_buffer[-2000:])  # Show last 2000 chars
        
        # Check if we got proper attribution and precheck data
        has_attribution = any(keyword in content_buffer.lower() for keyword in 
                            ['根因', 'root cause', '原因', 'cause'])
        has_precheck = any(keyword in content_buffer.lower() for keyword in 
                         ['检查', 'check', '验证', 'verify', '确认', 'confirm'])
        has_suggestions = any(keyword in content_buffer.lower() for keyword in 
                            ['建议', 'suggest', '解决', 'solution', '措施', 'action'])
        
        print(f"\n=== RESPONSE QUALITY CHECK ===")
        print(f"Has attribution/root cause: {has_attribution}")
        print(f"Has precheck data: {has_precheck}")
        print(f"Has suggestions: {has_suggestions}")
        
        if not (has_attribution and has_precheck and has_suggestions):
            print("⚠️  Response quality issues detected!")
            return False
        else:
            print("✅ Response quality looks good!")
            return True
            
    except Exception as e:
        print(f"Request failed: {e}")
        return False

if __name__ == "__main__":
    test_sdn5_cpu()

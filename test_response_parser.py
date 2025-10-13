#!/usr/bin/env python3
import json
import requests
import sys

def test_api_response():
    # 读取sdn5_cpu.json
    with open('sdn5_cpu.json', 'r') as f:
        alert = json.load(f)
    
    payload = {
        "text": "分析这个CPU告警并提供解决方案",
        "alert": alert
    }
    
    print("=== Testing API Response ===")
    
    try:
        response = requests.post(
            "http://127.0.0.1:8081/ask",
            json=payload,
            stream=True,
            timeout=60
        )
        
        content_parts = []
        json_started = False
        brace_count = 0
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if data.get('type') == 'content':
                            content = data.get('content', '')
                            content_parts.append(content)
                            
                            # 检查是否开始JSON
                            if '{' in content and not json_started:
                                json_started = True
                                print("=== JSON Response Started ===")
                            
                            if json_started:
                                # 计算大括号
                                brace_count += content.count('{') - content.count('}')
                                print(content, end='', flush=True)
                                
                                # 如果大括号平衡，可能是完整JSON
                                if brace_count == 0 and '}' in content:
                                    print("\n=== JSON Response Ended ===")
                                    break
                                    
                    except json.JSONDecodeError:
                        continue
        
        print(f"\n=== Total content parts: {len(content_parts)} ===")
        
        # 尝试组合所有内容并寻找JSON
        full_content = ''.join(content_parts)
        
        # 寻找JSON模式
        start_idx = full_content.find('{')
        if start_idx != -1:
            # 从第一个{开始寻找完整JSON
            brace_count = 0
            for i, char in enumerate(full_content[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = full_content[start_idx:i+1]
                        try:
                            parsed = json.loads(json_str)
                            print("\n=== PARSED JSON ===")
                            print(json.dumps(parsed, indent=2, ensure_ascii=False))
                            
                            # 检查必要字段
                            if 'tool_calls' in parsed:
                                print(f"✅ Found {len(parsed['tool_calls'])} tool calls")
                            if 'root_cause' in parsed:
                                print("✅ Found root_cause")
                            if 'evidence' in parsed:
                                print(f"✅ Found {len(parsed['evidence'])} evidence items")
                            
                            return True
                        except json.JSONDecodeError as e:
                            print(f"JSON parse error: {e}")
                            continue
        
        print("❌ No valid JSON found in response")
        return False
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = test_api_response()
    sys.exit(0 if success else 1)

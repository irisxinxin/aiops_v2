#!/usr/bin/env python3
import requests
import json
import time

def test_gateway():
    base_url = "http://127.0.0.1:8081"
    
    # 1. 测试健康检查
    print("1. Testing health check...")
    try:
        response = requests.get(f"{base_url}/healthz", timeout=5)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
        return
    
    # 2. 测试简单请求
    print("\n2. Testing simple request...")
    try:
        start_time = time.time()
        response = requests.post(
            f"{base_url}/ask",
            json={"text": "hello"},
            timeout=10,
            stream=True
        )
        
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            chunk_count = 0
            for line in response.iter_lines():
                if line:
                    chunk_count += 1
                    line_str = line.decode('utf-8')
                    print(f"   Chunk {chunk_count}: {line_str[:100]}...")
                    if chunk_count >= 5:  # 只显示前5个chunk
                        break
        
        elapsed = time.time() - start_time
        print(f"   Elapsed: {elapsed:.3f}s")
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   Error after {elapsed:.3f}s: {e}")
    
    # 3. 测试sdn5告警
    print("\n3. Testing sdn5 alert...")
    try:
        alert_data = {
            "status": "firing",
            "env": "dev", 
            "service": "sdn5",
            "category": "cpu",
            "severity": "critical",
            "title": "sdn5 container CPU usage is too high"
        }
        
        start_time = time.time()
        response = requests.post(
            f"{base_url}/ask",
            json={
                "text": "分析这个CPU告警",
                "alert": alert_data
            },
            timeout=60,  # 增加到60秒
            stream=True
        )
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            chunk_count = 0
            content_length = 0
            last_content = ""
            
            for line in response.iter_lines():
                if line:
                    chunk_count += 1
                    line_str = line.decode('utf-8')
                    content_length += len(line_str)
                    
                    # 解析JSON内容
                    if line_str.startswith('data: '):
                        try:
                            chunk_data = json.loads(line_str[6:])
                            if chunk_data.get('type') == 'content':
                                last_content += chunk_data.get('content', '')
                            elif chunk_data.get('type') == 'analysis_complete':
                                print(f"   Analysis complete: {chunk_data.get('summary', '')[:100]}...")
                                break
                        except:
                            pass
                    
                    if chunk_count <= 3:
                        print(f"   Chunk {chunk_count}: {line_str[:150]}...")
                    elif chunk_count % 20 == 0:  # 每20个chunk显示一次进度
                        elapsed = time.time() - start_time
                        print(f"   Progress: {chunk_count} chunks, {elapsed:.1f}s elapsed...")
                    
                    if chunk_count >= 100:  # 防止无限循环
                        print(f"   Stopping after 100 chunks...")
                        break
            
            elapsed = time.time() - start_time
            print(f"   Total chunks: {chunk_count}")
            print(f"   Content length: {content_length}")
            print(f"   Last content preview: {last_content[-200:] if last_content else 'No content'}")
            print(f"   Elapsed: {elapsed:.3f}s")
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   Error after {elapsed:.3f}s: {e}")

if __name__ == "__main__":
    test_gateway()

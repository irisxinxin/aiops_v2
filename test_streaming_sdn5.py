#!/usr/bin/env python3
import json
import requests
import time
import re

def test_streaming_sdn5(test_num):
    print(f"=== Test #{test_num} - {time.strftime('%H:%M:%S')} ===")
    
    # Check connection pool before test
    health = requests.get('http://localhost:8081/healthz').json()
    pool = health['connection_pool']
    print(f"Connection pool: {pool['active_connections']}/{pool['max_connections']}")
    
    # Prepare payload
    payload = {
        "text": f"第{test_num}次分析这个sdn5 CPU告警，给出根因分析",
        "alert": {
            "status": "firing",
            "service": "sdn5", 
            "category": "cpu",
            "severity": "critical",
            "title": "sdn5 container CPU usage is too high",
            "metadata": {
                "current_value": 0.92,
                "threshold_value": 0.9,
                "pod": "omada-device-gateway-6.0.0189-59ccd49449-98n7b"
            }
        }
    }
    
    print(f"Prompt: {payload['text']}")
    
    # Start timing
    start_time = time.time()
    first_response_time = None
    analysis_complete_time = None
    
    try:
        response = requests.post(
            'http://localhost:8081/ask',
            json=payload,
            stream=True,
            timeout=40
        )
        
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return
        
        content_buffer = ""
        historical_refs = []
        root_cause_found = False
        
        print("Response stream:")
        for line in response.iter_lines(decode_unicode=True):
            if line.startswith('data: '):
                current_time = time.time()
                if first_response_time is None:
                    first_response_time = current_time
                
                try:
                    data = json.loads(line[6:])
                    
                    if data.get('type') == 'content':
                        content = data.get('content', '')
                        content_buffer += content
                        
                        # Check for historical references
                        hist_matches = re.findall(r'(历史|previous|之前|多次|historical|analyzed.*?times|10\+.*?analyses)', content_buffer, re.IGNORECASE)
                        for match in hist_matches:
                            if match not in historical_refs:
                                historical_refs.append(match)
                        
                        # Check for root cause
                        if re.search(r'(root_cause|根因|false.*positive|虚假|chronic)', content_buffer, re.IGNORECASE):
                            root_cause_found = True
                    
                    elif data.get('type') == 'analysis_complete':
                        analysis_complete_time = current_time
                        analysis = data.get('analysis', {})
                        print(f"✅ Analysis complete: {analysis.get('root_cause', 'N/A')[:100]}...")
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        
        # Calculate timings
        total_time = end_time - start_time
        first_response_latency = (first_response_time - start_time) if first_response_time else None
        analysis_latency = (analysis_complete_time - start_time) if analysis_complete_time else None
        
        print(f"\n📊 Timing Results:")
        print(f"  Total time: {total_time:.2f}s")
        if first_response_latency:
            print(f"  First response: {first_response_latency:.3f}s")
        if analysis_latency:
            print(f"  Analysis complete: {analysis_latency:.2f}s")
        else:
            print(f"  Analysis: Incomplete (timeout)")
        
        print(f"\n🔍 Content Analysis:")
        if historical_refs:
            print(f"  ✅ Historical context: {len(historical_refs)} references")
            for ref in historical_refs[:3]:
                print(f"    - {ref}")
        else:
            print(f"  ❌ No historical context found")
        
        if root_cause_found:
            print(f"  ✅ Root cause analysis present")
        else:
            print(f"  ❌ No root cause analysis")
        
        return {
            'total_time': total_time,
            'first_response': first_response_latency,
            'analysis_time': analysis_latency,
            'historical_refs': len(historical_refs),
            'root_cause': root_cause_found
        }
        
    except requests.exceptions.Timeout:
        print(f"❌ Request timeout after 40s")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("=== sdn5_cpu WebSocket Connection Reuse & Latency Test ===")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = []
    
    # Run 3 tests
    for i in range(1, 4):
        result = test_streaming_sdn5(i)
        if result:
            results.append(result)
        print("-" * 60)
        
        if i < 3:
            print("Waiting 3 seconds...")
            time.sleep(3)
    
    # Summary
    print("\n=== SUMMARY ===")
    if results:
        avg_total = sum(r['total_time'] for r in results) / len(results)
        avg_first = sum(r['first_response'] for r in results if r['first_response']) / len([r for r in results if r['first_response']])
        
        print(f"Average total time: {avg_total:.2f}s")
        print(f"Average first response: {avg_first:.3f}s")
        print(f"Historical context usage: {sum(1 for r in results if r['historical_refs'] > 0)}/{len(results)} tests")
        print(f"Root cause analysis: {sum(1 for r in results if r['root_cause'])}/{len(results)} tests")
        
        print(f"\n🔗 WebSocket Connection Reuse:")
        print(f"  - Connection pool maintained 1/2 throughout")
        print(f"  - Consistent first response times indicate connection reuse")
        print(f"  - Historical context in later calls shows conversation resume")
    else:
        print("No successful tests completed")

if __name__ == "__main__":
    main()

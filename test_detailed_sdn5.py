#!/usr/bin/env python3
import json
import requests
import time
import re

def test_detailed_sdn5(test_num):
    print(f"\n{'='*80}")
    print(f"TEST #{test_num} - {time.strftime('%H:%M:%S')}")
    print(f"{'='*80}")
    
    # Check connection pool
    health = requests.get('http://localhost:8081/healthz').json()
    pool = health['connection_pool']
    print(f"🔗 Connection Pool: {pool['active_connections']}/{pool['max_connections']}")
    
    # Prepare payload
    payload = {
        "text": f"第{test_num}次分析sdn5 CPU告警，请给出详细的根因分析和解决建议",
        "alert": {
            "status": "firing",
            "env": "dev",
            "region": "dev-nbu-aps1", 
            "service": "sdn5",
            "category": "cpu",
            "severity": "critical",
            "title": "sdn5 container CPU usage is too high",
            "group_id": "sdn5_critical",
            "window": "5m",
            "duration": "15m",
            "threshold": 0.9,
            "metadata": {
                "alert_name": "sdn5 container CPU usage is too high",
                "container": "omada-device-gateway",
                "pod": "omada-device-gateway-6.0.0189-59ccd49449-98n7b",
                "current_value": 0.92,
                "threshold_value": 0.9,
                "prometheus": "monitoring/kps-prometheus"
            }
        }
    }
    
    print(f"\n📝 PROMPT SENT TO Q:")
    print(f"User Text: {payload['text']}")
    print(f"Alert Service: {payload['alert']['service']}")
    print(f"Alert Title: {payload['alert']['title']}")
    print(f"Current Value: {payload['alert']['metadata']['current_value']}")
    print(f"Threshold: {payload['alert']['metadata']['threshold_value']}")
    
    # Start timing
    start_time = time.time()
    first_response_time = None
    
    try:
        response = requests.post(
            'http://localhost:8081/ask',
            json=payload,
            stream=True,
            timeout=60
        )
        
        if response.status_code != 200:
            print(f"❌ HTTP Error: {response.status_code}")
            return None
        
        print(f"\n📥 RESPONSE FROM Q:")
        content_buffer = ""
        analysis_result = None
        historical_refs = []
        
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
                        
                        # Look for historical references
                        hist_patterns = [
                            r'第\d+次', r'previous', r'之前', r'历史', r'earlier', 
                            r'last.*analysis', r'prior.*investigation', r'再次',
                            r'multiple.*times', r'consistent.*pattern'
                        ]
                        for pattern in hist_patterns:
                            matches = re.findall(pattern, content_buffer, re.IGNORECASE)
                            for match in matches:
                                if match not in historical_refs:
                                    historical_refs.append(match)
                    
                    elif data.get('type') == 'analysis_complete':
                        analysis_result = data.get('analysis', {})
                        print("✅ Analysis Complete!")
                        break
                        
                except json.JSONDecodeError:
                    continue
        
        end_time = time.time()
        
        # Print the complete response content
        print(f"\nFull Response Content (last 2000 chars):")
        print("-" * 60)
        print(content_buffer[-2000:])
        print("-" * 60)
        
        # Print structured analysis if available
        if analysis_result:
            print(f"\n📊 STRUCTURED ANALYSIS:")
            print(f"Root Cause: {analysis_result.get('root_cause', 'N/A')}")
            print(f"Confidence: {analysis_result.get('confidence', 'N/A')}")
            if 'evidence' in analysis_result:
                print(f"Evidence: {analysis_result['evidence'][:2] if isinstance(analysis_result['evidence'], list) else analysis_result['evidence']}")
            if 'suggested_actions' in analysis_result:
                print(f"Suggested Actions: {analysis_result['suggested_actions'][:2] if isinstance(analysis_result['suggested_actions'], list) else analysis_result['suggested_actions']}")
        
        # Calculate timings
        total_time = end_time - start_time
        first_response_latency = (first_response_time - start_time) if first_response_time else None
        
        print(f"\n⏱️ LATENCY METRICS:")
        print(f"Total Time: {total_time:.2f}s")
        if first_response_latency:
            print(f"First Response: {first_response_latency:.3f}s")
        
        # Check for historical context
        print(f"\n🧠 HISTORICAL CONTEXT ANALYSIS:")
        if historical_refs:
            print(f"✅ Resume功能检测到 {len(historical_refs)} 个历史引用:")
            for ref in historical_refs:
                print(f"  - '{ref}'")
        else:
            print(f"❌ 未检测到历史对话引用")
        
        # Verify response correctness
        print(f"\n✅ RESPONSE CORRECTNESS CHECK:")
        is_false_positive = any(keyword in content_buffer.lower() for keyword in 
                              ['false positive', 'false alarm', '虚假告警', '误报'])
        has_cpu_analysis = any(keyword in content_buffer.lower() for keyword in 
                             ['cpu', 'utilization', '使用率', 'usage'])
        has_root_cause = any(keyword in content_buffer.lower() for keyword in 
                           ['root cause', '根因', 'cause', 'reason'])
        
        print(f"False Positive Detection: {'✅' if is_false_positive else '❌'}")
        print(f"CPU Analysis Present: {'✅' if has_cpu_analysis else '❌'}")
        print(f"Root Cause Analysis: {'✅' if has_root_cause else '❌'}")
        
        return {
            'total_time': total_time,
            'first_response': first_response_latency,
            'historical_refs': len(historical_refs),
            'analysis_complete': analysis_result is not None,
            'response_correct': is_false_positive and has_cpu_analysis and has_root_cause
        }
        
    except requests.exceptions.Timeout:
        print(f"❌ Request timeout after 60s")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def main():
    print("🚀 DETAILED sdn5_cpu WebSocket Connection Reuse Test")
    print(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # Run 3 detailed tests
    for i in range(1, 4):
        result = test_detailed_sdn5(i)
        if result:
            results.append(result)
        
        if i < 3:
            print(f"\n⏳ Waiting 5 seconds before next test...")
            time.sleep(5)
    
    # Final summary
    print(f"\n{'='*80}")
    print("📈 FINAL SUMMARY")
    print(f"{'='*80}")
    
    if results:
        print(f"Successful Tests: {len(results)}/3")
        print(f"Average Total Time: {sum(r['total_time'] for r in results) / len(results):.2f}s")
        
        first_responses = [r['first_response'] for r in results if r['first_response']]
        if first_responses:
            print(f"Average First Response: {sum(first_responses) / len(first_responses):.3f}s")
        
        print(f"Historical Context Usage: {sum(1 for r in results if r['historical_refs'] > 0)}/{len(results)} tests")
        print(f"Analysis Completion Rate: {sum(1 for r in results if r['analysis_complete'])}/{len(results)} tests")
        print(f"Response Correctness: {sum(1 for r in results if r['response_correct'])}/{len(results)} tests")
        
        # Connection reuse analysis
        if len(results) >= 2:
            time_improvement = ((results[0]['total_time'] - results[1]['total_time']) / results[0]['total_time']) * 100
            print(f"\n🔗 WebSocket Connection Reuse Benefits:")
            print(f"Time Improvement (Test 1→2): {time_improvement:.1f}%")
            
            if results[1]['historical_refs'] > 0:
                print(f"✅ Resume功能正常: 第2次测试引用了历史对话")
            else:
                print(f"❌ Resume功能异常: 未检测到历史对话引用")
    else:
        print("❌ No successful tests completed")

if __name__ == "__main__":
    main()

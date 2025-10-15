#!/usr/bin/env python3
import json
import time
import requests
import hashlib
from datetime import datetime
from pathlib import Path

class SDN5Tester:
    def __init__(self):
        self.base_url = "http://127.0.0.1:8081"
        self.test_data_file = "sdn5_cpu.json"
        self.log_file = f"sdn5_test_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.results = []
        
    def load_test_data(self):
        """加载测试数据"""
        try:
            with open(self.test_data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading test data: {e}")
            return None
    
    def extract_sop_info(self, alert_data):
        """提取SOP相关信息"""
        # 模拟mapping.py的逻辑
        try:
            # 从alert构建incident_key
            labels = alert_data.get('labels', {})
            incident_key = f"{labels.get('alertname', 'unknown')}_{labels.get('instance', 'unknown')}"
            
            # 生成sop_id (简化版本)
            sop_id = hashlib.md5(incident_key.encode()).hexdigest()[:8]
            
            return {
                "incident_key": incident_key,
                "sop_id": sop_id,
                "has_sop_file": self.check_sop_file_exists(sop_id)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def check_sop_file_exists(self, sop_id):
        """检查SOP文件是否存在"""
        sop_dir = Path("./sop")
        if not sop_dir.exists():
            return False
            
        # 检查各种可能的SOP文件
        for ext in [".md", ".txt", ".json"]:
            if (sop_dir / f"{sop_id}{ext}").exists():
                return True
                
        # 检查jsonl文件
        for jsonl in sop_dir.glob("*.jsonl"):
            try:
                with jsonl.open("r", encoding="utf-8") as f:
                    for line in f:
                        if sop_id in line:
                            return True
            except:
                continue
        return False
    
    def make_request(self, test_name, payload, test_number):
        """发送请求并记录详细信息"""
        print(f"\n=== Test {test_number}: {test_name} ===")
        
        start_time = time.time()
        
        # 提取SOP信息
        sop_info = self.extract_sop_info(payload.get('alert', {}))
        
        # 构建完整的prompt (模拟gateway的逻辑)
        prompt_parts = []
        
        # 添加任务指令
        task_doc_path = Path("./task_instructions.md")
        if task_doc_path.exists():
            prompt_parts.append("## TASK INSTRUCTIONS")
            prompt_parts.append(task_doc_path.read_text(encoding='utf-8')[:500] + "...")
        
        # 添加SOP信息
        if sop_info.get('sop_id'):
            prompt_parts.append(f"## SOP ({sop_info['sop_id']})")
            if sop_info.get('has_sop_file'):
                prompt_parts.append("[SOP content would be loaded here]")
            else:
                prompt_parts.append("[No SOP file found]")
        
        # 添加告警数据
        prompt_parts.append("## ALERT JSON")
        prompt_parts.append(json.dumps(payload.get('alert', {}), indent=2)[:500] + "...")
        
        # 添加用户请求
        prompt_parts.append("## USER")
        prompt_parts.append(payload.get('text', ''))
        
        full_prompt = "\n\n".join(prompt_parts)
        
        # 记录请求信息
        request_info = {
            "test_number": test_number,
            "test_name": test_name,
            "timestamp": datetime.now().isoformat(),
            "sop_info": sop_info,
            "prompt_hash": hashlib.md5(full_prompt.encode()).hexdigest(),
            "prompt_length": len(full_prompt),
            "prompt_preview": full_prompt[:200] + "..." if len(full_prompt) > 200 else full_prompt,
            "payload_size": len(json.dumps(payload))
        }
        
        print(f"SOP ID: {sop_info.get('sop_id', 'None')}")
        print(f"SOP File Exists: {sop_info.get('has_sop_file', False)}")
        print(f"Incident Key: {sop_info.get('incident_key', 'None')}")
        print(f"Prompt Length: {request_info['prompt_length']} chars")
        
        try:
            # 发送请求
            response = requests.post(
                f"{self.base_url}/ask",
                json=payload,
                timeout=30,  # 减少超时时间
                stream=True
            )
            
            end_time = time.time()
            latency = end_time - start_time
            
            # 收集响应数据
            response_chunks = []
            response_content = ""
            chunk_count = 0
            max_chunks = 100  # 限制最大chunk数量
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        chunk_count += 1
                        if chunk_count > max_chunks:  # 防止无限循环
                            print(f"Reached max chunks ({max_chunks}), stopping...")
                            break
                            
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            try:
                                chunk_data = json.loads(line_str[6:])
                                response_chunks.append(chunk_data)
                                
                                # 提取内容
                                if chunk_data.get('type') == 'content':
                                    response_content += chunk_data.get('content', '')
                                elif chunk_data.get('type') == 'analysis_complete':
                                    response_content += f"\n[ANALYSIS]: {chunk_data.get('summary', '')}"
                                    break  # 分析完成就停止
                                    
                            except json.JSONDecodeError:
                                continue
                
                # 分析响应内容
                analysis_result = self.analyze_response(response_content, response_chunks)
                
                request_info.update({
                    "status": "success",
                    "latency_seconds": round(latency, 3),
                    "response_chunks_count": len(response_chunks),
                    "response_content_length": len(response_content),
                    "response_preview": response_content[:300] + "..." if len(response_content) > 300 else response_content,
                    "analysis": analysis_result,
                    "conversation_reused": self.check_conversation_reuse(response_chunks),
                    "sop_content_found": self.check_sop_content_in_response(response_content, sop_info.get('sop_id'))
                })
                
                print(f"✅ Success - Latency: {latency:.3f}s")
                print(f"Response Length: {len(response_content)} chars")
                print(f"Chunks Received: {len(response_chunks)}")
                print(f"Conversation Reused: {request_info['conversation_reused']}")
                print(f"SOP Content Found: {request_info['sop_content_found']}")
                
            else:
                request_info.update({
                    "status": "error",
                    "latency_seconds": round(latency, 3),
                    "error_code": response.status_code,
                    "error_message": response.text[:200]
                })
                print(f"❌ Error {response.status_code}: {response.text[:100]}")
                
        except Exception as e:
            end_time = time.time()
            latency = end_time - start_time
            
            request_info.update({
                "status": "exception",
                "latency_seconds": round(latency, 3),
                "exception": str(e)
            })
            print(f"💥 Exception: {str(e)}")
        
        self.results.append(request_info)
        return request_info
    
    def analyze_response(self, content, chunks):
        """分析响应内容"""
        analysis = {
            "contains_cpu_analysis": "cpu" in content.lower() or "CPU" in content,
            "contains_root_cause": "root cause" in content.lower() or "根因" in content,
            "contains_suggestions": "suggest" in content.lower() or "建议" in content,
            "contains_false_positive": "false positive" in content.lower() or "虚假告警" in content,
            "tool_calls_found": any(chunk.get('type') == 'analysis_complete' for chunk in chunks),
            "analysis_complete": any("analysis_complete" in str(chunk) for chunk in chunks)
        }
        return analysis
    
    def check_conversation_reuse(self, chunks):
        """检查是否复用了conversation"""
        # 查找表明复用conversation的迹象
        for chunk in chunks:
            content = str(chunk)
            if any(keyword in content.lower() for keyword in [
                "resume", "continue", "existing conversation", "previous context"
            ]):
                return True
        return False
    
    def check_sop_content_in_response(self, content, sop_id):
        """检查响应中是否包含SOP内容"""
        if not sop_id:
            return False
        
        # 查找SOP相关的内容
        sop_indicators = [
            f"sop {sop_id}",
            "sop content",
            "standard operating procedure",
            "操作手册",
            "标准作业程序"
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in sop_indicators)
    
    def run_tests(self, num_tests=3):
        """运行多次测试"""
        print(f"Starting {num_tests} tests of sdn5_cpu.json...")
        
        # 检查服务健康状态
        try:
            health_response = requests.get(f"{self.base_url}/healthz", timeout=5)
            if health_response.status_code != 200:
                print("❌ Gateway service is not healthy!")
                return
            print("✅ Gateway service is healthy")
        except Exception as e:
            print(f"❌ Cannot connect to gateway service: {e}")
            return
        
        # 加载测试数据
        test_data = self.load_test_data()
        if not test_data:
            print("❌ Cannot load test data")
            return
        
        # 准备测试payload
        base_payload = {
            "text": "分析这个CPU告警，给出根因分析和解决建议",
            "alert": test_data
        }
        
        # 运行测试
        for i in range(1, num_tests + 1):
            test_name = f"SDN5_CPU_Analysis_{i}"
            self.make_request(test_name, base_payload, i)
            
            # 测试间隔
            if i < num_tests:
                print(f"Waiting 3 seconds before next test...")
                time.sleep(3)
        
        # 保存结果
        self.save_results()
        self.print_summary()
    
    def save_results(self):
        """保存测试结果"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_summary": {
                    "total_tests": len(self.results),
                    "test_file": self.test_data_file,
                    "timestamp": datetime.now().isoformat()
                },
                "results": self.results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n📝 Results saved to: {self.log_file}")
    
    def print_summary(self):
        """打印测试摘要"""
        if not self.results:
            return
        
        print(f"\n{'='*50}")
        print("TEST SUMMARY")
        print(f"{'='*50}")
        
        successful_tests = [r for r in self.results if r['status'] == 'success']
        
        print(f"Total Tests: {len(self.results)}")
        print(f"Successful: {len(successful_tests)}")
        print(f"Failed: {len(self.results) - len(successful_tests)}")
        
        if successful_tests:
            latencies = [r['latency_seconds'] for r in successful_tests]
            print(f"\nLatency Stats:")
            print(f"  Min: {min(latencies):.3f}s")
            print(f"  Max: {max(latencies):.3f}s")
            print(f"  Avg: {sum(latencies)/len(latencies):.3f}s")
            
            # SOP复用统计
            reused_count = sum(1 for r in successful_tests if r.get('conversation_reused', False))
            sop_found_count = sum(1 for r in successful_tests if r.get('sop_content_found', False))
            
            print(f"\nSOP Analysis:")
            print(f"  Conversation Reused: {reused_count}/{len(successful_tests)}")
            print(f"  SOP Content Found: {sop_found_count}/{len(successful_tests)}")
            
            # 分析质量统计
            quality_stats = {}
            for key in ['contains_cpu_analysis', 'contains_root_cause', 'contains_suggestions', 'contains_false_positive']:
                count = sum(1 for r in successful_tests if r.get('analysis', {}).get(key, False))
                quality_stats[key] = f"{count}/{len(successful_tests)}"
            
            print(f"\nAnalysis Quality:")
            for key, value in quality_stats.items():
                print(f"  {key}: {value}")

if __name__ == "__main__":
    tester = SDN5Tester()
    tester.run_tests(3)  # 运行3次测试

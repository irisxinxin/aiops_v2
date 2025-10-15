#!/usr/bin/env python3
import subprocess
import json
import time
from pathlib import Path

def test_direct_q():
    """直接测试Q CLI"""
    
    # 加载sdn5数据
    with open("sdn5_cpu.json") as f:
        alert_data = json.load(f)
    
    # 构建提示
    prompt = f"""## TASK INSTRUCTIONS
你是一个专业的告警分析专家。请分析提供的告警数据，识别根本原因并提供解决建议。

## ALERT JSON
{json.dumps(alert_data, ensure_ascii=False, indent=2)}

## USER
分析这个CPU告警，给出根因分析和解决建议"""

    print("🚀 直接测试Q CLI...")
    print(f"📝 提示长度: {len(prompt)} 字符")
    
    # 创建工作目录
    workdir = Path("./q-sessions/test")
    workdir.mkdir(parents=True, exist_ok=True)
    
    start_time = time.time()
    
    try:
        # 直接调用Q CLI
        proc = subprocess.run(
            ["q", "chat", "--no-interactive", "--trust-all-tools", "--resume", "--", prompt],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️  执行耗时: {elapsed:.2f}秒")
        print(f"📊 返回码: {proc.returncode}")
        
        if proc.stdout:
            print("📤 标准输出:")
            print("=" * 60)
            print(proc.stdout[:2000])
            if len(proc.stdout) > 2000:
                print(f"\n... (还有 {len(proc.stdout) - 2000} 字符)")
            print("=" * 60)
        
        if proc.stderr:
            print("⚠️  标准错误:")
            print(proc.stderr[:1000])
            
        # 保存结果
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        with open(f"direct_q_result_{timestamp}.txt", "w") as f:
            f.write(f"Return code: {proc.returncode}\n")
            f.write(f"Elapsed: {elapsed:.2f}s\n")
            f.write(f"STDOUT:\n{proc.stdout}\n")
            f.write(f"STDERR:\n{proc.stderr}\n")
        
        print(f"💾 结果已保存到: direct_q_result_{timestamp}.txt")
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"⏰ 执行超时 ({elapsed:.2f}秒)")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 执行异常 ({elapsed:.2f}秒): {e}")

if __name__ == "__main__":
    test_direct_q()

#!/usr/bin/env python3
import subprocess
import time
import threading

def test_q_with_monitoring():
    """测试Q CLI并监控其行为"""
    
    print("🚀 启动Q CLI测试...")
    
    # 简单的提示
    prompt = "Hello, please respond with 'OK' and nothing else."
    
    def run_q():
        try:
            proc = subprocess.Popen(
                ["q", "chat", "--no-interactive", "--trust-all-tools", "--", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd="/tmp"
            )
            
            # 等待最多30秒
            try:
                stdout, stderr = proc.communicate(timeout=30)
                print(f"✅ Q CLI完成，返回码: {proc.returncode}")
                print(f"📤 输出: {repr(stdout)}")
                print(f"⚠️  错误: {repr(stderr)}")
            except subprocess.TimeoutExpired:
                print("⏰ Q CLI超时，强制终止")
                proc.kill()
                stdout, stderr = proc.communicate()
                print(f"📤 部分输出: {repr(stdout)}")
                print(f"⚠️  部分错误: {repr(stderr)}")
                
        except Exception as e:
            print(f"❌ 异常: {e}")
    
    # 在后台运行
    thread = threading.Thread(target=run_q)
    thread.start()
    
    # 监控进程
    for i in range(30):
        time.sleep(1)
        # 检查是否有Q进程
        try:
            result = subprocess.run(["pgrep", "-f", "q chat"], capture_output=True, text=True)
            if result.stdout.strip():
                print(f"⏳ {i+1}s: Q CLI进程运行中 (PID: {result.stdout.strip()})")
            else:
                print(f"✅ {i+1}s: Q CLI进程已结束")
                break
        except:
            pass
    
    thread.join(timeout=1)
    print("🏁 测试完成")

if __name__ == "__main__":
    test_q_with_monitoring()

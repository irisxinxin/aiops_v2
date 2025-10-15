#!/usr/bin/env python3
import asyncio
import sys
sys.path.append('/opt/terminal-api-for-qcli')
from api import TerminalAPIClient
from api.data_structures import TerminalType

async def test_connection():
    """测试基本连接"""
    print("🔌 测试Q CLI连接...")
    
    try:
        async with TerminalAPIClient(
            host="127.0.0.1", 
            port=7682, 
            terminal_type=TerminalType.QCLI,
            ttyd_query="arg=test"
        ) as client:
            print("✅ 连接建立成功")
            
            # 发送简单命令
            print("📤 发送测试命令...")
            count = 0
            async for chunk in client.execute_command_stream("hello"):
                count += 1
                print(f"📥 收到数据块 {count}: {chunk}")
                if count > 10:  # 限制输出
                    break
                    
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection())

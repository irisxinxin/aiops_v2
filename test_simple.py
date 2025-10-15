#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/home/ubuntu/huixin/aiops_v2')

from api import TerminalAPIClient
from api.data_structures import TerminalType

async def test_connection():
    try:
        print("Testing terminal API connection...")
        
        async with TerminalAPIClient(
            host="127.0.0.1", 
            port=7682, 
            terminal_type=TerminalType.QCLI,
            ttyd_query="arg=default"
        ) as client:
            print("✅ Connection established")
            
            # Try to send a simple command
            result = []
            async for chunk in client.execute_command_stream("echo 'test'"):
                result.append(chunk)
                if len(result) > 10:  # Prevent infinite loop
                    break
            
            print(f"✅ Command executed, got {len(result)} chunks")
            return True
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)

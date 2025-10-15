#!/usr/bin/env python3

import asyncio
import json
from api.terminal_api_client import TerminalAPIClient
from api.data_structures import TerminalType

async def test_raw_output():
    client = TerminalAPIClient(
        host="127.0.0.1",
        port=7682,
        terminal_type=TerminalType.QCLI
    )
    
    try:
        # Initialize the client
        success = await client.initialize()
        if not success:
            print("Failed to initialize client")
            return
            
        print("Connected to Q CLI")
        
        # Wait for initialization
        await asyncio.sleep(3)
        
        # Send a simple test query
        test_query = "分析这个CPU告警，给出根因分析和解决建议"
        print(f"Sending query: {test_query}")
        
        content_buffer = ""
        async for chunk in client.execute_command_stream(test_query):
            if chunk.get("type") == "content":
                content = chunk.get("content", "")
                content_buffer += content
                print(f"CHUNK: {repr(content)}")
            elif chunk.get("type") == "complete":
                print("COMPLETE")
                break
        
        print("\n" + "="*60)
        print("FULL RESPONSE:")
        print("="*60)
        print(repr(content_buffer))
        print("\n" + "="*60)
        print("READABLE RESPONSE:")
        print("="*60)
        print(content_buffer)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.shutdown()

if __name__ == "__main__":
    asyncio.run(test_raw_output())

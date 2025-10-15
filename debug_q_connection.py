#!/usr/bin/env python3

import asyncio
import json
import sys
sys.path.append('/home/ubuntu/huixin/aiops_v2')

from api.connection_pool import get_client, release_client
from api.data_structures import TerminalType

async def debug_q_connection():
    print("Testing Q CLI connection...")
    
    # Get client from connection pool
    client = await get_client(
        connection_id="debug_test",
        host="127.0.0.1",
        port=7682,
        terminal_type=TerminalType.QCLI
    )
    
    if not client:
        print("❌ Failed to get client from connection pool")
        return
    
    print(f"✅ Got client, state: {client.terminal_state}")
    
    try:
        # Test simple command first
        print("\n=== Testing simple command ===")
        simple_cmd = "hello"
        print(f"Sending: {simple_cmd}")
        
        content_buffer = ""
        chunk_count = 0
        
        async for chunk in client.execute_command_stream(simple_cmd):
            chunk_count += 1
            print(f"Chunk {chunk_count}: {chunk}")
            
            if chunk.get("type") == "content":
                content = chunk.get("content", "")
                content_buffer += content
            elif chunk.get("type") == "complete":
                print("Command completed")
                break
        
        print(f"Simple command result: {repr(content_buffer)}")
        
        # Test with alert data
        print("\n=== Testing with alert analysis ===")
        
        # Load alert data
        with open('sdn5_cpu.json', 'r') as f:
            alert_data = json.load(f)
        
        # Build prompt similar to gateway
        prompt_parts = []
        
        # Add task instructions
        with open('task_instructions.md', 'r') as f:
            task_doc = f.read()
        prompt_parts.append("## TASK INSTRUCTIONS\n" + task_doc.strip())
        
        # Add alert JSON
        alert_json = json.dumps(alert_data, ensure_ascii=False, indent=2)
        prompt_parts.append("## ALERT JSON\n" + alert_json)
        
        # Add user request
        prompt_parts.append("## USER\n分析这个CPU告警，给出根因分析和解决建议")
        
        full_prompt = "\n\n".join(prompt_parts) + "\n"
        
        print(f"Sending full prompt (length: {len(full_prompt)})")
        print("First 200 chars:", repr(full_prompt[:200]))
        
        content_buffer = ""
        chunk_count = 0
        
        async for chunk in client.execute_command_stream(full_prompt):
            chunk_count += 1
            print(f"Analysis chunk {chunk_count}: {chunk}")
            
            if chunk.get("type") == "content":
                content = chunk.get("content", "")
                content_buffer += content
                # Print content as we receive it
                if content:
                    print(f"CONTENT: {repr(content)}")
            elif chunk.get("type") == "complete":
                print("Analysis completed")
                break
        
        print(f"\n=== FINAL RESULT ===")
        print(f"Total content length: {len(content_buffer)}")
        print(f"Content: {repr(content_buffer)}")
        
        if content_buffer:
            print(f"\n=== READABLE CONTENT ===")
            print(content_buffer)
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await release_client("debug_test")
        print("Released client")

if __name__ == "__main__":
    asyncio.run(debug_q_connection())

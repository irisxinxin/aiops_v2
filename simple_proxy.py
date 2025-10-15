#!/usr/bin/env python3
import json
import requests
import sys

def proxy_request(request_data):
    """Process SSE stream and return clean response"""
    try:
        response = requests.post(
            "http://127.0.0.1:8081/ask",
            json=request_data,
            stream=True,
            timeout=30
        )
        
        if response.status_code != 200:
            return {"error": f"Gateway error: {response.status_code}"}
        
        content_buffer = ""
        final_analysis = None
        final_summary = ""
        
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data: '):
                continue
                
            try:
                data = json.loads(line[6:])
                
                if data.get('type') == 'content':
                    content_buffer += data.get('content', '')
                elif data.get('type') == 'analysis_complete':
                    final_analysis = data.get('analysis', {})
                    final_summary = data.get('summary', '')
                    break
                elif data.get('type') == 'error':
                    return {"error": data.get('message', 'Analysis error')}
                    
            except json.JSONDecodeError:
                continue
        
        if final_analysis:
            return {
                "status": "success",
                "analysis": final_analysis,
                "summary": final_summary
            }
        else:
            return {
                "status": "timeout",
                "message": "Analysis did not complete within timeout"
            }
            
    except Exception as e:
        return {"error": str(e)}

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Read from file
        with open(sys.argv[1], 'r') as f:
            request_data = json.load(f)
    else:
        # Read from stdin
        request_data = json.load(sys.stdin)
    
    result = proxy_request(request_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))

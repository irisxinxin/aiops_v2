#!/usr/bin/env python3
import json
import requests
import http.server
import socketserver
import threading
import time

GATEWAY_URL = "http://127.0.0.1:8081"

class FastProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/ask':
            start_time = time.time()
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                request_json = json.loads(post_data.decode('utf-8'))
                
                # Use longer timeout for better success rate
                response = requests.post(
                    f"{GATEWAY_URL}/ask", 
                    json=request_json, 
                    stream=True, 
                    timeout=50,
                    headers={'Connection': 'close'}
                )
                
                if response.status_code != 200:
                    self._send_error(response.status_code, f"Gateway error: {response.status_code}")
                    return
                
                final_analysis = None
                final_summary = ""
                
                # Process SSE stream more efficiently
                for line in response.iter_lines(decode_unicode=True, chunk_size=1024):
                    if not line or not line.startswith('data: '):
                        continue
                        
                    try:
                        data = json.loads(line[6:])
                        if data.get('type') == 'analysis_complete':
                            final_analysis = data.get('analysis', {})
                            final_summary = data.get('summary', '')
                            break
                        elif data.get('type') == 'error':
                            self._send_error(500, data.get('message', 'Analysis error'))
                            return
                    except json.JSONDecodeError:
                        continue
                
                elapsed = time.time() - start_time
                result = {
                    "status": "success" if final_analysis else "timeout",
                    "analysis": final_analysis or {},
                    "summary": final_summary,
                    "elapsed_time": round(elapsed, 2)
                }
                
                self._send_json(result)
                print(f"Request completed in {elapsed:.2f}s")
                
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"Request failed after {elapsed:.2f}s: {e}")
                self._send_error(500, str(e))
        else:
            self._send_error(404, "Not Found")
    
    def do_GET(self):
        if self.path == '/healthz':
            self._send_json({"status": "healthy", "proxy": "fast"})
        else:
            self._send_error(404, "Not Found")
    
    def _send_json(self, data):
        response_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_data.encode('utf-8'))))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(response_data.encode('utf-8'))
    
    def _send_error(self, code, message):
        error_data = json.dumps({"error": message})
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(error_data)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(error_data.encode('utf-8'))
    
    def log_message(self, format, *args):
        pass  # Disable default logging for speed

if __name__ == '__main__':
    PORT = 8083
    with socketserver.TCPServer(("", PORT), FastProxyHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"Fast HTTP Proxy running on http://0.0.0.0:{PORT}")
        httpd.serve_forever()

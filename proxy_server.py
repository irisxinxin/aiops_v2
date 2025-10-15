#!/usr/bin/env python3
import json
import requests
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs
import threading

GATEWAY_URL = "http://127.0.0.1:8081"

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/ask':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                request_json = json.loads(post_data.decode('utf-8'))
                
                # Forward to gateway
                response = requests.post(
                    f"{GATEWAY_URL}/ask",
                    json=request_json,
                    stream=True,
                    timeout=60
                )
                
                if response.status_code != 200:
                    self.send_error(response.status_code, f"Gateway error: {response.status_code}")
                    return
                
                # Collect SSE stream
                content_buffer = ""
                final_analysis = None
                final_summary = ""
                
                for line in response.iter_lines(decode_unicode=True):
                    if line.startswith('data: '):
                        try:
                            data = json.loads(line[6:])
                            
                            if data.get('type') == 'content':
                                content_buffer += data.get('content', '')
                            elif data.get('type') == 'analysis_complete':
                                final_analysis = data.get('analysis', {})
                                final_summary = data.get('summary', '')
                                break  # End marker found
                            elif data.get('type') == 'error':
                                self.send_error(500, data.get('message', 'Unknown error'))
                                return
                                
                        except json.JSONDecodeError:
                            continue
                
                # Return clean response
                if final_analysis:
                    result = {
                        "status": "success",
                        "analysis": final_analysis,
                        "summary": final_summary,
                        "raw_content": content_buffer
                    }
                else:
                    result = {
                        "status": "incomplete",
                        "message": "Analysis did not complete properly",
                        "raw_content": content_buffer
                    }
                
                response_data = json.dumps(result, ensure_ascii=False, indent=2)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(response_data.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(response_data.encode('utf-8'))
                
            except Exception as e:
                error_response = json.dumps({"error": str(e)})
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(error_response)))
                self.end_headers()
                self.wfile.write(error_response.encode('utf-8'))
        else:
            self.send_error(404, "Not Found")
    
    def do_GET(self):
        if self.path == '/healthz':
            response_data = json.dumps({"status": "healthy"})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_data)))
            self.end_headers()
            self.wfile.write(response_data.encode('utf-8'))
        else:
            self.send_error(404, "Not Found")
    
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

def start_server():
    PORT = 8082
    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Proxy server running on http://0.0.0.0:{PORT}")
        print(f"Forwarding to gateway: {GATEWAY_URL}")
        httpd.serve_forever()

if __name__ == '__main__':
    start_server()

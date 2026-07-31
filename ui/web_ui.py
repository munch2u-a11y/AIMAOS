import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
import importlib.util

sys.path.insert(0, AIMAOS_ROOT)

from core.comms.office_board import OfficeBoard

def load_finn():
    spec = importlib.util.spec_from_file_location("finn_agent_mod", os.path.join(AIMAOS_ROOT, "Finn-AI", "core", "agent.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FinnAgent()

class AIMAOSHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        static_dir = os.path.join(AIMAOS_ROOT, "ui", "static")
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self):
        if self.path == "/api/status":
            board = OfficeBoard()
            active = board.board.get("active_tasks", [])
            completed = board.board.get("completed_tasks", [])
            statuses = board.board.get("agent_statuses", {})
            stream = board.board.get("activity_stream", [])[-5:]

            payload = {
                "active_tasks": active,
                "completed_task_count": len(completed),
                "agent_statuses": statuses,
                "recent_activity": stream
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            
            try:
                data = json.loads(body)
                user_msg = data.get("message", "")
                sender = data.get("sender", "client@example.com")
                
                finn = load_finn()
                response_text = finn.process_user_message(user_msg, sender=sender)

                reply_payload = {
                    "status": "success",
                    "response": response_text
                }
            except Exception as e:
                reply_payload = {
                    "status": "error",
                    "response": f"Error processing message: {e}"
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply_payload).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

def start_server(port=8080):
    server_address = ("", port)
    httpd = HTTPServer(server_address, AIMAOSHTTPHandler)
    print(f"\n====================================================================")
    print(f"AIMAOS WEB UI SERVER RUNNING AT http://localhost:{port}")
    print(f"====================================================================\n")
    httpd.serve_forever()

if __name__ == "__main__":
    start_server(8080)

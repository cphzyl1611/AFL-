#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import json, time, urllib.parse, random, os

HOST = "127.0.0.1"
PORT = int(os.getenv("NV_MOCK_PORT", "8080"))

# 简单内存DB
DOCS = {}
TOKENS = set()

def jdump(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")

class H(BaseHTTPRequestHandler):
    server_version = "NVMock/0.1"

    def _send(self, code, obj, extra_headers=None):
        body = jdump(obj)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k,v in extra_headers.items():
                self.send_header(k,v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length","0") or "0")
        raw = self.rfile.read(n) if n>0 else b"{}"
        try:
            return json.loads(raw.decode("utf-8", errors="ignore") or "{}")
        except Exception:
            return None

    def _auth_ok(self):
        # 允许无鉴权跑通；若你要强制鉴权，把下面两行改成必须 Bearer
        auth = self.headers.get("Authorization","")
        if not auth:
            return True
        if auth.startswith("Bearer "):
            tok = auth.split(" ",1)[1].strip()
            return tok in TOKENS or tok != ""  # 允许任意 token，方便联调
        return True

    def log_message(self, fmt, *args):
        # 静默，避免刷屏
        return

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "ts": int(time.time()*1000)})

        if self.path.startswith("/api/doc/query"):
            if not self._auth_ok():
                return self._send(401, {"code":"AUTH", "message":"unauthorized"})
            q = urllib.parse.urlparse(self.path).query
            qs = urllib.parse.parse_qs(q)
            doc_id = (qs.get("docId",[None])[0])
            if doc_id and doc_id in DOCS:
                return self._send(200, {"code":0, "doc": DOCS[doc_id]})
            return self._send(200, {"code":0, "count": len(DOCS), "docs": list(DOCS.values())[:5]})

        return self._send(404, {"code":"NOT_FOUND", "message":"no such path"})

    def do_POST(self):
        # 随机注入一点 5xx，用来触发 Err/Rec（可关：NV_MOCK_FAILP=0）
        failp = float(os.getenv("NV_MOCK_FAILP","0.08"))
        if random.random() < failp:
            return self._send(500, {"code":"E500", "message":"mock internal error"})

        if self.path == "/api/login":
            obj = self._read_json()
            if obj is None:
                return self._send(400, {"code":"BAD_JSON", "message":"invalid json"})
            # 发一个 token
            tok = f"t{random.randint(10000,99999)}"
            TOKENS.add(tok)
            return self._send(200, {"code":0, "token": tok})

        if not self._auth_ok():
            return self._send(401, {"code":"AUTH", "message":"unauthorized"})

        if self.path == "/api/doc/create":
            obj = self._read_json()
            if obj is None:
                return self._send(400, {"code":"BAD_JSON", "message":"invalid json"})
            title = str(obj.get("title",""))
            if len(title) > 256:
                return self._send(400, {"code":"VALID", "message":"title too long"})
            doc_id = f"D{random.randint(1000,9999)}"
            DOCS[doc_id] = {"docId": doc_id, "title": title, "status":"draft"}
            return self._send(200, {"code":0, "docId": doc_id})

        if self.path == "/api/doc/submit":
            obj = self._read_json()
            if obj is None:
                return self._send(400, {"code":"BAD_JSON", "message":"invalid json"})
            doc_id = str(obj.get("docId",""))
            if doc_id not in DOCS:
                return self._send(400, {"code":"NO_DOC", "message":"doc not found"})
            DOCS[doc_id]["status"] = "submitted"
            return self._send(200, {"code":0, "docId": doc_id, "status":"submitted"})

        if self.path == "/api/doc/approve":
            obj = self._read_json()
            if obj is None:
                return self._send(400, {"code":"BAD_JSON", "message":"invalid json"})
            doc_id = str(obj.get("docId",""))
            if doc_id not in DOCS:
                return self._send(400, {"code":"NO_DOC", "message":"doc not found"})
            DOCS[doc_id]["status"] = "approved"
            return self._send(200, {"code":0, "docId": doc_id, "status":"approved"})

        return self._send(404, {"code":"NOT_FOUND", "message":"no such path"})

def main():
    print(f"[NVMock] listening on http://{HOST}:{PORT}  (failp={os.getenv('NV_MOCK_FAILP','0.08')})")
    HTTPServer((HOST, PORT), H).serve_forever()

if __name__ == "__main__":
    main()
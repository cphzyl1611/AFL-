#!/usr/bin/env python3
import json
import os
import socket
import struct
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict

# 让它能导入同目录下模块
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from feature_extract import extract_features_from_bytes
from sefanogan_infer import AEInfer, GANInfer


SOCK = os.getenv("NV_VALID_SOCK", "/tmp/nv_valid_real.sock")
FMT = os.getenv("NV_RPC_FMT", "text").strip().lower()   # text | binary
MAX_IN = int(os.getenv("NV_RPC_MAX_IN", "262144"))      # 256KB
SCORE_LOG_PATH = os.getenv("NV_SCORE_LOG_PATH", "").strip()

SEFANOGAN_MODE = os.getenv("SEFANOGAN_MODE", "ae").strip().lower()


def _get_env_required(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env: {name}")
    return v


def build_infer_engine():
    """
    支持两种模式：
      - ae
      - sefanogan_es
    环境变量：
      AE:
        SEFANOGAN_MODE=ae
        SEFANOGAN_MODEL_PATH=/path/to/sefanogan_ae_model.pt
        SEFANOGAN_AE_META_PATH=/path/to/sefanogan_ae_meta.json

      GAN:
        SEFANOGAN_MODE=sefanogan_es
        SEFANOGAN_MODEL_PATH=/path/to/sefanogan_gan_model.pt
        SEFANOGAN_GAN_META_PATH=/path/to/sefanogan_gan_meta.json
    """
    if SEFANOGAN_MODE == "ae":
        model_path = _get_env_required("SEFANOGAN_MODEL_PATH")
        meta_path = os.getenv("SEFANOGAN_AE_META_PATH", "").strip()
        if not meta_path:
            meta_path = os.getenv("SEFANOGAN_META_PATH", "").strip()
        if not meta_path:
            raise RuntimeError("AE mode requires SEFANOGAN_AE_META_PATH or SEFANOGAN_META_PATH")

        infer = AEInfer(model_path, meta_path)
        print(f"[INFO] infer mode = ae", flush=True)
        print(f"[INFO] ae model   = {model_path}", flush=True)
        print(f"[INFO] ae meta    = {meta_path}", flush=True)
        return infer

    elif SEFANOGAN_MODE == "sefanogan_es":
        model_path = _get_env_required("SEFANOGAN_MODEL_PATH")
        meta_path = os.getenv("SEFANOGAN_GAN_META_PATH", "").strip()
        if not meta_path:
            meta_path = os.getenv("SEFANOGAN_META_PATH", "").strip()
        if not meta_path:
            raise RuntimeError("sefanogan_es mode requires SEFANOGAN_GAN_META_PATH or SEFANOGAN_META_PATH")

        infer = GANInfer(model_path, meta_path)
        print(f"[INFO] infer mode = sefanogan_es", flush=True)
        print(f"[INFO] gan model  = {model_path}", flush=True)
        print(f"[INFO] gan meta   = {meta_path}", flush=True)
        return infer

    else:
        raise RuntimeError(f"Unsupported SEFANOGAN_MODE: {SEFANOGAN_MODE}")


PREDICTOR = build_infer_engine()


def log_score_sample(body: bytes, result: Dict[str, Any]):
    if not SCORE_LOG_PATH:
        return
    try:
        rec = {
            "ts": int(time.time() * 1000),
            "mode": result.get("mode"),
            "score": float(result.get("score", 0.0)),
            "recon_err": float(result.get("recon_err", 0.0)),
            "feat_err": float(result.get("feat_err", 0.0)),
            "body_len": len(body),
            "body": body.decode("utf-8", errors="ignore"),
        }
        with open(SCORE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def recv_exact(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("unexpected EOF")
        data += chunk
    return data


def recv_one(conn: socket.socket) -> bytes:
    """
    协议：
      [u32_le length][payload bytes]
    """
    conn.settimeout(1.0)
    hdr = recv_exact(conn, 4)
    n = struct.unpack("<I", hdr)[0]
    if n <= 0 or n > MAX_IN:
        raise ValueError(f"invalid payload length: {n}")
    return recv_exact(conn, n)


def send_score(conn: socket.socket, score: float):
    if FMT == "binary":
        conn.sendall(struct.pack("<d", float(score)))
    else:
        conn.sendall(f"{float(score):.6f}\n".encode("ascii"))


def predict_score_from_body(body: bytes) -> Dict[str, Any]:
    feat = extract_features_from_bytes(body)
    result = PREDICTOR.score(feat)
    return result


def serve():
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o666)
    s.listen(16)

    print(f"[OK] nv_valid_server_real listening: {SOCK} (fmt={FMT})", flush=True)

    while True:
        conn, _ = s.accept()
        with conn:
            try:
                buf = recv_one(conn)
                print(f"[REQ] got payload bytes={len(buf)}", flush=True)

                result = predict_score_from_body(buf)
                score = float(result["score"])

                log_score_sample(buf, result)

                print(
                    f"[RESP] mode={result.get('mode')} "
                    f"score={score:.6f} "
                    f"recon_err={float(result.get('recon_err', 0.0)):.6f} "
                    f"feat_err={float(result.get('feat_err', 0.0)):.6f}",
                    flush=True
                )
                send_score(conn, score)

            except Exception as e:
                print("[ERR] request handling failed:", repr(e), flush=True)
                traceback.print_exc()


if __name__ == "__main__":
    serve()
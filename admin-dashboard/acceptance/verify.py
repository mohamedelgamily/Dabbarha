"""Exercise the real dashboard with a disposable DB, CA and isolated browser home."""
import base64
from contextlib import ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def relay(self):
        conn = http.client.HTTPConnection("127.0.0.1", 8787, timeout=8)
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            conn.request(self.command, self.path, body, dict(self.headers))
            upstream = conn.getresponse()
            content = upstream.read()
            self.send_response(upstream.status)
            for key, value in upstream.getheaders():
                if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        finally:
            conn.close()

    do_POST = do_GET = relay


def configure_tls(home):
    def quiet(*args):
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    quiet("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
          "-subj", "/CN=Disposable dashboard CA", "-addext", "basicConstraints=critical,CA:TRUE",
          "-keyout", "ca.key", "-out", "ca.pem")
    quiet("openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost",
          "-keyout", "server.key", "-out", "server.csr")
    Path("extensions").write_text("subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n")
    quiet("openssl", "x509", "-req", "-in", "server.csr", "-CA", "ca.pem", "-CAkey", "ca.key",
          "-CAcreateserial", "-days", "1", "-extfile", "extensions", "-out", "server.pem")
    # Chromium Linux NSS locations across releases. Both are in the throwaway home.
    for directory in [home / ".pki/nssdb", home / ".local/share/pki/nssdb"]:
        directory.mkdir(parents=True)
        db = "sql:" + str(directory)
        quiet("certutil", "-N", "-d", db, "--empty-password")
        quiet("certutil", "-A", "-d", db, "-n", "Acceptance CA", "-t", "C,,", "-i", "ca.pem")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("server.pem", "server.key")
    return context


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def run():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="dabbarha-browser-") as tmp, ExitStack() as stack:
        home = Path(tmp)
        os.chdir(home)
        base = {"HOME": tmp, "TMPDIR": tmp, "PATH": os.environ["PATH"]}
        api_env = dict(base, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1", APP_ENV="test",
                       DATABASE_URL="sqlite:///" + str(home / "test.db"), RATE_LIMIT_BACKEND="memory",
                       ADMIN_API_ENABLED="true", SESSION_AUTH_ENABLED="true", SESSION_LEGACY_ISSUANCE="false",
                       JWT_SECRET_KEY=secrets.token_urlsafe(48))
        for key in ("SESSION_RECEIPT_KEY", "ADMIN_TOTP_ENCRYPTION_KEY"):
            api_env[key] = base64.b64encode(secrets.token_bytes(32)).decode()
        os.environ.update(api_env)
        sys.path.insert(0, str(ROOT))
        from alembic import command
        from alembic.config import Config
        from app.core.admin_settings import AdminSettings
        from app.db.database import SessionLocal
        from app.models.user import User
        from app.services.admin_security import encrypt_totp_secret, generate_totp_secret

        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(config, "head")

        def start(args, env):
            proc = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stack.callback(stop, proc)
            return proc

        # The CI namespace has only loopback; fixed service ports are private to the job.
        api = "http://127.0.0.1:8000"
        proc = start([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                      "--port", "8000", "--no-access-log"], api_env)
        client = stack.enter_context(httpx.Client(base_url=api, trust_env=False, timeout=2))
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError("Disposable API startup failed")
            try:
                if client.get("/health").status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError("Disposable API readiness timed out")
        password = secrets.token_urlsafe(32)
        admin, ordinary = "admin@example.com", "ordinary@example.com"
        for email in (ordinary, admin):
            response = client.post("/auth/register", json=dict(name="Acceptance", email=email, password=password))
            response.raise_for_status()
        seed = generate_totp_secret()
        with SessionLocal.begin() as db:
            user = db.get(User, response.json()["id"])
            settings = AdminSettings.from_environ(api_env)
            user.admin_role = "superadmin"
            user.admin_totp_key_id = settings.totp_key_id
            user.admin_totp_nonce, user.admin_totp_ciphertext = encrypt_totp_secret(seed, user.id, settings)

        proxy = ThreadingHTTPServer(("127.0.0.1", 0), Proxy)
        stack.callback(proxy.server_close)
        proxy.socket = configure_tls(home).wrap_socket(proxy.socket, server_side=True)
        origin = f"https://127.0.0.1:{proxy.server_port}"
        bff = start(["node", str(HERE.parent / "server.mts")], dict(base, ADMIN_ORIGIN=origin, API_ORIGIN=api))
        for _ in range(100):
            if bff.poll() is not None:
                raise RuntimeError("Dashboard startup failed")
            try:
                with socket.create_connection(("127.0.0.1", 8787), timeout=.2):
                    break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError("Dashboard startup timed out")
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        stack.callback(proxy.shutdown)
        factor = base64.b64encode(base64.b32decode(seed + "=" * (-len(seed) % 8))).decode()
        subprocess.run(["node", str(HERE / "browser.mjs")], env=dict(base,
                       PLAYWRIGHT_BROWSERS_PATH=os.environ["PLAYWRIGHT_BROWSERS_PATH"]),
                       input=json.dumps(dict(origin=origin, admin=admin, ordinary=ordinary,
                                             password=password, factor=factor)), text=True, check=True, timeout=120)


if __name__ == "__main__":
    run()

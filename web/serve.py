"""웹 네일 AR용 로컬 HTTPS 서버.

폰 브라우저에서 폰 카메라(getUserMedia)를 쓰려면 보안 컨텍스트(HTTPS)가 필요하다.
이 스크립트는 자체서명 인증서를 자동 생성하고 web/ 폴더를 HTTPS로 서빙한다.
폰은 PC와 같은 Wi-Fi에서 출력된 https://<PC-IP>:8443 으로 접속(인증서 경고는 '고급→계속').

사용:  python web/serve.py        (web/ 폴더에서 실행해도 됨)
"""
from __future__ import annotations

import datetime
import http.server
import functools
import ipaddress
import os
import socket
import ssl
import sys

PORT = 8443
HERE = os.path.dirname(os.path.abspath(__file__))
# Certs live OUTSIDE the served web/ dir (this server does static file serving of HERE), so the
# private key can't be fetched via GET /key.pem. Moved to <root>/certs/ (2026-07-04 security fix).
_CERT_DIR = os.path.join(os.path.dirname(HERE), "certs")
CERT = os.path.join(_CERT_DIR, "cert.pem")
KEY = os.path.join(_CERT_DIR, "key.pem")


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ensure_cert(ip: str) -> None:
    """자체서명 인증서 생성(없을 때). SAN에 LAN IP/localhost 포함."""
    if os.path.isfile(CERT) and os.path.isfile(KEY):
        return
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        print("[serve] cryptography 필요: pip install cryptography")
        sys.exit(1)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "nail-ar-local")])
    san = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    try:
        san.append(x509.IPAddress(ipaddress.ip_address(ip)))
    except ValueError:
        pass
    now = datetime.datetime.utcnow()
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256()))
    with open(KEY, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[serve] 자체서명 인증서 생성: {CERT}")


def main():
    ip = lan_ip()
    ensure_cert(ip)

    # JS MIME 보장(ESM 모듈 로딩용) — 클래스 속성에 등록
    http.server.SimpleHTTPRequestHandler.extensions_map.update(
        {".js": "text/javascript", ".mjs": "text/javascript"})
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print("=" * 56)
    print("  폰 브라우저에서 아래 주소로 접속 (같은 Wi-Fi):")
    print(f"      https://{ip}:{PORT}")
    print("  인증서 경고가 뜨면 '고급 → 계속/방문'을 누르세요.")
    print("  PC 확인:  https://localhost:%d" % PORT)
    print("  종료: Ctrl+C")
    print("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] 종료")


if __name__ == "__main__":
    main()

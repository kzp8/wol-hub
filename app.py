#!/usr/bin/env python3
import os
import sys
import time
import json
import socket
import threading
import subprocess
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8096))
HOST_API = os.environ.get("HOST_API_URL", "http://10.0.0.1:8095")

DEVICES = {
    "pc": {
        "id": "pc",
        "name": "PC David (AORUS 15P XD)",
        "mac": "D8:5E:D3:82:1E:64",
        "ip": "192.168.68.58",
        "port_check": 58291,
        "desc": "Laptop Gaming & Workstation principal",
        "icon": "💻"
    },
    "pve": {
        "id": "pve",
        "name": "Proxmox Host (Lenovo PVE)",
        "mac": "98:FA:9B:1A:9E:25",
        "ip": "192.168.68.100",
        "port_check": 8006,
        "desc": "Servidor físico Proxmox VE",
        "icon": "🖥️"
    }
}

DEVICE_STATUS = {
    "pc": {"online": False, "latency_ms": None, "last_seen": None},
    "pve": {"online": True, "latency_ms": None, "last_seen": None}
}

EVENT_LOG = []
LOG_LOCK = threading.Lock()

def add_log(msg, level="info"):
    with LOG_LOCK:
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "msg": msg,
            "level": level
        }
        EVENT_LOG.insert(0, entry)
        if len(EVENT_LOG) > 50:
            EVENT_LOG.pop()

def check_device(ip, tcp_port=None):
    if tcp_port:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.35)
            t0 = time.time()
            if s.connect_ex((ip, tcp_port)) == 0:
                s.close()
                return True, int((time.time() - t0) * 1000)
            s.close()
        except:
            pass

    try:
        t0 = time.time()
        ret = subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ret.returncode == 0:
            return True, int((time.time() - t0) * 1000)
    except:
        pass

    return False, None

def monitor_loop():
    while True:
        for dev_id, dev in DEVICES.items():
            online, lat = check_device(dev["ip"], dev.get("port_check"))
            DEVICE_STATUS[dev_id]["online"] = online
            DEVICE_STATUS[dev_id]["latency_ms"] = lat
            if online:
                DEVICE_STATUS[dev_id]["last_seen"] = time.strftime("%H:%M:%S")
        time.sleep(4)

def send_magic_packet(mac_str, target_ip="192.168.68.58"):
    clean_mac = mac_str.replace(":", "").replace("-", "").replace(".", "").strip()
    if len(clean_mac) != 12:
        raise ValueError("MAC inválida (debe tener 12 dígitos hexadecimales)")

    total_sent = 0

    # 1. Disparar a través de la micro-API del host (L2 Broadcast físico en eth0)
    try:
        req = urllib.request.Request(
            f"{HOST_API}/pve-api/wol",
            data=json.dumps({"mac": mac_str, "ip": target_ip}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                total_sent += data.get("packets_sent", 18)
    except Exception as e:
        pass

    # 2. Enviar directamente desde el contenedor vía sockets UDP
    mac_bytes = bytes.fromhex(clean_mac)
    magic_pkt = b"\xff" * 6 + mac_bytes * 16

    destinations = [
        ("192.168.71.255", 9),
        ("255.255.255.255", 9),
        ("192.168.68.255", 9),
        ("192.168.71.255", 7),
        ("255.255.255.255", 7),
    ]
    if target_ip:
        destinations.append((target_ip, 9))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    for burst in range(3):
        for ip, port in destinations:
            try:
                sock.sendto(magic_pkt, (ip, port))
                total_sent += 1
            except:
                pass
        time.sleep(0.04)

    sock.close()
    return total_sent

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Homelab WoL Hub</title>
    <link rel="apple-touch-icon" href="https://img.icons8.com/fluency/192/power.png">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#11111b">
    <style>
        :root {
            --bg: #11111b;
            --surface0: #181825;
            --surface1: #1e1e2e;
            --surface2: #313244;
            --text: #cdd6f4;
            --subtext: #a6adc8;
            --blue: #89b4fa;
            --green: #a6e3a1;
            --yellow: #f9e2af;
            --red: #f38ba8;
            --mauve: #cba6f7;
            --sapphire: #74c7ec;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body {
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 24px 16px;
        }
        .container {
            width: 100%;
            max-width: 520px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        header {
            text-align: center;
            padding: 10px 0;
        }
        h1 {
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--blue), var(--mauve));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }
        header p {
            font-size: 13px;
            color: var(--subtext);
        }
        .card {
            background: var(--surface1);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
            background: linear-gradient(90deg, var(--blue), var(--mauve));
            opacity: 0.8;
        }
        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        .device-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .device-icon {
            font-size: 28px;
            background: var(--surface2);
            width: 48px;
            height: 48px;
            border-radius: 14px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .device-title {
            font-size: 16px;
            font-weight: 600;
            color: #fff;
        }
        .device-desc {
            font-size: 12px;
            color: var(--subtext);
            margin-top: 2px;
        }
        .badge {
            font-size: 11px;
            font-weight: 600;
            padding: 5px 10px;
            border-radius: 12px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .badge-online {
            background: rgba(166, 227, 161, 0.15);
            color: var(--green);
            border: 1px solid rgba(166, 227, 161, 0.3);
        }
        .badge-offline {
            background: rgba(249, 226, 175, 0.15);
            color: var(--yellow);
            border: 1px solid rgba(249, 226, 175, 0.3);
        }
        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        .badge-online .dot {
            box-shadow: 0 0 8px var(--green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 0.5; transform: scale(0.9); }
            50% { opacity: 1; transform: scale(1.1); }
            100% { opacity: 0.5; transform: scale(0.9); }
        }
        .details-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            background: var(--surface0);
            padding: 12px;
            border-radius: 12px;
            margin-bottom: 18px;
            font-size: 12px;
        }
        .detail-item {
            display: flex;
            flex-direction: column;
        }
        .detail-label {
            color: var(--subtext);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .detail-val {
            font-family: monospace;
            font-size: 12px;
            color: var(--text);
            margin-top: 2px;
        }
        .btn-wake {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 14px;
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: #fff;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 4px 15px rgba(2, 132, 199, 0.35);
        }
        .btn-wake:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(2, 132, 199, 0.5);
            background: linear-gradient(135deg, #0369a1, #1d4ed8);
        }
        .btn-wake:active {
            transform: scale(0.98);
        }
        .btn-wake.sending {
            background: linear-gradient(135deg, var(--green), #059669);
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);
        }
        .secondary-card {
            background: var(--surface0);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 14px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .btn-small {
            padding: 8px 14px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: var(--surface2);
            color: var(--text);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.15s;
        }
        .btn-small:hover {
            background: var(--blue);
            color: #111;
        }
        .log-section {
            background: var(--surface0);
            border-radius: 16px;
            padding: 14px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .log-header {
            font-size: 12px;
            font-weight: 600;
            color: var(--subtext);
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
        }
        .log-list {
            list-style: none;
            max-height: 120px;
            overflow-y: auto;
            font-size: 11px;
            font-family: monospace;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .log-item {
            color: var(--subtext);
            display: flex;
            gap: 6px;
        }
        .log-time { color: var(--blue); }
        .log-msg { color: var(--text); }
        .shortcuts-box {
            font-size: 12px;
            color: var(--subtext);
            background: rgba(137, 180, 250, 0.05);
            border: 1px dashed rgba(137, 180, 250, 0.2);
            border-radius: 12px;
            padding: 12px;
            line-height: 1.5;
        }
        .shortcuts-box code {
            background: rgba(0,0,0,0.3);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--blue);
            font-size: 11px;
        }
        .toast {
            position: fixed;
            bottom: 20px;
            background: #1e1e2e;
            color: #fff;
            padding: 12px 20px;
            border-radius: 14px;
            font-size: 13px;
            font-weight: 500;
            border: 1px solid var(--green);
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
            opacity: 0;
            transform: translateY(20px);
            transition: all 0.3s ease;
            pointer-events: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .toast.show {
            opacity: 1;
            transform: translateY(0);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Homelab WoL Hub</h1>
            <p>Disparador Wake-on-LAN Gigabit desde la red local</p>
        </header>

        <!-- Main Card: PC David -->
        <div class="card">
            <div class="card-header">
                <div class="device-info">
                    <div class="device-icon">💻</div>
                    <div>
                        <div class="device-title">PC David (AORUS 15P)</div>
                        <div class="device-desc">Laptop Gaming & Workstation</div>
                    </div>
                </div>
                <div id="pc-badge" class="badge badge-offline">
                    <span class="dot"></span>
                    <span id="pc-status-text">Comprobando...</span>
                </div>
            </div>

            <div class="details-grid">
                <div class="detail-item">
                    <span class="detail-label">Dirección MAC</span>
                    <span class="detail-val">D8:5E:D3:82:1E:64</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">IP Reservada</span>
                    <span class="detail-val">192.168.68.58</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Subnet Broadcast</span>
                    <span class="detail-val">192.168.71.255 (/22)</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Latencia LAN</span>
                    <span id="pc-lat" class="detail-val">-</span>
                </div>
            </div>

            <button id="btn-wake-pc" class="btn-wake" onclick="wakeDevice('pc')">
                <span id="btn-icon">⚡</span>
                <span id="btn-text">DESPERTAR PC</span>
            </button>
        </div>

        <!-- Secondary: Proxmox Host -->
        <div class="secondary-card">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 22px;">🖥️</span>
                <div>
                    <div style="font-size: 14px; font-weight: 600;">Proxmox PVE Host</div>
                    <div style="font-size: 11px; color: var(--subtext);">98:FA:9B:1A:9E:25 · 192.168.68.100</div>
                </div>
            </div>
            <button class="btn-small" onclick="wakeDevice('pve')">⚡ Wake</button>
        </div>

        <!-- Atajos / Siri API -->
        <div class="shortcuts-box">
            💡 <b>Disparo por API o Atajo de Siri:</b><br>
            Puedes encender el PC llamando por GET o POST a:<br>
            <code>https://wol.davidrus.dev/api/wake?target=pc</code>
        </div>

        <!-- Log en vivo -->
        <div class="log-section">
            <div class="log-header">
                <span>REGISTRO DE DISPAROS RECIENTES</span>
                <span style="cursor: pointer;" onclick="fetchStatus()">🔄 Refrescar</span>
            </div>
            <ul id="log-list" class="log-list">
                <li class="log-item"><span class="log-time">--:--:--</span><span class="log-msg">Iniciando monitor...</span></li>
            </ul>
        </div>
    </div>

    <div id="toast" class="toast">✨ ¡Paquete mágico enviado con éxito!</div>

    <script>
        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 3000);
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                const pc = data.devices.pc;
                const badge = document.getElementById('pc-badge');
                const statusText = document.getElementById('pc-status-text');
                const latText = document.getElementById('pc-lat');

                if (pc.online) {
                    badge.className = 'badge badge-online';
                    statusText.textContent = 'ONLINE';
                    latText.textContent = (pc.latency_ms !== null ? pc.latency_ms + ' ms' : 'Activo');
                } else {
                    badge.className = 'badge badge-offline';
                    statusText.textContent = 'SUSPENDIDO / OFF';
                    latText.textContent = (pc.last_seen ? 'Visto ' + pc.last_seen : 'Inactivo');
                }

                const logList = document.getElementById('log-list');
                if (data.logs && data.logs.length > 0) {
                    logList.innerHTML = data.logs.map(l =>
                        `<li class="log-item"><span class="log-time">[${l.time}]</span> <span class="log-msg">${l.msg}</span></li>`
                    ).join('');
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function wakeDevice(target) {
            const btn = document.getElementById('btn-wake-pc');
            const icon = document.getElementById('btn-icon');
            const text = document.getElementById('btn-text');

            if (target === 'pc') {
                btn.classList.add('sending');
                icon.textContent = '🚀';
                text.textContent = 'ENVIANDO RÁFAGAS...';
            }

            try {
                const res = await fetch('/api/wake?target=' + target, { method: 'POST' });
                const json = await res.json();
                if (json.ok) {
                    showToast('🚀 Paquetes mágicos emitidos (' + json.packets_sent + ' enviados)');
                } else {
                    showToast('❌ Error: ' + json.error);
                }
            } catch (err) {
                showToast('❌ Error conectando con el servidor');
            } finally {
                setTimeout(() => {
                    if (target === 'pc') {
                        btn.classList.remove('sending');
                        icon.textContent = '⚡';
                        text.textContent = 'DESPERTAR PC';
                    }
                    fetchStatus();
                }, 1000);
            }
        }

        setInterval(fetchStatus, 3500);
        fetchStatus();
    </script>
</body>
</html>
"""

class WoLRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
            return

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with LOG_LOCK:
                recent_logs = list(EVENT_LOG[:15])
            data = {
                "devices": {
                    "pc": {**DEVICES["pc"], **DEVICE_STATUS["pc"]},
                    "pve": {**DEVICES["pve"], **DEVICE_STATUS["pve"]}
                },
                "logs": recent_logs
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if path == "/api/wake":
            params = parse_qs(parsed.query)
            target = params.get("target", ["pc"])[0]
            self.handle_wake_action(target)
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/wake":
            params = parse_qs(parsed.query)
            target = params.get("target", ["pc"])[0]
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                try:
                    body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                    if "target" in body:
                        target = body["target"]
                except:
                    pass
            self.handle_wake_action(target)
            return

        self.send_error(404, "Not Found")

    def handle_wake_action(self, target):
        dev = DEVICES.get(target)
        if not dev:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Dispositivo no encontrado"}).encode("utf-8"))
            return

        client_ip = self.client_address[0]
        try:
            sent = send_magic_packet(dev["mac"], dev.get("ip"))
            msg = f"Disparo WoL a {dev['name']} ({dev['mac']}) [x{sent} pkts]"
            add_log(msg, "success")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "target": target,
                "device": dev["name"],
                "mac": dev["mac"],
                "packets_sent": sent,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }).encode("utf-8"))
        except Exception as e:
            add_log(f"Error WoL a {dev['name']}: {str(e)}", "error")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), WoLRequestHandler)
    print(f"WoL Server escuchando en http://0.0.0.0:{PORT}")
    add_log(f"Servidor WoL iniciado en puerto {PORT}", "info")

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    server.serve_forever()

if __name__ == "__main__":
    run_server()
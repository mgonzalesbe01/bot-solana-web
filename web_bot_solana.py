import sys
import time
import threading
import logging
import requests
import random
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- VERIFICACIÓN DE LIBRERÍAS ---
try:
    import ccxt
except ImportError:
    logger.error("⚠️ Error: CCXT no está instalado.")
    sys.exit(1)

# ================= CONFIGURACIÓN DEL BOT =================
PAR_MONEDA = 'SOL/USDT'
CAPITAL_TOTAL = 100.00
NUMERO_GRIDS = 6
RANGO_PORCENTAJE = 0.03
COMISION_SIMULADA = 0.001
# URL de Render para el stay_awake
APP_URL = "https://bot-solana-martin.onrender.com" 
# =========================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Inversión - SOL Bot 🤖</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #0b0e11; color: #eaeaea; font-family: 'Inter', sans-serif; }
        .card { background-color: #1e2329; border: none; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
        .stat-card { padding: 25px; text-align: center; border: 1px solid #2b3139; }
        .btn-start { background-color: #2ebd85; border: none; color: white; font-weight: 600; padding: 12px; transition: 0.3s; }
        .btn-start:hover:not(:disabled) { background-color: #26a373; transform: scale(1.02); }
        .btn-stop { background-color: #f6465d; border: none; color: white; font-weight: 600; padding: 12px; }
        .log-container { height: 400px; overflow-y: auto; background: #161a1e; border-radius: 8px; padding: 15px; font-family: 'Roboto Mono', monospace; font-size: 0.85rem; border: 1px solid #2b3139; }
        .text-white-bright { color: #ffffff !important; }
        .text-label { color: #d1d4dc !important; font-weight: 500; }
        .stat-main-value { font-size: 2.8rem; font-weight: 800; color: #ffffff !important; text-shadow: 0 2px 10px rgba(255,255,255,0.2); margin: 5px 0; }
        .text-profit { color: #2ebd85; font-weight: bold; }
        .text-loss { color: #f6465d; font-weight: bold; }
        .grid-line { border-left: 4px solid #474d57; padding-left: 10px; margin-bottom: 5px; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-thumb { background: #474d57; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="container py-4">
        <div class="row mb-4 align-items-center">
            <div class="col-md-8">
                <h2 class="mb-0 text-white-bright">🤖 Solana <span class="text-warning">Grid Bot</span></h2>
                <p class="text-label mb-0">Protección Anti-Bloqueo Activada</p>
            </div>
            <div class="col-md-4 text-md-end">
                <span id="status-badge" class="badge bg-secondary fs-6">Iniciando...</span>
            </div>
        </div>
        <div class="row">
            <div class="col-lg-4">
                <div class="card stat-card">
                    <small class="text-label text-uppercase small">Valor Total Cartera</small>
                    <div id="equity-val" class="stat-main-value">$0.00</div>
                    <div id="pnl-val" class="fs-5">$0.00 (0%)</div>
                </div>
                <div class="card p-3">
                    <h6 class="text-label mb-3 text-uppercase small fw-bold">Panel de Control</h6>
                    <div class="d-grid gap-2">
                        <button id="btn-start" onclick="startBot()" class="btn btn-start">ACTIVAR ALGORITMO</button>
                        <button id="btn-stop" onclick="stopBot()" class="btn btn-danger btn-stop" disabled>DETENER SISTEMA</button>
                    </div>
                </div>
                <div class="card p-3">
                    <h6 class="text-label mb-3 text-uppercase small fw-bold">Desglose de Fondos</h6>
                    <div class="d-flex justify-content-between mb-2">
                        <span class="text-label">Capital Inicial:</span>
                        <span class="text-white-bright fw-bold">$100.00</span>
                    </div>
                    <div class="d-flex justify-content-between mb-2">
                        <span class="text-label">Saldo USDT:</span>
                        <span id="usdt-bal" class="text-white-bright fw-bold">$0.00</span>
                    </div>
                    <div class="d-flex justify-content-between">
                        <span class="text-label">Saldo SOL:</span>
                        <span id="sol-bal" class="fw-bold text-warning">0.0000 SOL</span>
                    </div>
                </div>
            </div>
            <div class="col-lg-8">
                <div class="card p-3 h-100">
                    <div class="d-flex justify-content-between mb-3">
                        <h6 class="text-label mb-0 text-uppercase small fw-bold">Actividad del Algoritmo</h6>
                        <small id="last-update" class="text-label small">Update: --:--</small>
                    </div>
                    <div id="log-box" class="log-container">
                        <div class="text-secondary small">Listo para operar en la nube...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        function updateUI() {
            fetch('/status').then(res => res.json()).then(data => {
                document.getElementById('btn-start').disabled = data.running;
                document.getElementById('btn-stop').disabled = !data.running;
                const badge = document.getElementById('status-badge');
                badge.innerText = data.running ? "BOT ACTIVO" : "BOT EN PAUSA";
                badge.className = "badge fs-6 " + (data.running ? "bg-success" : "bg-danger");
                document.getElementById('equity-val').innerText = "$" + data.equity.toFixed(2);
                document.getElementById('usdt-bal').innerText = "$" + data.usdt.toFixed(2);
                document.getElementById('sol-bal').innerText = data.sol.toFixed(4) + " SOL";
                const pnl = data.pnl;
                const pnlPercent = (pnl / 100) * 100;
                const pnlEl = document.getElementById('pnl-val');
                pnlEl.innerText = (pnl >= 0 ? "+" : "") + "$" + pnl.toFixed(2) + " (" + pnlPercent.toFixed(2) + "%)";
                pnlEl.className = "fs-5 fw-bold " + (pnl >= 0 ? "text-profit" : "text-loss");
                const logBox = document.getElementById('log-box');
                logBox.innerHTML = data.logs.join("");
                logBox.scrollTop = logBox.scrollHeight;
                document.getElementById('last-update').innerText = "Update: " + new Date().toLocaleTimeString();
            }).catch(e => {
                const badge = document.getElementById('status-badge');
                badge.innerText = "RECONECTANDO...";
                badge.className = "badge bg-warning text-dark fs-6";
            });
        }
        function startBot() { fetch('/start', {method: 'POST'}); }
        function stopBot() { fetch('/stop', {method: 'POST'}); }
        setInterval(updateUI, 2000);
    </script>
</body>
</html>
"""

class GridBotEngine:
    def __init__(self):
        self.running = False
        self.logs = []
        # Lista de espejos de Binance para rotación
        self.mirrors = [
            "https://api.binance.com",
            "https://api1.binance.com",
            "https://api2.binance.com",
            "https://api3.binance.com"
        ]
        self.current_mirror_idx = 0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        self.usdt = CAPITAL_TOTAL
        self.sol = 0.0
        self.equity = CAPITAL_TOTAL
        self.grids = []

    def add_log(self, mensaje, tipo="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = "#848e9c"
        if tipo == "compra": color = "#2ebd85"
        if tipo == "venta": color = "#f0b90b"
        if tipo == "error": color = "#f6465d"
        entry = f"<div class='grid-line'><span style='color:#5e6673'>[{timestamp}]</span> <span style='color:{color}'>{mensaje}</span></div>"
        self.logs.append(entry)
        if len(self.logs) > 60: self.logs.pop(0)

    def get_market_price(self):
        """Intenta obtener el precio rotando entre diferentes servidores de Binance"""
        symbol = PAR_MONEDA.replace('/', '')
        
        # Intentamos con 3 espejos distintos si fallan
        for _ in range(3):
            base_url = self.mirrors[self.current_mirror_idx]
            url = f"{base_url}/api/v3/ticker/price?symbol={symbol}"
            
            try:
                response = requests.get(url, headers=self.headers, timeout=8)
                if response.status_code == 200:
                    return float(response.json()['price'])
                elif response.status_code == 429:
                    self.add_log("⚠️ Límite de IP alcanzado. Rotando servidor...", "error")
                else:
                    logger.error(f"Error {response.status_code} en {base_url}")
            except Exception as e:
                logger.error(f"Fallo en espejo {base_url}: {e}")
            
            # Rotar al siguiente espejo
            self.current_mirror_idx = (self.current_mirror_idx + 1) % len(self.mirrors)
            time.sleep(1)
            
        return None

    def setup_grids(self, precio):
        self.add_log(f"🏗️ Rejilla configurada en ${precio:.2f}")
        techo = precio * (1 + RANGO_PORCENTAJE)
        piso = precio * (1 - RANGO_PORCENTAJE)
        paso = (techo - piso) / NUMERO_GRIDS
        self.grids = []
        nivel = piso
        for i in range(NUMERO_GRIDS + 1):
            self.grids.append({'id': i, 'precio': nivel, 'comprado': False})
            nivel += paso

    def main_loop(self):
        self.add_log("🌐 Buscando puerta de enlace segura...")
        
        precio_inicial = self.get_market_price()
        
        if not precio_inicial:
            self.add_log("❌ Binance bloqueó todos los espejos. Esperando 30s...", "error")
            time.sleep(30)
            precio_inicial = self.get_market_price()
            if not precio_inicial:
                self.add_log("⚠️ Baneo de IP persistente en Render. Intenta reiniciar más tarde.", "error")
                self.running = False
                return
            
        self.setup_grids(precio_inicial)
        inversion_por_nivel = CAPITAL_TOTAL / NUMERO_GRIDS
        
        while self.running:
            try:
                precio_actual = self.get_market_price()
                if not precio_actual: 
                    time.sleep(10)
                    continue
                
                self.equity = self.usdt + (self.sol * precio_actual)
                
                for linea in self.grids:
                    if precio_actual < linea['precio'] and not linea['comprado']:
                        if self.usdt >= inversion_por_nivel:
                            self.usdt -= inversion_por_nivel
                            self.sol += (inversion_por_nivel / precio_actual) * (1 - COMISION_SIMULADA)
                            linea['comprado'] = True
                            self.add_log(f"🟢 COMPRA en Nivel {linea['id']} (${precio_actual:.2f})", "compra")
                            
                    elif linea['comprado'] and precio_actual > (linea['precio'] * 1.015):
                        cantidad_venta = inversion_por_nivel / linea['precio']
                        self.sol -= cantidad_venta
                        self.usdt += (cantidad_venta * precio_actual) * (1 - COMISION_SIMULADA)
                        linea['comprado'] = False
                        profit = (cantidad_venta * precio_actual) - inversion_por_nivel
                        self.add_log(f"🚀 VENTA en Nivel {linea['id']} | Profit: +${profit:.2f}", "venta")
                
                # Pausa más larga para evitar que Binance nos detecte por frecuencia
                time.sleep(random.uniform(4, 7))
                
            except Exception as e:
                logger.error(f"Error en loop: {e}")
                time.sleep(15)

app = Flask(__name__)
bot = GridBotEngine()

def stay_awake():
    while True:
        time.sleep(600)
        if APP_URL:
            try: requests.get(APP_URL + "/status")
            except: pass

@app.route('/')
def home(): return render_template_string(HTML_TEMPLATE)

@app.route('/start', methods=['POST'])
def start():
    if not bot.running:
        bot.running = True
        threading.Thread(target=bot.main_loop, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/stop', methods=['POST'])
def stop():
    bot.running = False
    return jsonify({"status": "ok"})

@app.route('/status')
def status():
    return jsonify({
        "running": bot.running,
        "logs": bot.logs,
        "usdt": bot.usdt,
        "sol": bot.sol,
        "equity": bot.equity,
        "pnl": bot.equity - CAPITAL_TOTAL
    })

if __name__ == '__main__':
    threading.Thread(target=stay_awake, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
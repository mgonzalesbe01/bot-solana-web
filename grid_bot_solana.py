import sys
import time
import threading
import logging
import requests # Necesario para el auto-ping
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- VERIFICACIÓN DE LIBRERÍAS ---
try:
    import ccxt
except ImportError:
    logger.error("⚠️ Error: CCXT no está instalado. Añádelo a requirements.txt")
    sys.exit(1)

# ================= CONFIGURACIÓN DEL BOT =================
PAR_MONEDA = 'SOL/USDT'
CAPITAL_TOTAL = 100.00
NUMERO_GRIDS = 6
RANGO_PORCENTAJE = 0.03
COMISION_SIMULADA = 0.001
APP_URL = "" # Aquí pondrás tu URL de Render una vez la tengas
# =========================================================

# --- INTERFAZ WEB (HTML/CSS/JS) ---
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
        .card { background-color: #1e2329; border: none; border-radius: 12px; margin-bottom: 20px; }
        .stat-card { padding: 20px; text-align: center; }
        .btn-start { background-color: #2ebd85; border: none; color: white; font-weight: 600; }
        .btn-stop { background-color: #f6465d; border: none; color: white; font-weight: 600; }
        .log-container { 
            height: 400px; 
            overflow-y: auto; 
            background: #161a1e; 
            border-radius: 8px; 
            padding: 15px; 
            font-family: 'Roboto Mono', monospace;
            font-size: 0.85rem;
            border: 1px solid #2b3139;
        }
        .text-profit { color: #2ebd85; }
        .text-loss { color: #f6465d; }
        .grid-line { border-left: 4px solid #474d57; padding-left: 10px; margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="container py-4">
        <div class="row mb-4 align-items-center">
            <div class="col-md-8">
                <h2 class="mb-0">🤖 Solana <span class="text-warning">Grid Bot</span></h2>
                <p class="text-secondary mb-0">Sistema de trading automático institucional</p>
            </div>
            <div class="col-md-4 text-md-end">
                <span id="status-badge" class="badge bg-secondary">Cargando...</span>
            </div>
        </div>

        <div class="row">
            <div class="col-lg-4">
                <div class="card stat-card">
                    <small class="text-secondary">VALOR TOTAL DE CARTERA</small>
                    <div id="equity-val" class="display-6 fw-bold mt-1">$0.00</div>
                    <div id="pnl-val" class="fs-5 fw-bold">$0.00 (0%)</div>
                </div>

                <div class="card p-3">
                    <h6 class="text-secondary mb-3">CONTROLES</h6>
                    <div class="d-grid gap-2">
                        <button id="btn-start" onclick="startBot()" class="btn btn-start">ACTIVAR ALGORITMO</button>
                        <button id="btn-stop" onclick="stopBot()" class="btn btn-stop" disabled>DETENER SISTEMA</button>
                    </div>
                </div>

                <div class="card p-3">
                    <h6 class="text-secondary mb-3">DESGLOSE DE ACTIVOS</h6>
                    <div class="d-flex justify-content-between mb-2">
                        <span>Saldo USDT:</span>
                        <span id="usdt-bal" class="fw-bold">$0.00</span>
                    </div>
                    <div class="d-flex justify-content-between">
                        <span>Saldo SOL:</span>
                        <span id="sol-bal" class="fw-bold text-warning">0.0000</span>
                    </div>
                </div>
            </div>

            <div class="col-lg-8">
                <div class="card p-3">
                    <div class="d-flex justify-content-between mb-3">
                        <h6 class="text-secondary mb-0">EJECUCIÓN EN TIEMPO REAL</h6>
                        <small id="last-update" class="text-secondary">Sincronizando...</small>
                    </div>
                    <div id="log-box" class="log-container">
                        <div class="text-secondary">Esperando señal del servidor...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        function updateUI() {
            fetch('/status')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('btn-start').disabled = data.running;
                    document.getElementById('btn-stop').disabled = !data.running;
                    const badge = document.getElementById('status-badge');
                    badge.innerText = data.running ? "SISTEMA ACTIVO" : "SISTEMA EN PAUSA";
                    badge.className = data.running ? "badge bg-success" : "badge bg-danger";
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
                    document.getElementById('last-update').innerText = "Último tick: " + new Date().toLocaleTimeString();
                });
        }
        function startBot() { fetch('/start', {method: 'POST'}); }
        function stopBot() { fetch('/stop', {method: 'POST'}); }
        setInterval(updateUI, 1500);
    </script>
</body>
</html>
"""

class GridBotEngine:
    def __init__(self):
        self.running = False
        self.logs = []
        self.exchange = ccxt.binance({'enableRateLimit': True})
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
        try:
            return float(self.exchange.fetch_ticker(PAR_MONEDA)['last'])
        except:
            return None

    def setup_grids(self, precio):
        self.add_log(f"Configurando rejilla en ${precio:.2f}...")
        techo = precio * (1 + RANGO_PORCENTAJE)
        piso = precio * (1 - RANGO_PORCENTAJE)
        paso = (techo - piso) / NUMERO_GRIDS
        self.grids = []
        nivel = piso
        for i in range(NUMERO_GRIDS + 1):
            self.grids.append({'id': i, 'precio': nivel, 'comprado': False})
            nivel += paso

    def main_loop(self):
        precio_inicial = self.get_market_price()
        if not precio_inicial:
            self.add_log("Error de conexión", "error")
            self.running = False
            return
        self.setup_grids(precio_inicial)
        inversion_por_nivel = CAPITAL_TOTAL / NUMERO_GRIDS
        while self.running:
            try:
                precio_actual = self.get_market_price()
                if not precio_actual: continue
                self.equity = self.usdt + (self.sol * precio_actual)
                for linea in self.grids:
                    if precio_actual < linea['precio'] and not linea['comprado']:
                        if self.usdt >= inversion_por_nivel:
                            cantidad = inversion_por_nivel / precio_actual
                            self.usdt -= inversion_por_nivel
                            self.sol += (cantidad * (1 - COMISION_SIMULADA))
                            linea['comprado'] = True
                            self.add_log(f"COMPRA Nivel {linea['id']} (${precio_actual:.2f})", "compra")
                    elif linea['comprado'] and precio_actual > (linea['precio'] * 1.015):
                        cantidad_venta = inversion_por_nivel / linea['precio']
                        valor_venta = cantidad_venta * precio_actual
                        self.sol -= cantidad_venta
                        self.usdt += (valor_venta * (1 - COMISION_SIMULADA))
                        linea['comprado'] = False
                        profit = valor_venta - inversion_por_nivel
                        self.add_log(f"VENTA exitosa. Profit: +${profit:.2f}", "venta")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(5)

app = Flask(__name__)
bot = GridBotEngine()

# --- FUNCIÓN PARA EVITAR QUE SE DUERMA ---
def stay_awake():
    """Realiza una petición a sí mismo cada 10 minutos"""
    while True:
        time.sleep(600) # 10 minutos
        if APP_URL:
            try:
                requests.get(APP_URL + "/status")
                logger.info("Keep-alive ping enviado.")
            except:
                pass

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
    # Iniciar hilo de auto-ping
    threading.Thread(target=stay_awake, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
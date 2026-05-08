#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClassicBallSortPuzzle — Web Interface para API de Recompensa (advClick)
=======================================================================
Flask app para hospedar na Render.
"""
from __future__ import annotations

from gevent import monkey
monkey.patch_all()

import base64
import hashlib
import json
import random
import time
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, render_template, request, jsonify, abort, make_response
from flask_socketio import SocketIO, emit
import requests as http_requests
import re

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

BASE_URL = "https://game.dengleigg.top"
PK_NO = 108002
SALT = "108002ppf6ggjixj0k17kmab4o5px2ee"
VER_NU = 3
DEFAULT_COUNTRY_CODE = "BRA"
DEFAULT_TEST_NUM = 0
DEFAULT_USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 9; SM-G960N Build/PQ3A.190605.07021633)"

# Ad IDs base para randomização
BASE_AD_IDS = ["b0f6577714a0sdt7", "c303h065ce7166dd"]

# Ad networks observadas
AD_NETWORKS = ["Unity Ads", "Google AdMob"]

# =============================================================================
# APP FLASK
# =============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ball-sort-secret-key-2025'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# =============================================================================
# ANTI-SCRAPING / ANTI-BOT MIDDLEWARE
# =============================================================================

# Known scraper/bot user-agent patterns
BLOCKED_BOTS = [
    'httrack', 'wget', 'curl', 'scrapy', 'python-requests', 'java',
    'libwww', 'lwp', 'urllib', 'httpunit', 'nutch', 'phpcrawl',
    'msnbot', 'dotbot', 'archive.org', 'saveweb', 'webzip',
    'teleport', 'webcopy', 'offline', 'mirror', 'grab', 'sitesucker',
    'cyotek', 'copier', 'collector', 'webripper', 'sitesnagger',
    'blackwidow', 'xaldon', 'zeus', 'webdownloader', 'backstreet',
]

@app.before_request
def block_scrapers():
    """Bloqueia scrapers, bots e ferramentas de download de sites."""
    ua = (request.headers.get('User-Agent', '') or '').lower()
    
    # Bloquear bots conhecidos
    for bot in BLOCKED_BOTS:
        if bot in ua:
            abort(403)
    
    # Bloquear se não tiver User-Agent
    if not ua or len(ua) < 10:
        abort(403)


@app.after_request
def add_security_headers(response):
    """Adiciona headers de segurança anti-scraping."""
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet, noimageindex'
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none';"
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'interest-cohort=()'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

# Armazenar sessões ativas
active_sessions: Dict[str, dict] = {}

# =============================================================================
# TRACKING DE GAIDS EM TEMPO REAL
# =============================================================================

# Mapeia socket_id -> lista de gaids
connected_clients: Dict[str, List[str]] = {}
# Conjunto de GAIDs ativos (com sessões rodando)
active_gaids: Dict[str, dict] = {}  # gaid -> {"connections": set(), "started_at": datetime, "sessions_running": int}


def get_all_unique_gaids() -> set:
    """Retorna todos os GAIDs únicos conectados."""
    gaids = set()
    for gaid_list in connected_clients.values():
        for g in gaid_list:
            if g:
                gaids.add(g)
    return gaids


def get_online_stats() -> dict:
    """Retorna estatísticas de usuários online."""
    unique_gaids = get_all_unique_gaids()
    running_gaids = set(g for g, info in active_gaids.items() if info.get('sessions_running', 0) > 0)
    return {
        'total_connections': len(connected_clients),
        'unique_gaids': len(unique_gaids),
        'gaids_running': len(running_gaids),
        'gaid_list': [{'gaid': g[:8] + '...', 'gaid_full': g, 'sessions': active_gaids.get(g, {}).get('sessions_running', 0)} for g in unique_gaids],
    }


def broadcast_stats():
    """Envia estatísticas atualizadas para todos os clientes."""
    stats = get_online_stats()
    socketio.emit('online_stats', stats)

# =============================================================================
# UTILITÁRIOS
# =============================================================================

def randomize_ad_id() -> str:
    """Gera um AD_ID randomizado baseado nos padrões observados."""
    base = random.choice(BASE_AD_IDS)
    # Randomiza alguns caracteres mantendo o padrão
    chars = list(base)
    # Randomiza 3-4 posições aleatórias
    positions = random.sample(range(len(chars)), random.randint(3, 5))
    for pos in positions:
        if chars[pos].isdigit():
            chars[pos] = str(random.randint(0, 9))
        elif chars[pos].isalpha():
            chars[pos] = random.choice('abcdefghijklmnopqrstuvwxyz')
    return ''.join(chars)


def md5_sign(source: str) -> str:
    """Calcula MD5 hex da string de origem."""
    return hashlib.md5(source.encode("utf-8")).hexdigest()


def make_order_id() -> str:
    """Gera orderId no formato: pkNo + '02' + YYYYMMDDHHMMSS + random(5 dígitos)"""
    now = datetime.now()
    time_str = now.strftime("%Y%m%d%H%M%S")
    rand = random.randint(10000, 99999)
    return f"{PK_NO}02{time_str}{rand}"


def make_pm(
    ltv: str,
    adv_type: str,
    ad_format: str = "reward",
    counter: int = 1,
    aid: Optional[str] = None,
) -> str:
    """Constrói o campo pm (base64 JSON) com informações do bid de anúncio."""
    if aid is None:
        aid = randomize_ad_id()
    
    ltv_float = float(ltv)
    rp = f"{ltv_float:.10f}"
    
    other_network = "Google AdMob" if adv_type == "Unity Ads" else "Unity Ads"
    other_format = "inter" if ad_format == "reward" else "reward"
    other_ltv = f"{random.uniform(0.000700, 0.001200):.6f}"
    
    pm_data = {
        "v": 1,
        "c": str(counter),
        "p": ltv,
        "rp": rp,
        "bc": 1,
        "pf": "max",
        "vt": adv_type,
        "aid": aid,
        "adf": ad_format,
        "bid": [
            {"pf": "max", "vt": other_network, "adf": other_format, "p": other_ltv},
            {"pf": "max", "vt": adv_type, "adf": ad_format, "p": ltv},
        ],
    }
    
    pm_json = json.dumps(pm_data, separators=(",", ":"), ensure_ascii=False)
    return base64.b64encode(pm_json.encode("utf-8")).decode("ascii")


def compute_adv_click_sign(
    pk_no: int,
    gaid: str,
    country_code: str,
    order_id: str,
    ltv: str,
    adv_type: str,
    test_num: int,
) -> str:
    """Calcula a assinatura para /ad/advClick."""
    source = f"{pk_no}||{gaid}||{country_code}||{order_id}||{ltv}||{adv_type}||{test_num}"
    return md5_sign(source + SALT)


# =============================================================================
# API FUNCTIONS
# =============================================================================

def api_post(endpoint: str, payload: dict, timeout: int = 20) -> dict:
    """Envia POST para a API e retorna a resposta JSON."""
    url = BASE_URL + endpoint
    headers = {
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    
    try:
        resp = http_requests.post(url, json=payload, headers=headers, timeout=timeout)
        return resp.json()
    except http_requests.exceptions.Timeout:
        return {"code": -1, "msg": "Timeout", "success": False}
    except Exception as e:
        return {"code": -1, "msg": str(e), "success": False}


def start_check(gaid: str, country_code: str = DEFAULT_COUNTRY_CODE) -> dict:
    """Login / StartCheck."""
    mob_id = "0000000000000"
    extra_info = base64.b64encode(
        json.dumps({"countryCode": country_code}).encode()
    ).decode()
    
    source = f"{PK_NO}||{gaid}||{mob_id}||{VER_NU}"
    sign = md5_sign(source + SALT)
    
    payload = {
        "pkNo": PK_NO,
        "gaid": gaid,
        "mobId": mob_id,
        "verNu": VER_NU,
        "extraInfo": extra_info,
        "sign": sign,
    }
    
    return api_post("/user/startCheck", payload)


def adv_click(
    gaid: str,
    ltv_min: float,
    ltv_max: float,
    adv_type: Optional[str] = None,
    ad_format: str = "reward",
    counter: int = 1,
    country_code: str = DEFAULT_COUNTRY_CODE,
) -> dict:
    """Envia recompensa de anúncio (advClick)."""
    ltv = f"{random.uniform(ltv_min, ltv_max):.6f}"
    if adv_type is None:
        adv_type = random.choice(AD_NETWORKS)
    
    order_id = make_order_id()
    pm = make_pm(ltv=ltv, adv_type=adv_type, ad_format=ad_format, counter=counter)
    
    sign = compute_adv_click_sign(
        pk_no=PK_NO,
        gaid=gaid,
        country_code=country_code,
        order_id=order_id,
        ltv=ltv,
        adv_type=adv_type,
        test_num=DEFAULT_TEST_NUM,
    )
    
    payload = {
        "pkNo": PK_NO,
        "gaid": gaid,
        "countryCode": country_code,
        "orderId": order_id,
        "ltv": ltv,
        "advType": adv_type,
        "testNum": DEFAULT_TEST_NUM,
        "pm": pm,
        "sign": sign,
    }
    
    return api_post("/ad/advClick", payload)


# =============================================================================
# SESSÃO DE REWARD
# =============================================================================

def run_reward_session(session_id: str, gaid: str, ltv_min: float, ltv_max: float, 
                       count: int, delay: float, session_num: int):
    """Executa uma sessão de rewards em background."""
    active_sessions[session_id] = {
        "status": "running",
        "total_coins": 0,
        "success_count": 0,
        "current": 0,
        "total": count,
        "session_num": session_num,
    }
    
    for i in range(count):
        if active_sessions.get(session_id, {}).get("status") == "stopped":
            socketio.emit('session_update', {
                'session_id': session_id,
                'session_num': session_num,
                'type': 'stopped',
                'message': f'Sessão {session_num} parada pelo usuário.',
            })
            break
        
        result = adv_click(
            gaid=gaid,
            ltv_min=ltv_min,
            ltv_max=ltv_max,
            counter=30 + i,
        )
        
        active_sessions[session_id]["current"] = i + 1
        
        if result.get("code") == 0:
            per_amount = result["data"]["perAmout"]
            toa_amount = result["data"]["toaAmout"]
            active_sessions[session_id]["total_coins"] += per_amount
            active_sessions[session_id]["success_count"] += 1
            
            socketio.emit('session_update', {
                'session_id': session_id,
                'session_num': session_num,
                'type': 'success',
                'current': i + 1,
                'total': count,
                'per_amount': per_amount,
                'toa_amount': toa_amount,
                'total_coins': active_sessions[session_id]["total_coins"],
                'ad_id': randomize_ad_id(),
                'message': f'[{i+1}/{count}] +{per_amount} moedas | Saldo: {toa_amount}',
            })
        else:
            msg = result.get("msg", "Unknown error")
            socketio.emit('session_update', {
                'session_id': session_id,
                'session_num': session_num,
                'type': 'error',
                'current': i + 1,
                'total': count,
                'message': f'[{i+1}/{count}] ERRO: {msg}',
            })
            if "limit" in msg.lower() or "restrict" in msg.lower():
                socketio.emit('session_update', {
                    'session_id': session_id,
                    'session_num': session_num,
                    'type': 'limit',
                    'message': 'Limite atingido. Sessão encerrada.',
                })
                break
        
        if i < count - 1 and delay > 0:
            time.sleep(delay)
    
    active_sessions[session_id]["status"] = "finished"
    
    # Decrementar sessions_running do GAID
    if gaid in active_gaids:
        active_gaids[gaid]['sessions_running'] = max(0, active_gaids[gaid]['sessions_running'] - 1)
        broadcast_stats()
    
    socketio.emit('session_update', {
        'session_id': session_id,
        'session_num': session_num,
        'type': 'finished',
        'total_coins': active_sessions[session_id]["total_coins"],
        'success_count': active_sessions[session_id]["success_count"],
        'message': f'Sessão {session_num} finalizada: {active_sessions[session_id]["success_count"]}/{count} sucesso, +{active_sessions[session_id]["total_coins"]} moedas',
    })


# =============================================================================
# ROTAS
# =============================================================================

@app.route('/robots.txt')
def robots():
    return app.send_static_file('robots.txt')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    gaid = data.get('gaid', '')
    if not gaid:
        return jsonify({"error": "GAID é obrigatório"}), 400
    
    result = start_check(gaid)
    return jsonify(result)


@app.route('/api/start', methods=['POST'])
def api_start():
    data = request.json
    gaid = data.get('gaid', '')
    ltv_min = float(data.get('ltv_min', 0.00120))
    ltv_max = float(data.get('ltv_max', 0.00230))
    count = int(data.get('count', 50))
    delay = float(data.get('delay', 10.0))
    sessions = int(data.get('sessions', 1))
    
    if not gaid:
        return jsonify({"error": "GAID é obrigatório"}), 400
    
    if sessions > 2:
        sessions = 2
    
    # Atualizar tracking de GAIDs
    if gaid not in active_gaids:
        active_gaids[gaid] = {'connections': set(), 'started_at': datetime.now(), 'sessions_running': 0}
    active_gaids[gaid]['sessions_running'] += sessions
    
    session_ids = []
    for s in range(sessions):
        session_id = str(uuid.uuid4())
        session_ids.append(session_id)
        thread = threading.Thread(
            target=run_reward_session,
            args=(session_id, gaid, ltv_min, ltv_max, count, delay, s + 1),
            daemon=True,
        )
        thread.start()
    
    broadcast_stats()
    return jsonify({"session_ids": session_ids, "message": f"{sessions} sessão(ões) iniciada(s)"})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    data = request.json
    session_id = data.get('session_id', '')
    if session_id in active_sessions:
        active_sessions[session_id]["status"] = "stopped"
        return jsonify({"message": "Sessão marcada para parar"})
    return jsonify({"error": "Sessão não encontrada"}), 404


@app.route('/api/stop_all', methods=['POST'])
def api_stop_all():
    for sid in active_sessions:
        if active_sessions[sid]["status"] == "running":
            active_sessions[sid]["status"] = "stopped"
    return jsonify({"message": "Todas as sessões marcadas para parar"})


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Retorna estatísticas de GAIDs online."""
    return jsonify(get_online_stats())


# =============================================================================
# SOCKET.IO EVENTS (tracking de conexões)
# =============================================================================

@socketio.on('connect')
def handle_connect():
    """Quando um cliente conecta via WebSocket."""
    connected_clients[request.sid] = []
    broadcast_stats()


@socketio.on('disconnect')
def handle_disconnect():
    """Quando um cliente desconecta."""
    old_gaids = connected_clients.pop(request.sid, [])
    for gaid in old_gaids:
        if gaid and gaid in active_gaids:
            active_gaids[gaid]['connections'].discard(request.sid)
            if not active_gaids[gaid]['connections'] and active_gaids[gaid]['sessions_running'] <= 0:
                del active_gaids[gaid]
    broadcast_stats()


@socketio.on('register_gaid')
def handle_register_gaid(data):
    """Quando um cliente registra seus GAIDs (pode ser múltiplos separados por vírgula)."""
    raw = data.get('gaid', '').strip()
    new_gaids = [g.strip() for g in raw.split(',') if g.strip()]
    
    # Remover GAIDs antigos desta conexão
    old_gaids = connected_clients.get(request.sid, [])
    for gaid in old_gaids:
        if gaid not in new_gaids and gaid in active_gaids:
            active_gaids[gaid]['connections'].discard(request.sid)
            if not active_gaids[gaid]['connections'] and active_gaids[gaid]['sessions_running'] <= 0:
                del active_gaids[gaid]
    
    # Registrar novos GAIDs
    connected_clients[request.sid] = new_gaids
    for gaid in new_gaids:
        if gaid not in active_gaids:
            active_gaids[gaid] = {'connections': set(), 'started_at': datetime.now(), 'sessions_running': 0}
        active_gaids[gaid]['connections'].add(request.sid)
    
    broadcast_stats()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=True)

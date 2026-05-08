#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClassicBallSortPuzzle — Web Interface para API de Recompensa (advClick)
=======================================================================
Flask app para hospedar na Render.
"""

from gevent import monkey
monkey.patch_all()

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import requests as http_requests

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

# Armazenar sessões ativas
active_sessions: Dict[str, dict] = {}

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


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=True)

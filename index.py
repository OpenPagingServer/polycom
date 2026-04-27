#!/usr/bin/env python3

import os
import sys
import time
import threading
import subprocess
import importlib.util
import requests
import pymysql
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_message_send():
    module_name = "polycom_message_send_runtime"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    module_path = BASE_DIR / "message_send.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


message_send = load_message_send()


def load_page_handler():
    module_path = BASE_DIR / "page_handler.py"
    spec = importlib.util.spec_from_file_location("polycom_page_handler", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


page_handler = load_page_handler()


def load_icon_server():
    module_path = BASE_DIR / "icon_server.py"
    spec = importlib.util.spec_from_file_location("polycom_icon_server", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


icon_server = load_icon_server()

ENV_PATH = BASE_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

core = None
running = False
thread = None
INTERVAL = 60

def init(core_obj):
    global core, running, thread
    core = core_obj
    running = True
    try:
        icon_server.start()
    except Exception as exc:
        log(f"polycom icon server error: {exc}")
    thread = threading.Thread(target=loop, daemon=True)
    thread.start()

def log(msg):
    if core and hasattr(core, "log"):
        core.log(msg)
    else:
        print(msg)

def db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
    )

def fetch_endpoints():
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ipv4, status FROM `endpoints-output-polycom-push`")
            return cur.fetchall()
    finally:
        conn.close()

def update_status(ipv4, status):
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE `endpoints-output-polycom-push` SET status=%s WHERE ipv4=%s",
                (status, ipv4),
            )
        conn.commit()
    finally:
        conn.close()

def ping_phone(ip):
    if not ip:
        return "Offline"

    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", "1000", ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return "Online" if result.returncode == 0 else "Offline"
    except Exception:
        return "Offline"

def loop():
    while running:
        try:
            endpoints = fetch_endpoints()
            for ip, status in endpoints:
                if status == "Unchecked":
                    continue

                result = ping_phone(ip)
                if result != status:
                    update_status(ip, result)
                    log(f"{ip} -> {result}")
        except Exception as e:
            log(f"polycom error: {e}")

        time.sleep(INTERVAL)

def shutdown():
    global running
    running = False
    try:
        icon_server.stop()
    except Exception:
        pass

def api_endpoint(command_string):
    message_send.handle_api(command_string)

def handle_dispatch(action, stream_id, msg_id, targets, metadata=None):
    if action == "prepare_livepage":
        page_handler.handle_dispatch(action, stream_id, msg_id, targets, metadata)
        return
    message_send.handle_dispatch(action, stream_id, msg_id, targets)

def receive_audio(chunk, stream_id):
    message_send.receive_audio(chunk, stream_id)

def end_stream(stream_id):
    message_send.end_stream(stream_id)

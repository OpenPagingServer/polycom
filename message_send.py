#!/usr/bin/env python3

import os
import queue
import random
import socket
import struct
import threading
import time
import urllib3
import xml.sax.saxutils as saxutils
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pymysql
import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent.parent / ".env"
load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
LOG_FILE = BASE_DIR / "polycom_module_debug.log"

IPC_PORT = 50000
FRAME_SIZE = 160
ALERT_PACKETS = 31
END_PACKETS = 12
ALERT_INTERVAL = 0.03
END_DELAY = 0.05
STREAM_IDLE_TIMEOUT = 3.0
CALLER_ID_MAX = 13
CODEC_G711U = 0x00
PUSH_AFTER_AUDIO_DELAY = float(os.getenv("POLYCOM_PUSH_AFTER_AUDIO_DELAY", "0.6"))
PRE_AUDIO_GRACE_SECONDS = 6.0
SILENCE_FRAME = b"\xff" * FRAME_SIZE

active_streams = {}
streams_lock = threading.Lock()
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
try:
    udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)
except OSError:
    pass


def debug_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
    )


def send_ready_signal(module_name, stream_id):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(("127.0.0.1", IPC_PORT))
        sock.sendall(f"READY {module_name} {stream_id}\n".encode("utf-8"))
        sock.recv(16)
        sock.close()
        debug_log(f"READY sent module={module_name} stream={stream_id}")
    except Exception as exc:
        debug_log(f"READY failed module={module_name} stream={stream_id} error={exc}")


def normalize_caller_id(value):
    raw = "" if value is None else str(value)
    ascii_bytes = raw.encode("ascii", errors="ignore")[:CALLER_ID_MAX]
    if len(ascii_bytes) < CALLER_ID_MAX:
        ascii_bytes += b"\x00"
    return ascii_bytes.ljust(CALLER_ID_MAX, b"\x00")


def build_common_header(op_code, channel, host_id, caller_id):
    return struct.pack("!BBIB13s", op_code, channel, host_id, CALLER_ID_MAX, caller_id)


def build_alert_packet(channel, host_id, caller_id):
    return build_common_header(0x0F, channel, host_id, caller_id)


def build_end_packet(channel, host_id, caller_id):
    return build_common_header(0xFF, channel, host_id, caller_id)


def build_transmit_packet(channel, host_id, caller_id, sample_count, current_frame, previous_frame=None):
    payload = bytearray()
    payload.extend(build_common_header(0x10, channel, host_id, caller_id))
    payload.extend(struct.pack("!BBI", CODEC_G711U, 0x00, sample_count))
    if previous_frame is not None:
        payload.extend(previous_frame)
    payload.extend(current_frame)
    return bytes(payload)


def derive_host_id(seed_value):
    if seed_value:
        cleaned = "".join(ch for ch in str(seed_value) if ch.isalnum())
        if len(cleaned) >= 8:
            try:
                return int(cleaned[-8:], 16)
            except ValueError:
                pass
    return random.randint(1, 0xFFFFFFFF)


def fetch_message(message_id):
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name, shortmessage, longmessage, type, color, icon FROM messages WHERE messageid=%s", (message_id,))
            return cur.fetchone()
    finally:
        conn.close()


def parse_targets(targets):
    target_info = {
        "ptt_ids": [],
        "push_ips": [],
        "all": False,
    }
    for target in targets:
        token = str(target).strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered == "all":
            target_info["all"] = True
            continue
        if lowered.startswith("ptt-"):
            value = token[4:].strip()
            if value and value not in target_info["ptt_ids"]:
                target_info["ptt_ids"].append(value)
            continue
        if lowered.startswith("push-"):
            value = token[5:].strip()
            if value and value not in target_info["push_ips"]:
                target_info["push_ips"].append(value)
    return target_info


def fetch_ptt_targets(target_info):
    conn = db()
    try:
        with conn.cursor() as cur:
            if target_info["all"]:
                cur.execute(
                    "SELECT id, ip, port, `group`, name "
                    "FROM `endpoints-output-polycom-ptt` "
                    "WHERE ip IS NOT NULL AND ip <> '' AND port IS NOT NULL AND `group` IS NOT NULL"
                )
                rows = cur.fetchall()
            elif target_info["ptt_ids"]:
                placeholders = ",".join(["%s"] * len(target_info["ptt_ids"]))
                cur.execute(
                    f"SELECT id, ip, port, `group`, name "
                    f"FROM `endpoints-output-polycom-ptt` "
                    f"WHERE id IN ({placeholders})",
                    tuple(target_info["ptt_ids"]),
                )
                rows = cur.fetchall()
            else:
                rows = []
    finally:
        conn.close()
    targets = []
    for row in rows:
        ip = row.get("ip")
        port = row.get("port")
        channel = row.get("group")
        if ip is None or port is None or channel is None:
            continue
        try:
            targets.append(
                {
                    "id": str(row.get("id")),
                    "ip": str(ip),
                    "port": int(port),
                    "channel": int(channel),
                    "name": row.get("name") or "",
                }
            )
        except (TypeError, ValueError):
            continue
    return targets


def fetch_push_targets(target_info):
    conn = db()
    try:
        with conn.cursor() as cur:
            if target_info["all"]:
                cur.execute(
                    "SELECT ipv4, status, username, password "
                    "FROM `endpoints-output-polycom-push` "
                    "WHERE ipv4 IS NOT NULL AND ipv4 <> ''"
                )
                rows = cur.fetchall()
            elif target_info["push_ips"]:
                placeholders = ",".join(["%s"] * len(target_info["push_ips"]))
                cur.execute(
                    f"SELECT ipv4, status, username, password "
                    f"FROM `endpoints-output-polycom-push` "
                    f"WHERE ipv4 IN ({placeholders})",
                    tuple(target_info["push_ips"]),
                )
                rows = cur.fetchall()
            else:
                rows = []
    finally:
        conn.close()
    return rows


def parse_hex_color(value, default="FFFFFF"):
    raw = ("" if value is None else str(value)).strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raw = default
    try:
        int(raw, 16)
    except ValueError:
        raw = default
    return raw.upper()


def pick_text_color(hex_color):
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    luminance = (0.299 * r) + (0.587 * g) + (0.114 * b)
    return "#111111" if luminance > 186 else "#FFFFFF"


def build_direct_push_xml(page_title, short_message, long_message, bg_color, priority="Critical"):
    safe_title = saxutils.escape("" if page_title is None else str(page_title))
    safe_short = saxutils.escape("" if short_message is None else str(short_message))
    safe_long = saxutils.escape("" if long_message is None else str(long_message)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")
    safe_priority = saxutils.escape("" if priority is None else str(priority))
    hex_color = parse_hex_color(bg_color)
    text_color = pick_text_color(hex_color)
    return (
        "<PolycomIPPhone>"
        f"<Data priority=\"{safe_priority}\">"
        f"<title>{safe_title}</title>"
        f"<body bgcolor=\"#{hex_color}\" text=\"{text_color}\">"
        f"<h1>{safe_short}</h1>{safe_long}"
        "</body>"
        "</Data>"
        "</PolycomIPPhone>"
    )


def local_ip_for_target(target_ip):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((target_ip, 9))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def build_icon_url(device_ip, icon_name):
    if not icon_name:
        return None
    local_ip = local_ip_for_target(device_ip)
    port = os.getenv("POLYCOM_ICON_PORT_ACTIVE") or os.getenv("POLYCOM_ICON_PORT") or "16976"
    return f"http://{local_ip}:{port}/icon?name={quote(str(icon_name))}"


def build_push_xml_for_device(device, page_title, short_message, long_message, bg_color, icon_name, priority="Critical"):
    safe_title = saxutils.escape("" if page_title is None else str(page_title))
    safe_short = saxutils.escape("" if short_message is None else str(short_message))
    safe_long = saxutils.escape("" if long_message is None else str(long_message)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")
    safe_priority = saxutils.escape("" if priority is None else str(priority))
    hex_color = parse_hex_color(bg_color)
    text_color = pick_text_color(hex_color)
    icon_url = build_icon_url(device.get("ipv4"), icon_name)
    icon_html = ""
    if icon_url:
        safe_icon_url = saxutils.escape(icon_url, {'"': "&quot;"})
        icon_html = f"<img src=\"{safe_icon_url}\" width=\"40\" height=\"40\" align=\"left\"/>"
    return (
        "<PolycomIPPhone>"
        f"<Data priority=\"{safe_priority}\">"
        f"<title>{safe_title}</title>"
        f"<body bgcolor=\"#{hex_color}\" text=\"{text_color}\">"
        f"{icon_html}<h1>{safe_short}</h1>{safe_long}"
        "</body>"
        "</Data>"
        "</PolycomIPPhone>"
    )


def push_to_device(device, xml_data, verify=False):
    ip = device.get("ipv4")
    username = device.get("username")
    password = device.get("password")
    if not ip or not username or not password:
        return False
    try:
        response = requests.post(
            f"https://{ip}/push",
            data=xml_data.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            auth=HTTPDigestAuth(username, password),
            timeout=5,
            verify=verify,
        )
        preview = (response.text or "")[:200].replace("\r", " ").replace("\n", " ")
        debug_log(f"PUSH {ip} status={response.status_code} body={preview}")
        return response.status_code == 200
    except requests.exceptions.RequestException as exc:
        debug_log(f"PUSH {ip} failed error={exc}")
        return False


def push_text_parallel(jobs):
    threads = []
    for device, xml_data in jobs:
        thread = threading.Thread(target=push_to_device, args=(device, xml_data), daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()


def delayed_push_text(jobs, delay_seconds):
    if not jobs:
        return
    def worker():
        debug_log(f"delayed_push_text sleeping delay={delay_seconds} devices={[device.get('ipv4') for device, _ in jobs]}")
        time.sleep(delay_seconds)
        push_text_parallel(jobs)
    threading.Thread(target=worker, daemon=True).start()


def send_udp_packet(packet, ip, port):
    try:
        udp_sock.sendto(packet, (ip, port))
    except OSError as exc:
        debug_log(f"send_udp_packet failed ip={ip} port={port} error={exc}")


def stream_sender(stream_id):
    with streams_lock:
        stream = active_streams.get(stream_id)
        if stream is None:
            return
        destinations = list(stream["destinations"])
        host_id = stream["host_id"]
        caller_id = stream["caller_id"]
        audio_queue = stream["queue"]
    debug_log(
        f"stream_sender start stream={stream_id} "
        f"destinations={[(dest['id'], dest['ip'], dest['port'], dest['channel']) for dest in destinations]}"
    )
    for _ in range(ALERT_PACKETS):
        for destination in destinations:
            send_udp_packet(
                build_alert_packet(destination["channel"], host_id, caller_id),
                destination["ip"],
                destination["port"],
            )
        time.sleep(ALERT_INTERVAL)
    previous_frame = None
    sample_count = 0
    while True:
        with streams_lock:
            stream = active_streams.get(stream_id)
            if stream is None:
                return
            queue_ref = stream["queue"]
            last_seen = stream["last_seen"]
            destinations = list(stream["destinations"])
            received_audio = stream.get("received_audio", False)
            pre_audio_until = stream.get("pre_audio_until", 0)
        try:
            frame = queue_ref.get(timeout=0.1)
        except queue.Empty:
            if not received_audio and time.time() < pre_audio_until:
                frame = SILENCE_FRAME
            else:
                if time.time() - last_seen > STREAM_IDLE_TIMEOUT:
                    break
                continue
        if frame is None:
            break
        for destination in destinations:
            packet = build_transmit_packet(
                destination["channel"],
                host_id,
                caller_id,
                sample_count,
                frame,
                previous_frame,
            )
            send_udp_packet(packet, destination["ip"], destination["port"])
        previous_frame = frame
        sample_count = (sample_count + FRAME_SIZE) % 4294967296
    time.sleep(END_DELAY)
    for _ in range(END_PACKETS):
        for destination in destinations:
            send_udp_packet(
                build_end_packet(destination["channel"], host_id, caller_id),
                destination["ip"],
                destination["port"],
            )
        time.sleep(ALERT_INTERVAL)
    with streams_lock:
        active_streams.pop(stream_id, None)
    debug_log(f"stream_sender end stream={stream_id} sample_count={sample_count}")


def ensure_stream(stream_id, message_name, ptt_targets):
    with streams_lock:
        stream = active_streams.get(stream_id)
        if stream is not None:
            stream["last_seen"] = time.time()
            stream["destinations"] = list(ptt_targets)
            debug_log(f"ensure_stream existing stream={stream_id}")
            return stream
        seed_value = ptt_targets[0]["id"] if ptt_targets else message_name
        caller_id = normalize_caller_id(message_name or "OpenPaging")
        host_id = derive_host_id(seed_value)
        stream = {
            "queue": queue.Queue(),
            "last_seen": time.time(),
            "host_id": host_id,
            "caller_id": caller_id,
            "destinations": list(ptt_targets),
            "received_audio": False,
            "pre_audio_until": time.time() + PRE_AUDIO_GRACE_SECONDS,
        }
        active_streams[stream_id] = stream
    debug_log(
        f"ensure_stream created stream={stream_id} caller={message_name} "
        f"ptt_targets={[(dest['id'], dest['ip'], dest['port'], dest['channel']) for dest in ptt_targets]}"
    )
    threading.Thread(target=stream_sender, args=(stream_id,), daemon=True).start()
    return stream


def handle_dispatch(action, stream_id, message_id, targets):
    normalized_targets = []
    for target in targets:
        token = str(target).strip()
        if token and token not in normalized_targets:
            normalized_targets.append(token)
    if not normalized_targets:
        if action == "prepare_audio":
            send_ready_signal("polycom", stream_id)
        return
    debug_log(f"handle_dispatch action={action} stream={stream_id} msg={message_id} targets={normalized_targets}")
    message = fetch_message(message_id)
    if not message:
        if action == "prepare_audio":
            send_ready_signal("polycom", stream_id)
        debug_log(f"message_not_found msg={message_id}")
        return
    target_info = parse_targets(normalized_targets)
    ptt_targets = fetch_ptt_targets(target_info)
    push_targets = [
        device
        for device in fetch_push_targets(target_info)
        if device.get("ipv4") and device.get("status") in ("Unchecked", "Online")
    ]
    msg_type = message.get("type", "text+audio")
    name = message.get("name", "")
    longmessage = message.get("longmessage", "")
    debug_log(
        f"ptt_targets={[(dest['id'], dest['ip'], dest['port'], dest['channel']) for dest in ptt_targets]} "
        f"push_targets={[(device.get('ipv4'), device.get('status')) for device in push_targets]} "
        f"msg_type={msg_type}"
    )
    shortmessage = message.get("shortmessage", "") or ""
    color = message.get("color", "") or ""
    icon = message.get("icon", "") or ""
    push_jobs = []
    for device in push_targets:
        push_jobs.append((device, build_push_xml_for_device(device, name, shortmessage, longmessage, color, icon)))
    if msg_type == "text" and push_jobs:
        push_text_parallel(push_jobs)
    elif msg_type == "text+audio" and action != "prepare_audio" and push_jobs:
        push_text_parallel(push_jobs)
    if msg_type not in ("audio", "text+audio"):
        if action == "prepare_audio":
            send_ready_signal("polycom", stream_id)
        return
    if action == "prepare_audio":
        if ptt_targets:
            ensure_stream(stream_id, name, ptt_targets)
        if msg_type == "text+audio" and push_jobs:
            delayed_push_text(push_jobs, PUSH_AFTER_AUDIO_DELAY)
        send_ready_signal("polycom", stream_id)


def handle_api(command_string):
    parts = str(command_string).strip().split()
    if len(parts) < 4:
        return
    handle_dispatch(parts[0], parts[2], parts[3], [parts[1]])


def receive_audio(chunk, stream_id):
    with streams_lock:
        stream = active_streams.get(stream_id)
        if stream is None:
            debug_log(f"receive_audio missing_stream stream={stream_id} bytes={len(chunk)}")
            return
        stream["last_seen"] = time.time()
        stream["received_audio"] = True
        queue_ref = stream["queue"]
    offset = 0
    while offset < len(chunk):
        frame = chunk[offset:offset + FRAME_SIZE]
        if len(frame) < FRAME_SIZE:
            frame = frame.ljust(FRAME_SIZE, b"\xff")
        queue_ref.put(frame)
        offset += FRAME_SIZE
    debug_log(f"receive_audio stream={stream_id} bytes={len(chunk)}")


def end_stream(stream_id):
    with streams_lock:
        stream = active_streams.get(stream_id)
        if stream is None:
            debug_log(f"end_stream missing stream={stream_id}")
            return
        stream["last_seen"] = 0
        queue_ref = stream["queue"]
    queue_ref.put(None)
    debug_log(f"end_stream stream={stream_id}")

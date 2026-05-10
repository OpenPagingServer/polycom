#!/usr/bin/env python3

import importlib
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEBUG = os.getenv("DEBUG", "").strip().lower() == "true"


def load_message_send():
    return importlib.import_module("polycom_message_send_runtime")


message_send = load_message_send()


def page_debug(message):
    if DEBUG:
        message_send.debug_log(f"page_handler {message}")


def handle_dispatch(action, stream_id, group_id, targets, metadata=None):
    page_debug(f"handle_dispatch_start action={action} stream={stream_id} group={group_id} targets={targets} metadata={metadata}")
    if action != "prepare_livepage":
        return
    normalized_targets = []
    for target in targets:
        token = str(target).strip()
        if token and token not in normalized_targets:
            normalized_targets.append(token)
    if not normalized_targets:
        page_debug(f"handle_dispatch_no_targets stream={stream_id}")
        message_send.send_ready_signal("polycom", stream_id)
        return
    target_info = message_send.parse_targets(normalized_targets)
    ptt_targets = message_send.fetch_ptt_targets(target_info)
    sender = ""
    if metadata and metadata.get("sender") is not None:
        sender = str(metadata.get("sender")).strip()
    page_debug(f"handle_dispatch_targets stream={stream_id} target_info={target_info} ptt_targets={ptt_targets} sender={sender!r}")
    if ptt_targets:
        message_send.ensure_stream(stream_id, sender or f"Live Page {group_id}", ptt_targets)
    page_debug(f"handle_dispatch_ready stream={stream_id}")
    message_send.send_ready_signal("polycom", stream_id)


def receive_audio(chunk, stream_id):
    message_send.receive_audio(chunk, stream_id)


def end_stream(stream_id):
    message_send.end_stream(stream_id)

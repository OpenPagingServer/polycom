#!/usr/bin/env python3

import importlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_message_send():
    return importlib.import_module("polycom_message_send_runtime")


message_send = load_message_send()


def handle_dispatch(action, stream_id, group_id, targets, metadata=None):
    if action != "prepare_livepage":
        return
    normalized_targets = []
    for target in targets:
        token = str(target).strip()
        if token and token not in normalized_targets:
            normalized_targets.append(token)
    if not normalized_targets:
        message_send.send_ready_signal("polycom", stream_id)
        return
    target_info = message_send.parse_targets(normalized_targets)
    ptt_targets = message_send.fetch_ptt_targets(target_info)
    sender = ""
    if metadata and metadata.get("sender") is not None:
        sender = str(metadata.get("sender")).strip()
    if ptt_targets:
        message_send.ensure_stream(stream_id, sender or f"Live Page {group_id}", ptt_targets)
    message_send.send_ready_signal("polycom", stream_id)


def receive_audio(chunk, stream_id):
    message_send.receive_audio(chunk, stream_id)


def end_stream(stream_id):
    message_send.end_stream(stream_id)

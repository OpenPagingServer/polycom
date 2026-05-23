import html


PUSH_TABLE = "endpoints-output-polycom-push"
PTT_TABLE = "endpoints-output-polycom-ptt"


def h(value):
    return html.escape("" if value is None else str(value), quote=True)


def forms():
    return {
        "push": {
            "label": "Polycom Push",
            "description": "Polycom VVX push message endpoint.",
        },
        "ptt": {
            "label": "Polycom PTT",
            "description": "Polycom multicast PTT group.",
        },
    }


def ensure_schema(conn_factory):
    conn = conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS `{PUSH_TABLE}` ("
                "`ipv4` VARCHAR(45) NOT NULL, "
                "`status` VARCHAR(32) NOT NULL DEFAULT 'Unchecked', "
                "`username` VARCHAR(255) NOT NULL DEFAULT '', "
                "`password` VARCHAR(255) NOT NULL DEFAULT '', "
                "PRIMARY KEY (`ipv4`), KEY `status_idx` (`status`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
            )
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS `{PTT_TABLE}` ("
                "`id` INT NOT NULL AUTO_INCREMENT, "
                "`name` VARCHAR(100) NOT NULL DEFAULT '', "
                "`ip` VARCHAR(45) NOT NULL DEFAULT '', "
                "`port` INT NOT NULL DEFAULT 0, "
                "`group` INT NOT NULL DEFAULT 1, "
                "PRIMARY KEY (`id`)"
                ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci"
            )
        conn.commit()
    finally:
        conn.close()


def query_one(conn_factory, sql, params=()):
    conn = conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def execute(conn_factory, sql, params=()):
    conn = conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def module_body(content):
    return (
        "<style>body{font-family:Tahoma,sans-serif;margin:0;padding:18px;color:#202124;background:#fff}.grid{display:grid;gap:12px}.row{display:grid;gap:6px}"
        "label{font-weight:500}.check{display:flex;align-items:center;gap:8px;font-weight:400}"
        ".control{padding:10px;border:1px solid #ddd;border-radius:4px;font:inherit}.button,button{background:#1976D2;color:#fff;border:0;border-radius:4px;padding:10px 14px;font:inherit;cursor:pointer}"
        ".danger{background:#c62828}.success{background:#e8f5e9;border:1px solid #a5d6a7;color:#1b5e20;padding:10px;border-radius:6px;margin-bottom:12px}"
        ".error{background:#ffebee;border:1px solid #ef9a9a;color:#b71c1c;padding:10px;border-radius:6px;margin-bottom:12px}"
        ".warn{background:#fff8e1;border:1px solid #ffe082;color:#5d4037;padding:12px;border-radius:6px;margin-bottom:12px}.meta{color:#5f6368;margin:0 0 14px}"
        "@media(prefers-color-scheme:dark){body{background:#1e1e1e;color:#e0e0e0}.control{background:#171717;border-color:#333;color:#eee}.button,button{background:#BB86FC;color:#000}.meta{color:#aaa}.warn{background:#352b10;border-color:#66511a;color:#ffe2a8}}</style>"
        + content
    )


def alert(message, error):
    out = ""
    if message:
        out += f'<div class="success">{h(message)}</div>'
    if error:
        out += f'<div class="error">{h(error)}</div>'
    return out


def validate_port(value):
    port = int(str(value or "0"))
    if port < 1 or port > 65535:
        raise ValueError("Port must be between 1 and 65535.")
    return port


def render_form(form_type, request, conn_factory, page, user):
    ensure_schema(conn_factory)
    if form_type not in forms():
        return page("Endpoint Form", module_body("<h1>Endpoint form not found</h1>"), "endpoints", user, status=404)
    message = ""
    error = ""
    values = {}
    if form_type == "push":
        values = {"ipv4": "", "username": "", "password": "", "unchecked": ""}
    elif form_type == "ptt":
        values = {"name": "", "ip": "", "port": "", "group": "1"}

    if request.method == "POST":
        try:
            for key in values:
                values[key] = str(request.form.get(key, values[key]) or "").strip()
            if form_type == "push":
                values["unchecked"] = "1" if request.form.get("unchecked") else ""
                if not values["ipv4"]:
                    raise ValueError("IPv4 address is required.")
                if query_one(conn_factory, f"SELECT ipv4 FROM `{PUSH_TABLE}` WHERE ipv4=%s", (values["ipv4"],)):
                    raise ValueError("That Polycom push endpoint already exists.")
                status = "Unchecked" if values["unchecked"] else "New"
                execute(
                    conn_factory,
                    f"INSERT INTO `{PUSH_TABLE}` (ipv4, status, username, password) VALUES (%s,%s,%s,%s)",
                    (values["ipv4"], status, values["username"], values["password"]),
                )
                message = "Polycom push endpoint added."
                values = {"ipv4": "", "username": "", "password": "", "unchecked": ""}
            else:
                if not all(values.get(k) for k in ("name", "ip", "port", "group")):
                    raise ValueError("Name, IP, port, and group are required.")
                port = validate_port(values["port"])
                group = int(values["group"])
                if group < 1 or group > 25:
                    raise ValueError("Group must be between 1 and 25.")
                execute(
                    conn_factory,
                    f"INSERT INTO `{PTT_TABLE}` (name, ip, port, `group`) VALUES (%s,%s,%s,%s)",
                    (values["name"], values["ip"], port, group),
                )
                message = "Polycom PTT endpoint added."
                values = {"name": "", "ip": "", "port": "", "group": "1"}
        except Exception as exc:
            error = str(exc)

    if form_type == "push":
        body = (
            f"{alert(message, error)}<form method='post' class='grid'>"
            f"<div class='row'><label>IPv4 Address</label><input class='control' name='ipv4' value='{h(values['ipv4'])}' required></div>"
            f"<div class='row'><label>Username</label><input class='control' name='username' value='{h(values['username'])}'></div>"
            f"<div class='row'><label>Password</label><input class='control' type='password' name='password' value='{h(values['password'])}'></div>"
            f"<label class='check'><input type='checkbox' name='unchecked' value='1' {'checked' if values.get('unchecked') else ''}> Do not check status</label>"
            "<button class='button' type='submit'>Add Polycom Push Endpoint</button></form>"
        )
    else:
        body = (
            f"{alert(message, error)}<form method='post' class='grid'>"
            f"<div class='row'><label>Name</label><input class='control' name='name' value='{h(values['name'])}' required></div>"
            f"<div class='row'><label>Multicast IP</label><input class='control' name='ip' value='{h(values['ip'])}' placeholder='224.0.1.116' required></div>"
            f"<div class='row'><label>Port</label><input class='control' type='number' name='port' min='1' max='65535' value='{h(values['port'])}' required></div>"
            f"<div class='row'><label>PTT Group</label><input class='control' type='number' name='group' min='1' max='25' value='{h(values['group'])}' required></div>"
            "<button class='button' type='submit'>Add Polycom PTT Endpoint</button></form>"
        )
    return page(forms()[form_type]["label"], module_body(body), "endpoints", user)


def render_action(action, endpoint_id, request, conn_factory, page, user):
    ensure_schema(conn_factory)
    message = ""
    error = ""
    row = None
    label = endpoint_id
    kind = "ptt" if str(endpoint_id).startswith("ptt-") else "push" if str(endpoint_id).startswith("push-") else ""
    try:
        if kind == "ptt":
            row_id = int(str(endpoint_id)[4:])
            row = query_one(conn_factory, f"SELECT id, name, ip, port, `group` FROM `{PTT_TABLE}` WHERE id=%s", (row_id,))
            if not row:
                raise ValueError("Endpoint not found.")
            label = f"{row.get('name') or 'Polycom PTT'} ({row.get('ip')}:{row.get('port')})"
            if request.method == "POST":
                if action == "delete":
                    execute(conn_factory, f"DELETE FROM `{PTT_TABLE}` WHERE id=%s", (row_id,))
                    return page("Endpoint Deleted", module_body("<script>window.top.location.href='/admin/manage-endpoints'</script><div class='success'>Polycom PTT endpoint deleted.</div>"), "endpoints", user)
                values = {key: str(request.form.get(key, "") or "").strip() for key in ("name", "ip", "port", "group")}
                port = validate_port(values["port"])
                group = int(values["group"])
                if group < 1 or group > 25:
                    raise ValueError("Group must be between 1 and 25.")
                execute(conn_factory, f"UPDATE `{PTT_TABLE}` SET name=%s, ip=%s, port=%s, `group`=%s WHERE id=%s", (values["name"], values["ip"], port, group, row_id))
                return page("Endpoint Saved", module_body("<script>window.top.location.href='/admin/manage-endpoints'</script><div class='success'>Polycom PTT endpoint updated.</div>"), "endpoints", user)
        elif kind == "push":
            ipv4 = str(endpoint_id)[5:]
            lookup = str(request.form.get("_lookup_ipv4", ipv4) or "").strip()
            row = query_one(conn_factory, f"SELECT ipv4, status, username, password FROM `{PUSH_TABLE}` WHERE ipv4=%s", (lookup,))
            if not row:
                raise ValueError("Endpoint not found.")
            label = f"{row.get('username') or 'Polycom Push'} ({row.get('ipv4')})"
            if request.method == "POST":
                if action == "delete":
                    execute(conn_factory, f"DELETE FROM `{PUSH_TABLE}` WHERE ipv4=%s", (row["ipv4"],))
                    return page("Endpoint Deleted", module_body("<script>window.top.location.href='/admin/manage-endpoints'</script><div class='success'>Polycom push endpoint deleted.</div>"), "endpoints", user)
                new_ipv4 = str(request.form.get("ipv4", "") or "").strip()
                username = str(request.form.get("username", "") or "").strip()
                password = str(request.form.get("password", "") or "").strip()
                if not new_ipv4:
                    raise ValueError("IPv4 address is required.")
                duplicate = query_one(conn_factory, f"SELECT ipv4 FROM `{PUSH_TABLE}` WHERE ipv4=%s AND ipv4<>%s", (new_ipv4, row["ipv4"]))
                if duplicate:
                    raise ValueError("That Polycom push endpoint already exists.")
                execute(conn_factory, f"UPDATE `{PUSH_TABLE}` SET ipv4=%s, username=%s, password=%s WHERE ipv4=%s", (new_ipv4, username, password, row["ipv4"]))
                return page("Endpoint Saved", module_body("<script>window.top.location.href='/admin/manage-endpoints'</script><div class='success'>Polycom push endpoint updated.</div>"), "endpoints", user)
        else:
            raise ValueError("Unknown Polycom endpoint type.")
    except Exception as exc:
        error = str(exc)

    if action == "delete":
        body = f"{alert(message, error)}"
        if row:
            body += f"<div class='warn'>Delete {h(label)}?</div><form method='post'><button class='button danger' type='submit'>Delete Endpoint</button></form>"
        return page("Delete Polycom Endpoint", module_body(body), "endpoints", user)

    if not row:
        return page("Edit Polycom Endpoint", module_body(alert(message, error)), "endpoints", user)
    if kind == "ptt":
        body = (
            f"{alert(message, error)}<form method='post' class='grid'>"
            f"<div class='row'><label>Name</label><input class='control' name='name' value='{h(row.get('name'))}' required></div>"
            f"<div class='row'><label>Multicast IP</label><input class='control' name='ip' value='{h(row.get('ip'))}' required></div>"
            f"<div class='row'><label>Port</label><input class='control' type='number' name='port' min='1' max='65535' value='{h(row.get('port'))}' required></div>"
            f"<div class='row'><label>PTT Group</label><input class='control' type='number' name='group' min='1' max='25' value='{h(row.get('group'))}' required></div>"
            "<button class='button' type='submit'>Save Polycom PTT Endpoint</button></form>"
        )
    else:
        body = (
            f"{alert(message, error)}<p class='meta'>Current status: {h(row.get('status'))}</p><form method='post' class='grid'>"
            f"<input type='hidden' name='_lookup_ipv4' value='{h(row.get('ipv4'))}'>"
            f"<div class='row'><label>IPv4 Address</label><input class='control' name='ipv4' value='{h(row.get('ipv4'))}' required></div>"
            f"<div class='row'><label>Username</label><input class='control' name='username' value='{h(row.get('username'))}'></div>"
            f"<div class='row'><label>Password</label><input class='control' type='password' name='password' value='{h(row.get('password'))}'></div>"
            "<button class='button' type='submit'>Save Polycom Push Endpoint</button></form>"
        )
    return page("Edit Polycom Endpoint", module_body(body), "endpoints", user)


def render_settings(request, conn_factory, page, user):
    return page("Polycom Settings", module_body("<h1>Polycom Settings</h1><p>No additional settings are required for this module.</p>"), "endpoints", user)

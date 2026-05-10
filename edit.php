<?php
function polycom_endpoint_h($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

$message = '';
$error = '';
$kind = '';
$row = null;

try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS `endpoints-output-polycom-push` (`ipv4` VARCHAR(45) NOT NULL, `status` ENUM('New', 'Unchecked', 'Offline', 'Online') NOT NULL DEFAULT 'Unchecked', `username` VARCHAR(255) NOT NULL DEFAULT '', `password` VARCHAR(255) NOT NULL DEFAULT '', PRIMARY KEY (`ipv4`), KEY `status_idx` (`status`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS `endpoints-output-polycom-ptt` (`id` INT NOT NULL AUTO_INCREMENT, `name` VARCHAR(100) NOT NULL DEFAULT '', `ip` VARCHAR(45) NOT NULL DEFAULT '', `port` INT NOT NULL DEFAULT 0, `group` INT NOT NULL DEFAULT 1, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci");

    if (strpos($endpointId, 'ptt-') === 0) {
        $kind = 'ptt';
        $id = (int)substr($endpointId, strlen('ptt-'));
        if ($id < 1) {
            throw new RuntimeException('Invalid Polycom PTT endpoint.');
        }
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            $values = [
                'name' => trim((string)($_POST['name'] ?? '')),
                'ip' => trim((string)($_POST['ip'] ?? '')),
                'port' => trim((string)($_POST['port'] ?? '')),
                'group' => trim((string)($_POST['group'] ?? '')),
            ];
            if ($values['name'] === '' || $values['ip'] === '' || $values['port'] === '' || $values['group'] === '') {
                throw new RuntimeException('Name, IP, port, and group are required.');
            }
            $port = (int)$values['port'];
            $group = (int)$values['group'];
            if ($port < 1 || $port > 65535) {
                throw new RuntimeException('Port must be between 1 and 65535.');
            }
            if ($group < 1 || $group > 25) {
                throw new RuntimeException('Group must be between 1 and 25.');
            }
            $stmt = $pdo->prepare("UPDATE `endpoints-output-polycom-ptt` SET `name` = :name, `ip` = :ip, `port` = :port, `group` = :group WHERE `id` = :id");
            $stmt->execute(['name' => $values['name'], 'ip' => $values['ip'], 'port' => $port, 'group' => $group, 'id' => $id]);
            $message = 'Polycom PTT endpoint updated.';
        }
        $stmt = $pdo->prepare("SELECT `id`, `name`, `ip`, `port`, `group` FROM `endpoints-output-polycom-ptt` WHERE `id` = :id");
        $stmt->execute(['id' => $id]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
    } elseif (strpos($endpointId, 'push-') === 0) {
        $kind = 'push';
        $oldIpv4 = trim((string)($_POST['_lookup_ipv4'] ?? substr($endpointId, strlen('push-'))));
        $stmt = $pdo->prepare("SELECT `ipv4`, `status`, `username`, `password` FROM `endpoints-output-polycom-push` WHERE `ipv4` = :ipv4");
        $stmt->execute(['ipv4' => $oldIpv4]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row && $_SERVER['REQUEST_METHOD'] === 'POST') {
            $values = [
                'ipv4' => trim((string)($_POST['ipv4'] ?? '')),
                'username' => trim((string)($_POST['username'] ?? '')),
                'password' => trim((string)($_POST['password'] ?? '')),
            ];
            if ($values['ipv4'] === '') {
                throw new RuntimeException('IPv4 address is required.');
            }
            $stmt = $pdo->prepare("SELECT COUNT(*) FROM `endpoints-output-polycom-push` WHERE `ipv4` = :ipv4 AND `ipv4` <> :oldipv4");
            $stmt->execute(['ipv4' => $values['ipv4'], 'oldipv4' => $row['ipv4']]);
            if ((int)$stmt->fetchColumn() > 0) {
                throw new RuntimeException('That Polycom push endpoint already exists.');
            }
            $stmt = $pdo->prepare("UPDATE `endpoints-output-polycom-push` SET `ipv4` = :ipv4, `username` = :username, `password` = :password WHERE `ipv4` = :oldipv4");
            $stmt->execute(['ipv4' => $values['ipv4'], 'username' => $values['username'], 'password' => $values['password'], 'oldipv4' => $row['ipv4']]);
            $message = 'Polycom push endpoint updated.';
            $stmt = $pdo->prepare("SELECT `ipv4`, `status`, `username`, `password` FROM `endpoints-output-polycom-push` WHERE `ipv4` = :ipv4");
            $stmt->execute(['ipv4' => $values['ipv4']]);
            $row = $stmt->fetch(PDO::FETCH_ASSOC);
        }
    } else {
        throw new RuntimeException('Unknown Polycom endpoint type.');
    }

    if (!$row) {
        throw new RuntimeException('Endpoint not found.');
    }
} catch (Throwable $exc) {
    $error = $exc->getMessage();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:Tahoma,sans-serif;margin:0;padding:18px;color:#202124;background:#fff}.grid{display:grid;gap:12px}.row{display:grid;gap:6px}label{font-weight:500}.control{padding:10px;border:1px solid #ddd;border-radius:4px;font:inherit}.button{background:#1976D2;color:#fff;border:0;border-radius:4px;padding:10px 14px;font:inherit;cursor:pointer}.success{background:#E8F5E9;border:1px solid #A5D6A7;color:#1B5E20;padding:10px;border-radius:6px;margin-bottom:12px}.error{background:#FFEBEE;border:1px solid #EF9A9A;color:#B71C1C;padding:10px;border-radius:6px;margin-bottom:12px}.meta{color:#5f6368;margin:0 0 14px}@media(prefers-color-scheme:dark){body{background:#1e1e1e;color:#e0e0e0}.control{background:#171717;border-color:#333;color:#eee}.button{background:#BB86FC;color:#000}.meta{color:#aaa}}
</style>
</head>
<body>
<?php if ($message): ?><div class="success"><?= polycom_endpoint_h($message) ?></div><?php endif; ?>
<?php if ($error): ?><div class="error"><?= polycom_endpoint_h($error) ?></div><?php endif; ?>
<?php if ($row && $kind === 'ptt'): ?>
    <form method="post" class="grid">
        <div class="row"><label>Name</label><input class="control" name="name" value="<?= polycom_endpoint_h($row['name'] ?? '') ?>" required></div>
        <div class="row"><label>Multicast IP</label><input class="control" name="ip" value="<?= polycom_endpoint_h($row['ip'] ?? '') ?>" required></div>
        <div class="row"><label>Port</label><input class="control" type="number" name="port" min="1" max="65535" value="<?= polycom_endpoint_h($row['port'] ?? '') ?>" required></div>
        <div class="row"><label>PTT Group</label><input class="control" type="number" name="group" min="1" max="25" value="<?= polycom_endpoint_h($row['group'] ?? '') ?>" required></div>
        <button class="button" type="submit">Save Polycom PTT Endpoint</button>
    </form>
<?php elseif ($row && $kind === 'push'): ?>
    <p class="meta">Current status: <?= polycom_endpoint_h($row['status'] ?? '') ?></p>
    <form method="post" class="grid">
        <input type="hidden" name="_lookup_ipv4" value="<?= polycom_endpoint_h($row['ipv4'] ?? '') ?>">
        <div class="row"><label>IPv4 Address</label><input class="control" name="ipv4" value="<?= polycom_endpoint_h($row['ipv4'] ?? '') ?>" required></div>
        <div class="row"><label>Username</label><input class="control" name="username" value="<?= polycom_endpoint_h($row['username'] ?? '') ?>"></div>
        <div class="row"><label>Password</label><input class="control" type="password" name="password" value="<?= polycom_endpoint_h($row['password'] ?? '') ?>"></div>
        <button class="button" type="submit">Save Polycom Push Endpoint</button>
    </form>
<?php endif; ?>
</body>
</html>

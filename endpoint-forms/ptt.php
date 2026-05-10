<?php
function ef_h($value) { return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8'); }
$message = '';
$error = '';
$values = ['name' => '', 'ip' => '', 'port' => '', 'group' => '1'];
try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS `endpoints-output-polycom-ptt` (`id` INT NOT NULL AUTO_INCREMENT, `name` VARCHAR(100) NOT NULL DEFAULT '', `ip` VARCHAR(45) NOT NULL DEFAULT '', `port` INT NOT NULL DEFAULT 0, `group` INT NOT NULL DEFAULT 1, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci");
    if ($_SERVER['REQUEST_METHOD'] === 'POST') {
        foreach ($values as $key => $_default) {
            $values[$key] = trim((string)($_POST[$key] ?? $_default));
        }
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
        $stmt = $pdo->prepare("INSERT INTO `endpoints-output-polycom-ptt` (`name`, `ip`, `port`, `group`) VALUES (:name, :ip, :port, :group)");
        $stmt->execute(['name' => $values['name'], 'ip' => $values['ip'], 'port' => $port, 'group' => $group]);
        $message = 'Polycom PTT endpoint added.';
        $values = ['name' => '', 'ip' => '', 'port' => '', 'group' => '1'];
    }
} catch (Throwable $exc) {
    $error = $exc->getMessage();
}
?>
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:Tahoma,sans-serif;margin:0;padding:18px;color:#202124;background:#fff}.grid{display:grid;gap:12px}.row{display:grid;gap:6px}label{font-weight:500}.control{padding:10px;border:1px solid #ddd;border-radius:4px;font:inherit}.button{background:#1976D2;color:#fff;border:0;border-radius:4px;padding:10px 14px;font:inherit;cursor:pointer}.success{background:#E8F5E9;border:1px solid #A5D6A7;color:#1B5E20;padding:10px;border-radius:6px;margin-bottom:12px}.error{background:#FFEBEE;border:1px solid #EF9A9A;color:#B71C1C;padding:10px;border-radius:6px;margin-bottom:12px}@media(prefers-color-scheme:dark){body{background:#1e1e1e;color:#e0e0e0}.control{background:#171717;border-color:#333;color:#eee}.button{background:#BB86FC;color:#000}}</style></head><body>
<?php if ($message): ?><div class="success"><?= ef_h($message) ?></div><?php endif; ?><?php if ($error): ?><div class="error"><?= ef_h($error) ?></div><?php endif; ?>
<form method="post" class="grid"><div class="row"><label>Name</label><input class="control" name="name" value="<?= ef_h($values['name']) ?>" required></div><div class="row"><label>Multicast IP</label><input class="control" name="ip" value="<?= ef_h($values['ip']) ?>" placeholder="224.0.1.116" required></div><div class="row"><label>Port</label><input class="control" type="number" name="port" min="1" max="65535" value="<?= ef_h($values['port']) ?>" required></div><div class="row"><label>PTT Group</label><input class="control" type="number" name="group" min="1" max="25" value="<?= ef_h($values['group']) ?>" required></div><button class="button" type="submit">Add Polycom PTT Endpoint</button></form>
</body></html>

<?php
function polycom_endpoint_delete_h($value) {
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

$message = '';
$error = '';
$row = null;
$label = $endpointId;

try {
    $pdo->exec("CREATE TABLE IF NOT EXISTS `endpoints-output-polycom-push` (`ipv4` VARCHAR(45) NOT NULL, `status` ENUM('New', 'Unchecked', 'Offline', 'Online') NOT NULL DEFAULT 'Unchecked', `username` VARCHAR(255) NOT NULL DEFAULT '', `password` VARCHAR(255) NOT NULL DEFAULT '', PRIMARY KEY (`ipv4`), KEY `status_idx` (`status`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci");
    $pdo->exec("CREATE TABLE IF NOT EXISTS `endpoints-output-polycom-ptt` (`id` INT NOT NULL AUTO_INCREMENT, `name` VARCHAR(100) NOT NULL DEFAULT '', `ip` VARCHAR(45) NOT NULL DEFAULT '', `port` INT NOT NULL DEFAULT 0, `group` INT NOT NULL DEFAULT 1, PRIMARY KEY (`id`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci");

    if (strpos($endpointId, 'ptt-') === 0) {
        $id = (int)substr($endpointId, strlen('ptt-'));
        $stmt = $pdo->prepare("SELECT `id`, `name`, `ip`, `port`, `group` FROM `endpoints-output-polycom-ptt` WHERE `id` = :id");
        $stmt->execute(['id' => $id]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row) {
            $label = ($row['name'] ?: 'Polycom PTT') . ' (' . $row['ip'] . ':' . $row['port'] . ')';
        }
        if ($row && $_SERVER['REQUEST_METHOD'] === 'POST') {
            $stmt = $pdo->prepare("DELETE FROM `endpoints-output-polycom-ptt` WHERE `id` = :id");
            $stmt->execute(['id' => $id]);
            $message = 'Polycom PTT endpoint deleted.';
            $row = null;
        }
    } elseif (strpos($endpointId, 'push-') === 0) {
        $ipv4 = substr($endpointId, strlen('push-'));
        $stmt = $pdo->prepare("SELECT `ipv4`, `username` FROM `endpoints-output-polycom-push` WHERE `ipv4` = :ipv4");
        $stmt->execute(['ipv4' => $ipv4]);
        $row = $stmt->fetch(PDO::FETCH_ASSOC);
        if ($row) {
            $label = ($row['username'] ?: 'Polycom Push') . ' (' . $row['ipv4'] . ')';
        }
        if ($row && $_SERVER['REQUEST_METHOD'] === 'POST') {
            $stmt = $pdo->prepare("DELETE FROM `endpoints-output-polycom-push` WHERE `ipv4` = :ipv4");
            $stmt->execute(['ipv4' => $row['ipv4']]);
            $message = 'Polycom push endpoint deleted.';
            $row = null;
        }
    } else {
        throw new RuntimeException('Unknown Polycom endpoint type.');
    }

    if (!$row && $message === '') {
        throw new RuntimeException('Endpoint not found.');
    }
} catch (Throwable $exc) {
    $error = $exc->getMessage();
}
?>
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{font-family:Tahoma,sans-serif;margin:0;padding:18px;color:#202124;background:#fff}.button{background:#C62828;color:#fff;border:0;border-radius:4px;padding:10px 14px;font:inherit;cursor:pointer}.success{background:#E8F5E9;border:1px solid #A5D6A7;color:#1B5E20;padding:10px;border-radius:6px;margin-bottom:12px}.error{background:#FFEBEE;border:1px solid #EF9A9A;color:#B71C1C;padding:10px;border-radius:6px;margin-bottom:12px}.warn{background:#FFF8E1;border:1px solid #FFE082;color:#5D4037;padding:12px;border-radius:6px;margin-bottom:12px}@media(prefers-color-scheme:dark){body{background:#1e1e1e;color:#e0e0e0}.warn{background:#352b10;border-color:#66511a;color:#ffe2a8}}</style></head><body>
<?php if ($message): ?><div class="success"><?= polycom_endpoint_delete_h($message) ?></div><?php endif; ?>
<?php if ($error): ?><div class="error"><?= polycom_endpoint_delete_h($error) ?></div><?php endif; ?>
<?php if ($row): ?><div class="warn">Delete <?= polycom_endpoint_delete_h($label) ?>?</div><form method="post"><button class="button" type="submit">Delete Endpoint</button></form><?php endif; ?>
</body></html>

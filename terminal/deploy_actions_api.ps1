# deploy_actions_api.ps1
# Déploie le patch "actions API" sur tous les Raspberry Pi MODICS.
# Lance en administrateur sur le serveur MODICS.
#
# Prérequis : OpenSSH (ssh + scp) disponible (Windows 10/Server 2019+).
# Si le Pi utilise un autre compte, modifier $PI_USER ci-dessous.
# Si un mot de passe est requis, installer sshpass ou configurer les clés SSH.

$PI_USER  = "pi"
$PI_MOUL  = "/home/pi/Downloads/moul.py"
$PATCH    = "C:\inetpub\modics\terminal\apply_actions_api.py"
$SSH_OPTS = "-o StrictHostKeyChecking=no -o ConnectTimeout=5"

# IPs des Pis (extraites de machines.json)
$PIS = @(
    @{Name="PRS 2";  IP="192.168.82.240"},
    @{Name="PRS 4";  IP="192.168.82.225"},
    @{Name="PRS 5";  IP="192.168.82.235"},
    @{Name="PRS 6";  IP="192.168.82.152"},
    @{Name="PRS 29"; IP="192.168.81.80"},
    @{Name="PRS 40"; IP="192.168.81.79"},
    @{Name="PRS 63"; IP="192.168.81.56"},
    @{Name="PRS 66"; IP="192.168.82.137"},
    @{Name="PRS 69"; IP="192.168.82.125"},
    @{Name="PRS 70"; IP="192.168.82.208"},
    @{Name="PRS 71"; IP="192.168.82.238"},
    @{Name="PRS 72"; IP="192.168.82.127"},
    @{Name="PRS 74"; IP="192.168.81.75"},
    @{Name="PRS 75"; IP="192.168.81.43"},
    @{Name="PRS 77"; IP="192.168.81.81"},
    @{Name="PRS 81"; IP="192.168.81.82"},
    @{Name="PRS 84"; IP="192.168.81.77"}
)

foreach ($pi in $PIS) {
    $ip   = $pi.IP
    $name = $pi.Name
    Write-Host "`n=== $name ($ip) ===" -ForegroundColor Cyan

    # 1. Copier le script de patch sur le Pi
    & scp $SSH_OPTS $PATCH "${PI_USER}@${ip}:/tmp/apply_actions_api.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  SKIP : impossible de joindre $ip" -ForegroundColor Yellow
        continue
    }

    # 2. Appliquer le patch
    $out = & ssh $SSH_OPTS "${PI_USER}@${ip}" "python3 /tmp/apply_actions_api.py $PI_MOUL 2>&1"
    Write-Host "  Patch : $out" -ForegroundColor $(if ($out -match "^OK") { "Green" } elseif ($out -match "déjà appliqué") { "DarkGreen" } else { "Red" })

    # 3. Redémarrer moul.py (systemd ou pkill + relance)
    if ($out -match "^OK") {
        $restart = & ssh $SSH_OPTS "${PI_USER}@${ip}" @'
if systemctl is-active --quiet modics 2>/dev/null; then
    sudo systemctl restart modics && echo "systemd restart OK"
else
    pkill -f moul.py 2>/dev/null; sleep 1
    nohup python3 /home/pi/Downloads/moul.py > /tmp/moul.log 2>&1 &
    echo "relance directe PID=$!"
fi
'@
        Write-Host "  Restart : $restart" -ForegroundColor Green
    }
}

Write-Host "`nDéploiement terminé." -ForegroundColor Cyan

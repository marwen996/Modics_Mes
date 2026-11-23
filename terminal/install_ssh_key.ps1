# install_ssh_key.ps1
# Installe la cle SSH publique du serveur MODICS sur chaque Raspberry Pi,
# pour permettre ensuite les connexions ssh/scp sans mot de passe.
# A lancer dans une fenetre PowerShell interactive : le mot de passe du compte
# "pi" est demande une fois par carte. Sans danger a relancer (pas de doublon).

$PI_USER = "pi"
$PUB     = "$env:USERPROFILE\.ssh\id_ed25519.pub"

if (-not (Test-Path $PUB)) {
    Write-Host "Cle publique introuvable : $PUB" -ForegroundColor Red
    exit 1
}
$key = (Get-Content $PUB -Raw).Trim()

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

$ok = @(); $ko = @()
foreach ($pi in $PIS) {
    $ip = $pi.IP; $name = $pi.Name
    Write-Host "`n=== $name ($ip) ===" -ForegroundColor Cyan

    # Deja installee ? (test sans mot de passe)
    & ssh -o BatchMode=yes -o ConnectTimeout=5 "${PI_USER}@${ip}" "true" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Cle deja installee" -ForegroundColor DarkGreen
        $ok += $name; continue
    }

    # Ajout de la cle (le mot de passe du Pi est demande ici)
    $cmd = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && grep -qxF '$key' ~/.ssh/authorized_keys 2>/dev/null || echo '$key' >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys"
    & ssh -o ConnectTimeout=5 "${PI_USER}@${ip}" $cmd

    # Verification
    & ssh -o BatchMode=yes -o ConnectTimeout=5 "${PI_USER}@${ip}" "true" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK" -ForegroundColor Green; $ok += $name
    } else {
        Write-Host "  ECHEC" -ForegroundColor Red; $ko += $name
    }
}

Write-Host "`nAcces OK : $($ok -join ', ')" -ForegroundColor Green
if ($ko.Count) { Write-Host "Echec    : $($ko -join ', ')" -ForegroundColor Red }

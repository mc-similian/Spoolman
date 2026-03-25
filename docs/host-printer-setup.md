# Host-Drucker Einrichtung (CUPS) für Spoolman

Diese Anleitung beschreibt die Einrichtung eines am Host angeschlossenen Druckers für Spoolman, mit besonderem Fokus auf den **KNAON Y41BT** Thermodrucker mit **30x40mm Etiketten** in einer Proxmox LXC + Docker Umgebung.

Die Anleitung ist aber auch für andere Drucker und Setups anwendbar.

---

## Inhaltsverzeichnis

1. [Architektur-Überblick](#architektur-überblick)
2. [CUPS auf dem Proxmox Host installieren](#1-cups-auf-dem-proxmox-host-installieren)
3. [Y41BT Drucker am Host einrichten](#2-y41bt-drucker-am-host-einrichten)
4. [Etikettenformat konfigurieren](#3-etikettenformat-konfigurieren)
5. [CUPS für Netzwerkzugriff konfigurieren](#4-cups-für-netzwerkzugriff-konfigurieren)
6. [Docker Compose anpassen](#5-docker-compose-anpassen)
7. [Spoolman Einstellungen](#6-spoolman-einstellungen)
8. [Testdruck](#7-testdruck)
9. [Fehlerbehebung](#fehlerbehebung)
10. [Andere Druckertypen](#andere-druckertypen)

---

## Architektur-Überblick

```
┌──────────────────────────────────────────────────┐
│  Proxmox Host                                    │
│                                                  │
│  USB ──► Y41BT Drucker                           │
│            ▲                                     │
│            │ /dev/usb/lp0                         │
│            │                                     │
│  ┌─────────┴──────────┐                          │
│  │  CUPS Server        │ ◄── Port 631            │
│  │  (auf dem Host)     │                          │
│  └─────────▲──────────┘                          │
│            │                                     │
│  ┌─────────┴──────────────────────────┐          │
│  │  LXC Container                      │          │
│  │  ┌──────────────────────────────┐   │          │
│  │  │  Docker Container (Spoolman) │   │          │
│  │  │  cups-client ──► CUPS_SERVER │   │          │
│  │  └──────────────────────────────┘   │          │
│  └─────────────────────────────────────┘          │
└──────────────────────────────────────────────────┘
```

**Empfohlener Ansatz:** CUPS läuft direkt auf dem Proxmox Host (oder im LXC). Der Spoolman Docker-Container verbindet sich über das Netzwerk mit CUPS. **Kein USB-Passthrough in den Container nötig.**

---

## 1. CUPS auf dem Proxmox Host installieren

```bash
# Auf dem Proxmox Host (oder im LXC Container):
apt update
apt install -y cups cups-client printer-driver-gutenprint

# CUPS-Dienst starten und aktivieren
systemctl enable cups
systemctl start cups

# Aktuellen Benutzer zur lpadmin-Gruppe hinzufügen
usermod -aG lpadmin root
```

> **Alternativ:** Du kannst CUPS auch im LXC Container installieren, in dem Docker läuft. In diesem Fall ist kein Netzwerk-Zugriff nötig, da CUPS und Spoolman im selben Container sind.

---

## 2. Y41BT Drucker am Host einrichten

### Über den Y41BT (KNAON)

| Eigenschaft | Wert |
|---|---|
| Typ | Thermodirektdrucker |
| Protokoll | TSPL (TSC Printer Language) |
| Auflösung | 203 x 203 DPI |
| Druckgeschwindigkeit | max. 100 mm/s |
| **Papierbreite** | **35–110 mm (Minimum 35mm!)** |
| Anschluss | USB-C, Bluetooth (BT nur Windows) |
| Hersteller | KNAON / FlashLabel (Xiamen Print Future Technology) |
| FCC ID | 2A6FW-Y41 |

> **Wichtig zu 30x40mm Etiketten:** Der Y41BT hat eine **minimale Papierbreite von 35mm**. 30mm breite Etiketten werden **nicht unterstützt**. Alternativen:
> - **40x30mm Etiketten** (quer einlegen, 40mm Breite) — funktioniert, aber 30mm Länge ist sehr kurz
> - **40x40mm Etiketten** — sicherer bezüglich des Einzugs
> - Etiketten ab **35mm Breite** verwenden (z.B. 35x45mm, 40x30mm, etc.)
>
> Bei jedem Etikettenwechsel muss die **Intelligent Label Calibration** durchgeführt werden: Halte die Feeder-Taste gedrückt, bis ein Piepton ertönt.

### Option A: Offiziellen KNAON Linux-Treiber installieren (empfohlen für AMD64)

Der offizielle Treiber installiert einen CUPS-Filter (`raster-tspl`) und eine PPD-Datei.

1. Drucker per USB-C an den Host anschließen und einschalten.

2. Treiber von der KNAON-Website herunterladen:
   - Gehe zu [knaon.com/pages/download-driver-user-manual](https://knaon.com/pages/download-driver-user-manual)
   - Lade den **Linux-Treiber (CPU: AMD64)** herunter (`.run`-Datei)
   - **Hinweis:** Der offizielle Treiber ist **nur für AMD64** verfügbar (kein ARM/Raspberry Pi!)

3. Treiber installieren:
   ```bash
   chmod +x KNAON_Y41BT_Linux_*.run
   ./KNAON_Y41BT_Linux_*.run
   ```

4. Drucker-URI ermitteln und Drucker hinzufügen:
   ```bash
   # USB-Geräte auflisten
   lpinfo -v | grep usb

   # Verfügbare Treiber für KNAON suchen
   lpinfo -m | grep -i knaon

   # Drucker mit dem gefundenen Treiber hinzufügen
   lpadmin -p Y41BT -E \
     -v "usb://KNAON/Y41BT" \
     -m <treiber-name-aus-lpinfo>
   ```

### Option B: Community TSPL-Treiber (auch für ARM/Raspberry Pi)

Der Y41BT ist ein TSPL-kompatibler Drucker (verwandt mit dem HPRT N41/SL42). Es gibt mehrere Open-Source CUPS-Treiber:

| Projekt | Sprache | Hinweise |
|---|---|---|
| [thorrak/rpi-tspl-cups-driver](https://github.com/thorrak/rpi-tspl-cups-driver) | C | Vorkompilierte `raster-tspl`-Filter + PPDs |
| [ch0dak/Label-Printer-for-Linux](https://github.com/ch0dak/Label-Printer-for-Linux) | Rust | Baubarer CUPS-Filter |
| [prodocik/xprinter-xp-v3-linux](https://github.com/prodocik/xprinter-xp-v3-linux) | Python | Python-basierter TSPL-Filter |

Beispielinstallation mit `rpi-tspl-cups-driver`:
```bash
git clone https://github.com/thorrak/rpi-tspl-cups-driver.git
cd rpi-tspl-cups-driver

# Filter und PPD installieren
sudo cp raster-tspl /usr/lib/cups/filter/
sudo chmod 755 /usr/lib/cups/filter/raster-tspl
sudo cp ppd/*.ppd /usr/share/cups/model/

# CUPS neustarten
sudo systemctl restart cups

# Drucker hinzufügen
lpinfo -v | grep usb
lpadmin -p Y41BT -E \
  -v "usb://KNAON/Y41BT" \
  -m <ppd-datei-aus-lpinfo-m>
```

### Option C: Generische Raw-Queue (Fallback)

Falls kein TSPL-Treiber funktioniert, kann eine Raw-Queue verwendet werden:

```bash
# USB-URI ermitteln
lpinfo -v | grep usb

# Drucker als Raw-Queue hinzufügen
lpadmin -p Y41BT -E \
  -v "usb://KNAON/Y41BT" \
  -m raw

# Als Standarddrucker setzen
lpadmin -d Y41BT
```

> **Hinweis:** Bei einer Raw-Queue werden Druckdaten ohne Konvertierung direkt an den Drucker gesendet. Dies funktioniert am besten, wenn Spoolman das Bild bereits in der richtigen Größe und Auflösung (203 DPI) rendert.

### Drucker testen

```bash
# Drucker-Status prüfen
lpstat -p -d

# Testseite drucken
echo "Testdruck Y41BT" | lp -d Y41BT
```

---

## 3. Etikettenformat konfigurieren

> **Wichtig:** Der Y41BT unterstützt Papierbreiten von **35–110mm**. 30mm Breite ist **nicht möglich**.
> Falls du 30x40mm Etiketten verwenden möchtest, lege sie **quer** ein (40mm Breite x 30mm Höhe) — oder verwende Etiketten ab 35mm Breite.

### Beispielformate

| Etikett | CUPS-Format | Hinweis |
|---|---|---|
| 40x30mm (quer) | `Custom.40x30mm` | 30mm Länge ist sehr kurz, Einzug ggf. problematisch |
| 40x40mm | `Custom.40x40mm` | Gute Alternative |
| 50x30mm | `Custom.50x30mm` | Mehr Platz für Inhalt |
| 62x29mm | `Custom.62x29mm` | Gängiges Etikettenformat |
| 100x150mm | `Custom.100x150mm` | Standardformat (4x6") |

### Standardformat setzen

```bash
# Benutzerdefinierte Papiergröße als Standard setzen (Beispiel 40x30mm)
lpadmin -p Y41BT -o PageSize=Custom.40x30mm

# Weitere nützliche Optionen
lpadmin -p Y41BT -o fit-to-page=true
lpadmin -p Y41BT -o orientation-requested=3  # 3=Hochformat, 4=Querformat
```

### Konfiguration überprüfen

```bash
# Aktuelle Optionen anzeigen
lpoptions -p Y41BT -l

# Druckerdetails anzeigen
lpstat -l -p Y41BT
```

### Drucker-Instanzen für verschiedene Etikettengrößen (optional)

Falls du mehrere Etikettengrößen verwendest, kannst du eigene Instanzen anlegen:

```bash
lpoptions -p Y41BT/label40x30 -o PageSize=Custom.40x30mm -o fit-to-page=true
lpoptions -p Y41BT/label62x29 -o PageSize=Custom.62x29mm -o fit-to-page=true
```

### Etikettenformat kalibrieren

Bei jedem Wechsel der Etikettengröße muss die automatische Kalibrierung durchgeführt werden:

1. Neue Etiketten in den Drucker einlegen
2. Die **Feeder-Taste** gedrückt halten, bis ein **Piepton** ertönt
3. Der Drucker fährt einige Etiketten durch und erkennt die Größe automatisch

### Testdruck

```bash
# PNG-Bild mit der konfigurierten Größe drucken
lp -d Y41BT -o PageSize=Custom.40x30mm -o fit-to-page label_test.png
```

---

## 4. CUPS für Netzwerkzugriff konfigurieren

Damit der Spoolman Docker-Container auf CUPS zugreifen kann, muss CUPS auf Netzwerkverbindungen hören.

### cupsd.conf anpassen

```bash
nano /etc/cups/cupsd.conf
```

Folgende Änderungen vornehmen:

```conf
# Auf allen Interfaces hören (oder nur auf Docker-Bridge)
Port 631
Listen /run/cups/cups.sock

# Web-Interface aktivieren (optional, für Verwaltung)
WebInterface Yes

# Zugriff für das Docker-Netzwerk erlauben
<Location />
  Order allow,deny
  Allow localhost
  Allow 172.16.0.0/12
  Allow 192.168.0.0/16
</Location>

<Location /admin>
  Order allow,deny
  Allow localhost
</Location>

<Location /admin/conf>
  AuthType Default
  Require user @SYSTEM
  Order allow,deny
  Allow localhost
</Location>
```

### CUPS neustarten

```bash
systemctl restart cups

# Prüfen, ob CUPS auf Port 631 hört
ss -tlnp | grep 631
```

---

## 5. Docker Compose anpassen

### docker-compose.yml

```yaml
version: "3.8"
services:
  spoolman:
    image: ghcr.io/donkie/spoolman:latest
    restart: unless-stopped
    volumes:
      - ./data:/home/app/.local/share/spoolman
    ports:
      - "7912:8000"
    environment:
      - TZ=Europe/Berlin
      # CUPS-Server auf dem Host
      - CUPS_SERVER=host.docker.internal:631
    extra_hosts:
      # Ermöglicht host.docker.internal im Container
      - "host.docker.internal:host-gateway"
```

> **Hinweis zur `CUPS_SERVER` Variable:** Dies ist eine Standard-CUPS-Umgebungsvariable, die von den `lp`/`lpstat`-Befehlen im Container automatisch verwendet wird. Es ist **kein USB-Passthrough** in den Container nötig.

### Wenn CUPS im selben LXC Container läuft

Falls CUPS direkt im LXC Container läuft (nicht auf dem Proxmox Host), verwende stattdessen die IP-Adresse des LXC:

```yaml
environment:
  - CUPS_SERVER=<LXC-IP-Adresse>:631
```

Oder wenn CUPS im selben Container wie Docker läuft:

```yaml
environment:
  - CUPS_SERVER=localhost:631
network_mode: host
```

---

## 6. Spoolman Einstellungen

1. Spoolman im Browser öffnen
2. **Einstellungen** → **Allgemein** navigieren
3. Im Abschnitt **Drucken**:
   - **Druckmodus** auf **Host-Drucker** umstellen
   - **Host-Drucker** → den `Y41BT` aus dem Dropdown wählen
   - **Druckeroptionen** (optional, Beispiel für 40x30mm):
     ```json
     {
       "media": "Custom.40x30mm",
       "fit-to-page": "",
       "orientation-requested": "3"
     }
     ```
4. **Speichern** klicken

### Druckeroptionen erklärt

| Option | Beschreibung | Beispiel |
|---|---|---|
| `media` | Papiergröße | `Custom.30x40mm`, `Custom.62x29mm` |
| `fit-to-page` | Bild auf Seite einpassen | `""` (leer = aktiviert) |
| `orientation-requested` | Ausrichtung | `3` = Hochformat, `4` = Querformat |
| `Resolution` | Druckauflösung | `203dpi` |
| `page-left`, `page-top` | Seitenränder (in Punkten, 1pt = 1/72 Zoll) | `0` |

### Spoolman Druck-Layout anpassen

Im Label-Druckdialog solltest du für deine Etiketten folgende Einstellungen verwenden (Beispiel 40x30mm):

- **Papiergröße:** Custom → 40mm x 30mm
- **Spalten:** 1
- **Zeilen:** 1
- **Ränder:** alle auf 0mm
- **Safe-Zone:** alle auf 0mm (oder nach Bedarf anpassen)

---

## 7. Testdruck

1. In Spoolman eine Spule öffnen oder den Etikettendruck starten
2. Layout im Vorschau-Dialog anpassen
3. Auf **"Über Host drucken"** klicken
4. Das Etikett sollte auf dem Y41BT gedruckt werden

### Vom Terminal testen

```bash
# Im Spoolman Docker-Container:
docker exec -it <container_name> lpstat -p -d

# Sollte den Y41BT als verfügbaren Drucker zeigen
```

---

## Fehlerbehebung

### Drucker wird nicht angezeigt

```bash
# 1. CUPS-Erreichbarkeit vom Container prüfen
docker exec -it <container_name> lpstat -h host.docker.internal:631 -p

# 2. CUPS-Server-Variable prüfen
docker exec -it <container_name> env | grep CUPS

# 3. Firewall prüfen (Port 631 muss offen sein)
iptables -L -n | grep 631
```

### "CUPS is not available" in Spoolman

- Stelle sicher, dass das Docker-Image mit `cups-client` gebaut wurde
- Prüfe ob die `CUPS_SERVER` Umgebungsvariable gesetzt ist
- Teste die Verbindung: `docker exec -it <container_name> lpstat -p`

### USB-Drucker wird auf dem Host nicht erkannt

```bash
# USB-Geräte auflisten
lsusb

# Kernel-Nachrichten prüfen
dmesg | grep -i usb | tail -20

# Prüfen ob usblp-Modul geladen ist
lsmod | grep usblp

# Falls nötig, usblp-Modul laden
modprobe usblp

# Gerätedatei prüfen
ls -la /dev/usb/lp*
```

### Druckqualität / Skalierung stimmt nicht

- **DPI anpassen:** Der Y41BT druckt mit 203 DPI. In den Spoolman-Druckeroptionen `"Resolution": "203dpi"` hinzufügen
- **Skalierung:** `"fit-to-page": ""` in den Optionen aktivieren
- **Ränder entfernen:** `"page-left": "0", "page-right": "0", "page-top": "0", "page-bottom": "0"` setzen

### Proxmox LXC-spezifische Probleme

Falls CUPS im LXC Container läuft und USB durchgereicht werden muss:

```bash
# Auf dem Proxmox Host: LXC Konfiguration bearbeiten
nano /etc/pve/lxc/<ID>.conf

# USB-Bus durchreichen (Bus-Nummer mit lsusb ermitteln)
lxc.cgroup2.devices.allow: c 189:* rwm
lxc.mount.entry: /dev/bus/usb/001 dev/bus/usb/001 none bind,optional,create=dir

# udev-Regel für Berechtigungen (auf dem Proxmox Host)
echo 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="XXXX", MODE="0666"' \
  > /etc/udev/rules.d/99-y41bt.rules
udevadm control --reload-rules

# LXC Container neustarten
pct restart <ID>
```

> **Tipp:** Die USB Vendor/Product ID findest du mit `lsusb` auf dem Proxmox Host. Ersetze `XXXX` durch die tatsächlichen Werte.

> **Wichtig:** USB-Hotplug funktioniert in LXC-Containern nicht zuverlässig. Der Drucker sollte vor dem Container-Start angeschlossen sein.

---

## Andere Druckertypen

Die Host-Druck-Funktion von Spoolman funktioniert mit jedem Drucker, der über CUPS eingerichtet ist.

### Gängige Label-Drucker

| Drucker | Treiber | Hinweise |
|---|---|---|
| **KNAON Y41BT** | Offizieller Linux-Treiber oder Raw-Queue | Siehe oben |
| **Brother QL-Serie** | `printer-driver-ptouch` | `apt install printer-driver-ptouch` |
| **DYMO LabelWriter** | `printer-driver-dymo` | `apt install printer-driver-dymo` |
| **Zebra (ZPL)** | Raw-Queue oder Zebra CUPS-Treiber | Raw-Queue für ZPL-Daten |
| **Niimbot** | Raw-Queue | Meist USB-Seriell, ESC/POS |
| **Generische Thermodrucker** | `printer-driver-gutenprint` oder Raw | `apt install printer-driver-gutenprint` |

### Allgemeine Einrichtung für andere Drucker

```bash
# 1. Drucker anschließen und URI ermitteln
lpinfo -v

# 2. Passenden Treiber finden
lpinfo -m | grep -i <hersteller>

# 3. Drucker hinzufügen
lpadmin -p MeinDrucker -E \
  -v "usb://Hersteller/Modell" \
  -m <treiber>

# 4. Papiergröße setzen (Breite x Höhe in mm)
lpadmin -p MeinDrucker -o PageSize=Custom.WIDTHxHEIGHTmm

# 5. Als Standard setzen
lpadmin -d MeinDrucker
```

---

## Quellen

- [KNAON Y41BT Produktseite](https://knaon.com/blogs/knaon-y41bt)
- [KNAON Y41BT User Manual](https://knaon.com/pages/knaon-y41bt-user-manual)
- [KNAON Y41BT Linux USB Setup Guide](https://knaon.com/blogs/knaon-y41bt/how-to-use-printer-on-linux-via-usb-cable)
- [KNAON / FlashLabel Driver Downloads](https://knaon.com/pages/download-driver-user-manual)
- [FlashLabel Driver Downloads](https://flashlabel.com/pages/download-driver-user-manual)
- [thorrak/rpi-tspl-cups-driver (Community TSPL-Treiber)](https://github.com/thorrak/rpi-tspl-cups-driver)
- [ch0dak/Label-Printer-for-Linux (Rust TSPL-Treiber)](https://github.com/ch0dak/Label-Printer-for-Linux)
- [prodocik/xprinter-xp-v3-linux (Python TSPL-Treiber)](https://github.com/prodocik/xprinter-xp-v3-linux)
- [CUPS Command-Line Administration](https://www.cups.org/doc/admin.html)
- [ArchWiki: CUPS](https://wiki.archlinux.org/title/CUPS)
- [Proxmox Forum: USB Passthrough in LXC](https://forum.proxmox.com/threads/pass-usb-device-to-lxc.124205/)
- [Proxmox Forum: LXC mit CUPS und /dev/usb/lp0](https://forum.proxmox.com/threads/lxc-with-cups-and-dev-usb-lp0.39020/)
- [FCC ID: 2A6FW-Y41](https://fccid.io/2A6FW-Y41)

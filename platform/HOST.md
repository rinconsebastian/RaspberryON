# Host: Raspberry Pi 3B+

Datos observados por SSH (solo lectura) el 2026-11-11.

| Dato | Valor |
|---|---|
| IP | 192.168.10.239/24 (`wlan0`, WiFi) |
| Usuario de administración | `rinconsebastian` (grupos `sudo`, `gpio`) |
| SO | Debian GNU/Linux 13 (trixie) |
| Arquitectura | aarch64 (arm64) |
| Python | 3.13.5 |
| RAM | 905 MB |
| Disco | 15 GB (SD), ~11 GB libres |
| GPIO | `/dev/gpiochip0`, `gpiochip1`, `gpiochip4`; `pinctrl` y `gpioset` disponibles |
| Puertos en escucha de inicio | solo 22 |
| sudo | pide contraseña hasta ejecutar `platform/enable-sudo.sh` |

Recomendación: reserva DHCP para esta IP en el enrutador y, si es posible, cable Ethernet.

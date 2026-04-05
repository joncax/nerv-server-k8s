# nerv-server-k8s-01 — Ports Reference

> **Last updated:** 2026-04-05
> **Server IP:** 192.168.1.50
> **mDNS:** nerv-server-k8s-01.local

## NodePort Services

| App | Namespace | Internal Port | NodePort | URL |
|---|---|---|---|---|
| Jellyfin | `jellyfin` | 8096 | 30096 | http://192.168.1.50:30096 |
| Sonarr | `sonarr` | 8989 | 30989 | http://192.168.1.50:30989 |
| Radarr | `radarr` | 7878 | 30878 | http://192.168.1.50:30878 |
| Bazarr | `bazarr` | 6767 | 30767 | http://192.168.1.50:30767 |
| Prowlarr | `prowlarr` | 9696 | 30696 | http://192.168.1.50:30696 |
| Transmission | `transmission` | 9091 | 30091 | http://192.168.1.50:30091 |
| Filebrowser | `filebrowser` | 8080 | 30082 | http://192.168.1.50:30082 |
| nerv-dashboard frontend | `nerv-dashboard` | 80 | 30080 | http://192.168.1.50:30080 |
| nerv-dashboard backend | `nerv-dashboard` | 8000 | 30081 | http://192.168.1.50:30081 |

## Other Services

| Service | Port | URL |
|---|---|---|
| Netdata | 19999 | http://192.168.1.50:19999 |
| MicroK8s API Server | 16443 | https://192.168.1.50:16443 |

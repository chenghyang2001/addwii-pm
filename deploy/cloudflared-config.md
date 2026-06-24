# Cloudflare Tunnel 設定說明

## 用途

將 VPS 內部的 Dashboard（port 8092）暴露到外網，透過 Cloudflare Tunnel 保護，不需開放防火牆 port。

## 前置條件

- Cloudflare 帳號已登入 VPS：`cloudflared tunnel login`
- 擁有一個 Cloudflare 管理的網域（例如：addwii.com）

## 建立 Tunnel

```bash
# 1. 建立 tunnel（一次性操作）
cloudflared tunnel create addwii-pm-dashboard

# 2. 確認 tunnel 建立成功，記錄 tunnel ID
cloudflared tunnel list

# 3. 建立設定檔（替換 <TUNNEL_ID>）
cat > ~/.cloudflared/config.yml << CFEOF
tunnel: <TUNNEL_ID>
credentials-file: /home/claude/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: dashboard.addwii.com
    service: http://localhost:8092
  - service: http_status:404
CFEOF

# 4. DNS 路由（替換 <TUNNEL_ID>）
cloudflared tunnel route dns <TUNNEL_ID> dashboard.addwii.com
```

## 啟動為 systemd 服務

```bash
# 安裝並啟用 cloudflared systemd service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

## 驗證

瀏覽器開啟 https://dashboard.addwii.com，應顯示 addwii-pm 任務看板。

## 注意事項

- Cloudflare Tunnel 不需要開防火牆 port，VPS 預設 deny-all 即可
- 若網域不在 Cloudflare 管理，需先將 NS 指向 Cloudflare
- Dashboard 只有唯讀 API，無需額外認證（敏感資料不在 Dashboard）

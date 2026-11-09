#!/bin/bash
# Deploy app Zalo PC (build tren server tu source) — CHI 1 LENH, chay tu
# bat cu thu muc nao:  bash deploy.sh
# Tu lo: cd ve thu muc app, dam bao file .env co du user + mat khau app
# (neu thieu/trong thi hoi mat khau 1 lan roi ghi lai .env), roi build
# + chay container. Khong can export bien moi truong bang tay nua, khong
# can nho phai dung dung thu muc.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

env_val() { sed -n "s/^$1=//p" .env 2>/dev/null | head -n 1; }

if [ ! -f .env ] || [ -z "$(env_val ZALO_PC_APP_USER)" ] || [ -z "$(env_val ZALO_PC_APP_PASSWORD)" ]; then
  echo "Thieu file .env hoac thieu user/mat khau app — nhap lai mot lan (mat khau khong hien chu):"
  read -s -p "Nhap mat khau app: " P; echo
  if [ -z "$P" ]; then echo "MAT KHAU RONG — dung lai, chua deploy."; exit 1; fi
  U="$(env_val ZALO_PC_APP_USER)"
  if [ -z "$U" ]; then U="TriTue2011"; fi
  printf 'ZALO_PC_APP_USER=%s\nZALO_PC_APP_PASSWORD=%s\n' "$U" "$P" > .env
  unset P U
fi

APP_VERSION=$(git rev-parse HEAD) docker compose --env-file .env -f docker-compose.build.yml up -d --build
sleep 5
docker logs zalo-zalo-pc-1 --tail 5

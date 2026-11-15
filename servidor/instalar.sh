#!/usr/bin/env bash
# Instala (o actualiza) Maquinitabs en un servidor Ubuntu: Oracle Cloud Always Free (ARM) u otro.
# Se corre en el servidor, desde la carpeta del proyecto:   bash servidor/instalar.sh
#
# Hace todo: instala Docker, abre los puertos 80 y 443 del firewall de Ubuntu, pide un usuario y una
# contraseña para entrar a la app, arma la imagen y la deja corriendo con HTTPS en
#   https://<IP-con-guiones>.sslip.io      (o en DOMINIO=tu.dominio si tenés uno)
# Volver a correrlo actualiza la app (git pull antes) sin perder los temas; pregunta de nuevo la
# contraseña solo si no hay una guardada.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "== Instalando Docker…"
  curl -fsSL https://get.docker.com | sudo sh
fi

echo "== Abriendo los puertos 80 y 443 del firewall de Ubuntu…"
for p in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 5 -p tcp --dport "$p" -m state --state NEW -j ACCEPT
done
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null 2>&1 || true
sudo netfilter-persistent save >/dev/null 2>&1 || true

if [ ! -f Caddyfile ]; then
  IP=$(curl -fsS https://api.ipify.org || curl -fsS https://ifconfig.me)
  DOMINIO=${DOMINIO:-$(echo "$IP" | tr . -).sslip.io}
  read -rp "Usuario para entrar a la app [banda]: " USUARIO
  USUARIO=${USUARIO:-banda}
  while true; do
    read -rsp "Contraseña (mínimo 8 caracteres): " CLAVE; echo
    [ ${#CLAVE} -ge 8 ] && break
    echo "Muy corta."
  done
  HASH=$(sudo docker run --rm caddy:2.8 caddy hash-password --plaintext "$CLAVE")
  cat > Caddyfile <<EOF
$DOMINIO {
	encode gzip
	basic_auth {
		$USUARIO $HASH
	}
	request_body {
		max_size 300MB
	}
	reverse_proxy maquinitabs:5055
}
EOF
  chmod 600 Caddyfile
fi
DOMINIO=$(head -n1 Caddyfile | cut -d' ' -f1)

mkdir -p canciones
echo "== Armando la imagen (la primera vez tarda 20-40 minutos)…"
sudo docker compose up -d --build
echo
echo "Listo: https://$DOMINIO"
echo "El certificado HTTPS se pide solo la primera vez que entrás (puede tardar un minuto)."

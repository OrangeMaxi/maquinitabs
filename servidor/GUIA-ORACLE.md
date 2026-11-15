# Maquinitabs en Oracle Cloud (gratis), para usarla desde cualquier lado

Con esto la app queda en un servidor en internet, con una dirección `https://` y usuario y contraseña, y se
usa desde el celular, la tablet o cualquier compu, sin depender de la compu de casa.

## Antes de arrancar: qué esperar

- **Gratis, con condiciones.** El plan *Always Free* de Oracle incluye un servidor ARM. Desde junio de 2026
  el límite es **2 núcleos y 12 GB de RAM** (antes era 4 y 24): alcanza, pero cada tema tarda unos
  **10-15 minutos** en separarse y analizarse (en la compu de casa, 5-10). Revisá los límites actuales en la
  consola, porque Oracle los cambia sin avisar mucho.
- **Pide tarjeta** para crear la cuenta (para verificar identidad; no cobra mientras uses solo lo gratuito).
- **YouTube suele bloquear las descargas desde servidores.** Si un link falla con un error de «bot» o
  «sign in», usá el botón **Subir** (la flecha al lado del link) con el archivo de audio del tema.
- **Si el servidor queda sin uso una semana**, Oracle puede apagarlo (lo «recupera» en las cuentas
  gratuitas). Se vuelve a prender desde la consola. Usándolo seguido no pasa.

## 1. Crear la cuenta

1. Entrá a <https://www.oracle.com/cloud/free/> → **Start for free**.
2. **Home region**: elegí una cercana, por ejemplo **Brazil East (São Paulo)** o **Chile Central (Santiago)**.
   No se puede cambiar después, y el servidor gratis tiene que estar en esa región.
3. Completá los datos y la tarjeta. La cuenta tarda unos minutos en quedar lista.

## 2. Crear el servidor

En la consola: menú ☰ → **Compute** → **Instances** → **Create instance**.

| Campo | Qué poner |
| --- | --- |
| Name | `maquinitabs` |
| Image | **Canonical Ubuntu 24.04** (botón *Change image*) |
| Shape | *Change shape* → **Ampere** → **VM.Standard.A1.Flex**, **2 OCPU** y **12 GB** de memoria |
| Networking | *Create new virtual cloud network*, *public subnet*, **Assign a public IPv4 address** |
| SSH keys | **Generate a key pair for me** → **Save private key** (guardá el archivo `.key`, sin él no entrás) |
| Boot volume | *Specify a custom boot volume size* → **100 GB** (lo gratis llega hasta 200 GB en total) |

**Create**. Si dice *Out of capacity*, no hay lugar libre en ese momento: probá otro *Availability domain*
o reintentá más tarde (a veces lleva varios intentos en distintos horarios).

Cuando quede en verde (*Running*), anotá la **Public IP address**.

## 3. Abrir los puertos de la web

La consola bloquea todo menos SSH. En la página del servidor: **Subnet** (link) → **Security Lists** →
**Default Security List** → **Add Ingress Rules**, dos reglas:

| Source CIDR | IP Protocol | Destination Port Range |
| --- | --- | --- |
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(El firewall de adentro de Ubuntu lo abre solo el instalador.)

## 4. Entrar al servidor e instalar

Desde PowerShell en tu compu (Windows ya trae SSH):

```powershell
ssh -i "C:\ruta\a\ssh-key-xxxx.key" ubuntu@IP_DEL_SERVIDOR
```

(Si se queja de los permisos de la clave: clic derecho en el archivo → Propiedades → Seguridad → que solo
tu usuario pueda leerlo.)

Ya adentro del servidor:

```bash
git clone https://github.com/OrangeMaxi/maquinitabs.git
cd maquinitabs
bash servidor/instalar.sh
```

Te pide un **usuario** y una **contraseña** para entrar a la app (es lo que vas a compartir con la banda).
Después arma todo: la primera vez tarda **20-40 minutos**. Al final muestra la dirección, algo así:

```
Listo: https://129-151-20-33.sslip.io
```

## 5. Usarla

Abrí esa dirección en cualquier navegador, poné el usuario y la contraseña, y listo. En el celular o la
tablet podés agregarla a la pantalla de inicio (menú del navegador → *Agregar a pantalla de inicio*).

La primera vez que entrás, el certificado HTTPS se pide solo y puede tardar un minuto.

## Mantenimiento

- **Actualizar la app** (cuando hay cambios nuevos en GitHub):

  ```bash
  cd maquinitabs && git pull && bash servidor/instalar.sh
  ```

  Los temas analizados no se pierden (están en `servidor/canciones`).
- **Cambiar la contraseña**: `rm servidor/Caddyfile && bash servidor/instalar.sh`.
- **Ver qué está haciendo**: `sudo docker logs -f maquinitabs`.
- **Pasar temas ya analizados desde la compu** (opcional, desde PowerShell en tu compu):

  ```powershell
  scp -i "C:\ruta\a\ssh-key-xxxx.key" -r "E:\Música\banda sin nombre\_herramientas\app\canciones\Mil Horas - Los Abuelos De La Nada" ubuntu@IP_DEL_SERVIDOR:maquinitabs/servidor/canciones/
  ```

- **Si el certificado HTTPS no sale** (la dirección `sslip.io` es compartida y a veces llega al límite de
  certificados): sacá un subdominio gratis en <https://www.duckdns.org> apuntando a la IP del servidor y
  corré `rm servidor/Caddyfile && DOMINIO=mibanda.duckdns.org bash servidor/instalar.sh`.

## Seguridad

- La app solo se ve con usuario y contraseña; sin eso devuelve «401». Compartila solo con la banda.
- El servidor no guarda nada personal: temas, pistas y análisis. Las búsquedas de créditos mandan título y
  artista a MusicBrainz y Wikipedia.

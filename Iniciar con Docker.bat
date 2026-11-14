@echo off
rem Arranca Maquinitabs con Docker y abre el navegador. La primera vez tarda 10-20 minutos.
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker no esta corriendo. Abri Docker Desktop, espera a que termine de iniciar y volve a probar.
  pause
  exit /b 1
)
docker compose -f app\docker-compose.yml up -d --build
if errorlevel 1 (
  echo.
  echo No se pudo arrancar. Revisa el mensaje de arriba.
  pause
  exit /b 1
)
start http://localhost:5055
echo.
echo Maquinitabs esta corriendo en http://localhost:5055
echo Para apagarla:  docker compose -f app\docker-compose.yml down
pause

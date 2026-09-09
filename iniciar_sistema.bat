@echo off
title Marketplace Manager AI - Servidor Local
echo ===============================================================
echo   Iniciando Marketplace Manager AI (Versao Definitiva 10/10)
echo   Conectando com a API Real do Mercado Livre Brasil...
echo ===============================================================
start http://localhost:8000
python servidor_local.py
pause

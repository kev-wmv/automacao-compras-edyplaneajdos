@echo off
title Publicar EncomendasEdy

echo.
echo ====================================
echo   Publicar nova versao
echo ====================================
echo.

:: Le versao atual
set /p VERSAO_ATUAL=<version.txt
echo Versao atual: %VERSAO_ATUAL%
echo.
set /p VERSAO_NOVA=Nova versao (Enter para cancelar):

if "%VERSAO_NOVA%"=="" (
    echo Cancelado.
    pause
    exit /b 0
)

:: Salva nova versao
echo %VERSAO_NOVA%> version.txt

echo.
echo [1/2] Compilando v%VERSAO_NOVA%...
echo.

call .venv312\Scripts\python.exe build_exe.py
if errorlevel 1 (
    echo.
    echo Tentativa 1 falhou. Tentando novamente...
    echo.
    call .venv312\Scripts\python.exe build_exe.py
    if errorlevel 1 (
        echo.
        echo ERRO no build apos 2 tentativas.
        echo Voltando para v%VERSAO_ATUAL%...
        echo %VERSAO_ATUAL%> version.txt
        pause
        exit /b 1
    )
)

echo.
echo [2/2] Publicando no GitHub...
echo.
call .venv312\Scripts\python.exe release.py
if errorlevel 1 (
    echo.
    echo ERRO na publicacao!
    pause
    exit /b 1
)

echo.
echo ====================================
echo  v%VERSAO_NOVA% publicada com sucesso!
echo  As maquinas atualizam na proxima abertura.
echo ====================================
echo.
pause

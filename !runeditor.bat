@echo off
cd /d "%~dp0editor"
if not exist "node_modules\electron" (
    echo Installing dependencies...
    call npm install
)
if not exist "dist\main.js" (
    echo Building...
    call npm run build
)
npx electron .

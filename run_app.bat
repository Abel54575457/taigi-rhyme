@echo off
chcp 65001 >nul
echo ========================================================
echo  台語押韻與寫歌 AI 創作工作台 (Taiwanese Rhyme Studio)
echo ========================================================
echo 正在啟動伺服器...
start http://127.0.0.1:8899
python server.py
pause

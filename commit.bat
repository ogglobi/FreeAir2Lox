@echo off
cd "c:\Zwischenspeicher\VSCode Workfolder\FreeAir2Lox-Bridge"
git add loxone_xml.py
git commit -m "fix: Preserve Loxone variable placeholder in XML - do not escape angle brackets"
git push origin main
echo Commit and push complete!

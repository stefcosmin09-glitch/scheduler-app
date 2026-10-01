# Rebuild local al CSS-ului Tailwind
#
# Ruleaza asta doar cand schimbi template-urile si vrei sa regenerezi
# app/static/tailwind.css. NU este nevoie la deploy - fisierul generat se
# versioneaza in repo, iar Railway doar ruleaza aplicatia Python.
#
# Cerinta: Node.js instalat (verificat cu `node --version`).
# Prima data: `npm install tailwindcss@2.2.19`
#
# Important: NODE_ENV=production este obligatoriu. Fara el Tailwind nu face
# purge si genereaza ~2.9 MB in loc de ~24 KB.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$env:NODE_ENV = "production"

npx tailwindcss@2.2.19 build "tailwind-input.css" -o "app/static/tailwind.css" --minify

$kb = [math]::Round((Get-Item "app/static/tailwind.css").Length / 1KB, 1)
Write-Host "Gata: app/static/tailwind.css = $kb KB"
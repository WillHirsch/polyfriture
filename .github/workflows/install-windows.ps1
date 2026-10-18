Write-Host ""
Write-Host "==========================================="
Write-Host "Cleaning up"
Write-Host "==========================================="

Remove-Item "build" -Recurse -ErrorAction Ignore
Remove-Item "dist" -Recurse -ErrorAction Ignore

Write-Host ""
Write-Host "==========================================="
Write-Host "Packaging with pyinstaller"
Write-Host "==========================================="

uv run pyinstaller polyfriture.spec -y --log-level=DEBUG

Write-Host ""
Write-Host "==========================================="
Write-Host "Archiving the package as a zip file"
Write-Host "==========================================="

Compress-Archive -Path .\dist\polyfriture\* -DestinationPath .\dist\polyfriture.zip

Write-Host ""
Write-Host "==========================================="
Write-Host "Read version from file"
Write-Host "==========================================="
$version = uv run python -c "import polyfriture; print(polyfriture.__version__)"
Write-Host $version

Write-Host ""
Write-Host "==========================================="
Write-Host "Build MSI with WiX"
Write-Host "==========================================="

& "$env:WIX/bin/heat.exe" dir "dist/polyfriture" -cg PolyfritureFiles -gg -scom -sreg -sfrag -srd -dr INSTALLFOLDER -out "dist/PolyfritureFilesFragment.wxs"
& "$env:WIX/bin/candle.exe" installer/polyfriture.wxs -dVersion="$version" -o dist/wixobj/ -arch x64
& "$env:WIX/bin/candle.exe" dist/PolyfritureFilesFragment.wxs -o dist/wixobj/
& "$env:WIX/bin/light.exe" -ext WixUIExtension -cultures:en-us -b dist/polyfriture dist/wixobj\*.wixobj -o "dist/polyfriture-$version.msi"

# Installer can be tested with:
#    msiexec /i dist\polyfriture-0.38.msi /l*v MyLogFile.txt
# for uninstall:
#    msiexec /x dist\polyfriture-0.38.msi

Write-Host ""
Write-Host "==========================================="
Write-Host "Build MSIX package"
Write-Host "==========================================="

Copy-Item -Path .\dist\polyfriture -Destination .\dist\polyfriture-msix -Recurse
Copy-Item -Path resources\images\friture.iconset\icon_512x512.png -Destination .\dist\polyfriture-msix\icon_512x512.png

# apply version to AppxManifest.xml and save it to the package folder.
$xml = [xml](Get-Content .\installer\appxmanifest.xml)
$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace("ns", $xml.DocumentElement.NamespaceURI)
$package = $xml.SelectSingleNode("//ns:Package", $ns)
$package.Identity.Version = "$version.0.0"
$xml.Save(".\dist\polyfriture-msix\AppxManifest.xml")

# SignTool is omitted here on purpose,
# as Microsoft Store ingestion signs the final package.
MakeAppx pack /v /d .\dist\polyfriture-msix /p ".\dist\polyfriture-$version.msix"

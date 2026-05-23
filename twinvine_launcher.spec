# twinvine_launcher.spec
# Build: & "C:\Users\Desktop\Downloads\twinvine-launcher\TwinVine\.venv\Scripts\python.exe" -m PyInstaller twinvine_launcher.spec
# Output: dist\TwinVineLauncher.exe

block_cipher = None
from PyInstaller.utils.hooks import collect_data_files

pyqt6_datas = collect_data_files("PyQt6", include_py_files=False)

a = Analysis(
    ["twinvine_launcher.py"],
    pathex=["C:\\Users\\Desktop\\AppData\\Local\\Programs\\Python\\Python313\\Lib"],
    binaries=[],
    datas=pyqt6_datas + [("assets", "assets")],
    hiddenimports=[
        "PyQt6", "PyQt6.QtWidgets", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.sip",
        "requests", "requests.adapters", "urllib3", "certifi",
        "charset_normalizer", "idna", "pkg_resources",
        "xmlrpc", "xmlrpc.client", "xmlrpc.server",
        "defusedxml", "defusedxml.xmlrpc",
        "colorsys", "difflib", "textwrap", "fractions",
        "decimal", "statistics", "unicodedata",
        "math", "cmath", "numbers", "abc",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "vinefeeder", "envied", "scrapy", "parsel", "beaupy",
        "lxml", "httpx", "rich", "click", "pyyaml", "yaml",
        "tkinter", "test", "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TwinVineLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime*.dll", "Qt6*.dll"],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=r"assets\icon.ico",
)

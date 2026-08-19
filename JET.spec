# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec dosyası — JET Otomasyon Aracı
# Kullanım: pyinstaller JET.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/index.html', '.'),   # HTML frontend -> exe içine gömülür
    ],
    hiddenimports=[
        'flask',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'werkzeug.exceptions',
        'pandas',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'xlrd',
        'webview',
        'webview.platforms.winforms',
        'clr',
        'System',
        'System.Windows.Forms',
        'pythonnet',
        'jinja2',
        'jinja2.ext',
        'itsdangerous',
        'click',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'sklearn', 'PIL', 'cv2', 'tensorflow', 'torch'],
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
    name='JET_Otomasyon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # Pencere modu — konsol göstermez
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # İkon eklemek isterseniz yorum satırını kaldırın
)

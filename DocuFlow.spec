# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  DocuFlow Enterprise — PyInstaller build spec
#  Run:  pyinstaller DocuFlow.spec
# ============================================================

import os, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect ALL PyQt6 Qt plugins (needed for correct styling on Windows/Mac)
qt_plugins = collect_data_files('PyQt6', includes=['Qt6/plugins/*'])

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # The QSS is now fully embedded in app.py, so the folder is optional.
        # Keep it here so dev edits to theme.qss still work when running from source.
        ('ui/styles/theme.qss', 'ui/styles'),
    ] + qt_plugins,
    hiddenimports=[
        'PyQt6.QtPrintSupport',   # required by QTextEdit
        'PyQt6.QtSvg',
        'PyQt6.sip',
        'PIL',
        'PIL.Image',
        'docx',
        'sqlite3',
        'smtplib',
        'email',
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='DocuFlow Enterprise',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # --windowed  (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='ui/styles/icon.ico',   # uncomment + add your .ico file
)

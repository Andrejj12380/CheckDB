# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis([
    'main.py',
],
    pathex=[],
    binaries=[],
    datas=[
        ('new_logo.png', '.'),
        ('flash.ico', '.'),
        ('loader.gif', '.'),
        ('products.json', '.'),
        ('profiles.json', '.'),
        ('appsettings.json', '.'),
    ],
    hiddenimports=collect_submodules('PyQt5'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CheckDB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    pngn='flash.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CheckDB'
) 
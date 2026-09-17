# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

# Exclude heavy unrelated machine-learning packages present in local dev environment
EXCLUDES = [
    'torch',
    'torchvision',
    'torchaudio',
    'scipy',
    'sympy',
    'llvmlite',
    'numba',
    'whisper',
    'openai-whisper',
    'matplotlib',
    'IPython',
    'pytest',
    'unittest',
    'tkinter',
    'curses'
]

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HIDDEN_IMPORTS = [
    'webview',
    'webview.platforms.winforms',
    'clr',
    'pythonnet',
    'fitz',
    'docx',
    'docx.document',
    'watchdog',
    'watchdog.observers',
    'watchdog.observers.winapi',
    'watchdog.events',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'cv2',
    'PIL',
    'onnxruntime',
    'pyclipper',
    'shapely'
] + collect_submodules('rapidocr_onnxruntime')

DATA_FILES = [
    ('gui', 'gui'),
    ('settings.example.json', '.')
] + collect_data_files('rapidocr_onnxruntime') + collect_data_files('onnxruntime')

a = Analysis(
    ['app.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ScannedDocumentsRenamer',
    icon=os.path.abspath('gui/icon.ico') if os.path.exists('gui/icon.ico') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ScannedDocumentsRenamer'
)

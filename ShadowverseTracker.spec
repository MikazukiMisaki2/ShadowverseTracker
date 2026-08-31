# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:/Github/ShadowverseTracker/run_tracker.py'],
    pathex=['D:/Github/ShadowverseTracker/src'],
    binaries=[],
    datas=[('D:/Github/ShadowverseTracker/SV_WB_Cards', 'SV_WB_Cards'), ('D:/Github/ShadowverseTracker/src/shadowverse_tracker/data/SV_WB_Cards.csv', 'shadowverse_tracker/data'), ('D:/Github/ShadowverseTracker/src/shadowverse_tracker/version_profiles', 'shadowverse_tracker/version_profiles')],
    hiddenimports=['shadowverse_tracker.version_profiles'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShadowverseTracker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShadowverseTracker',
)

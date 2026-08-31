# Shadowverse Tracker

《Shadowverse: Worlds Beyond》的 Windows 外置只读记牌器。它通过读取本机游戏进程的公开对局状态来维护牌库与对局记录；不修改游戏文件、不注入 DLL，也不会暂停游戏。

> 当前读取配置对应游戏版本 `1.9.0.17891`。游戏更新后，程序会在版本校验失败时停止读取，避免套用旧偏移产生错误数据。

## 当前功能

- 启动 Tracker 后自动等待游戏、自动连接对局；一局结束后会继续等待下一局。
- 显示我方手牌、双方公开场面、双方生命、PP、牌库数量与近期使用记录。
- 使用本地已选牌组维护剩余牌库；抽空的牌会保留为 `0/3`，悬浮牌库会以红色标记。
- `SV_WB_Cards` 卡图资源存在时，悬浮牌库优先显示卡图；缺图时才显示名称。
- 本地牌组仓库：可从官方牌组链接、hash 或四位临时牌组码导入，也可在 Tracker 内搜索、增删和调整卡牌。
- 牌组登记会选择职业与模式；新增卡牌限制为本职业或中立，轮换模式按当前卡包范围过滤。
- 对局记录：按当前牌组统计总胜率、各职业对局，以及先手/后手胜率。
- 抽牌概率：选择尚未抽空的牌并输入未来抽牌次数，计算至少抽到一张的概率。
- 人机本地对局中会显示客户端保存的对手手牌；在线对局只显示公开或可推断的信息。

## 直接运行发布版（推荐）

从 GitHub Release 下载 `ShadowverseTracker.zip` 后，**完整解压**再运行：

```text
ShadowverseTracker/
├─ ShadowverseTracker.exe
├─ _internal/
└─ SV_WB_Cards/
```

双击 `ShadowverseTracker.exe` 即可。不要只把 EXE 单独移走：`_internal` 与 `SV_WB_Cards` 都是运行所需文件，后者包含卡图与卡牌资源。

运行发布版不需要安装 Python、Pillow、PyInstaller 或二维码识别组件。请在同一台 Windows 电脑上启动游戏和 Tracker；如果进程读取被系统拒绝，请让两者以相同权限运行。

## 从源码运行

### 必需环境

- Windows 10/11
- Python 3.11 或更新版本
- 已安装并能启动的《Shadowverse: Worlds Beyond》
- 项目根目录中的 `SV_WB_Cards/` 资源目录（仓库内已包含，用于卡图）

Python 依赖只有 [Pillow](https://pypi.org/project/pillow/)，用于在 Tkinter 中显示 WebP 卡图；其余读取功能使用 Python 标准库与 Windows API。二维码导入已从当前版本移除，因此**不需要** OpenCV、pyzbar 等二维码依赖。

在 PowerShell 中执行：

```powershell
cd D:\Github\ShadowverseTracker
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python run_tracker.py
```

如果 PowerShell 阻止激活脚本，可仅对当前窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

也可以不创建虚拟环境，直接安装后运行：

```powershell
py -3.11 -m pip install -e .
py -3.11 run_tracker.py
```

## 使用说明

1. 启动 Tracker；它会自动等待游戏进程，无需手动填写 BattleModel 地址或点击连接。
2. 在“当前牌组”中选择已有牌组，或选择职业与模式后，在“链接 / 四位牌组码”中粘贴官方牌组链接、hash、或刚生成的四位牌组码，再导入保存。
3. 四位牌组码由官方服务查询，通常只有短暂有效期；过期或查询失败时请重新生成，或改用官方链接。
4. 卡组有小幅调整时，使用“编辑当前卡组”搜索并增删卡牌。保存不会重置该牌组已有胜率。
5. 勾选“启用对局记录（本地）”即可记录已识别终局；统计窗口会分开显示总计、对职业胜率、先手与后手胜率。

本地数据默认保存在：

```text
%LOCALAPPDATA%\ShadowverseTracker\decks.json
%LOCALAPPDATA%\ShadowverseTracker\matches.json
```

## 构建发布包

构建机需要 Python 3.11+、Pillow 与 PyInstaller。脚本会自动安装后两者，并把卡图、卡牌 CSV 和版本配置一起打入产物：

```powershell
cd D:\Github\ShadowverseTracker
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1
```

默认输出是启动更快的目录版：

```text
dist\ShadowverseTracker\ShadowverseTracker.exe
```

如确实需要单个 EXE：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 -OneFile
```

由于卡图资源接近 200 MB，推荐默认目录版；发布时将整个 `dist\ShadowverseTracker` 压缩为 ZIP 上传到 GitHub Release。

## 测试

```powershell
python -m unittest discover -s tests -q
```

## 限制与说明

- 这是针对特定游戏版本的研究项目；版本更新后需要新的版本配置才能恢复读取。
- Tracker 始终以只读方式访问进程，不会改写内存、游戏文件或网络数据。
- 在线对局不会显示对手隐藏手牌身份。
- 请自行确认卡图等第三方资源的使用与再分发许可。

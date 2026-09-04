# Shadowverse Tracker

《Shadowverse: Worlds Beyond》Windows 只读记牌器。Tracker 会读取本机游戏进程中的对局状态，用于显示牌库、手牌、场面、计数器和对局记录；不会修改游戏文件、注入 DLL 或暂停游戏。当前同时支持 Steam 版与国服 MuMu 配套的 Windows Unity 客户端；国服使用共享战场根对象的运行时发现，首次适配建议先在练习/对战页面确认状态栏显示“已连接国服”。

## 开始使用

1. 准备一个完整的 Tracker 程序目录（源码运行或已解压的程序目录）。
2. 如果使用 Windows 程序目录，请确认 `ShadowverseTracker.exe`、`_internal` 和 `SV_WB_Cards` 位于同一目录；源码运行可跳过此项。
3. 先启动游戏，再双击 `ShadowverseTracker.exe`。
4. Tracker 会自动寻找游戏和当前对局，不需要填写地址或点击“开始读取”；如果 Steam 与国服同时运行，可在“连接方式”中指定客户端。
5. 在“当前牌组”中选择或导入自己的牌组，记牌器才能准确维护剩余牌库。

### PySide6 界面迁移

当前迁移在 `ui/pyside6-migration` 分支。该分支将默认界面切换为 PySide6 + QFluentWidgets：左侧导航、卡片式仪表盘、牌组管理、概率计算、详细统计和设置分别独立成页，读取服务与训练记录仍复用现有后端。旧 Tk 界面保留在 `shadowverse_tracker.app`，便于回退和对照。

源码运行前安装依赖：

```powershell
python -m pip install -e .
python .\run_tracker.py
```

当前旧版发行包与迁移版发行包分别保存在 `dist\ShadowverseTracker-legacy` 和 `dist\ShadowverseTracker`；两者均为 onedir 目录，启动时请保留目录内的 `_internal` 与 `SV_WB_Cards`。此前生成的迁移包备份在 `dist\ShadowverseTracker-PySide6`。

### 国服直接启动

国服启动器会启动一个 Windows Unity 客户端，并不要求 Tracker 读取模拟器的 Android 内存。Tracker 会自动识别以下国服进程：`MuMu模拟器x影之诗高清版.exe`（部分 Windows API 会显示磁盘文件的 `.o` 后缀），并校验同目录的 `GameAssembly.dll`。

在已安装国服客户端的电脑上，可以先尝试直接启动 Unity 文件（把路径改成自己的安装位置）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_china_shadowverse.ps1 `
  -Mode Direct -GamePath 'D:\Games\Shadowverse\MuMu模拟器x影之诗高清版.o'
```

也可以使用仓库附带的脚本自动查找客户端；找不到 Windows 文件时会回退到 MuMu CLI：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_china_shadowverse.ps1
```

发布包中的同名脚本会与 `ShadowverseTracker.exe` 放在一起；源码运行时直接使用仓库的 `scripts` 目录即可。

明确使用 MuMu CLI（本机示例为 VM 1、国服包名 `com.netease.yzs.hd`）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_china_shadowverse.ps1 `
  -Mode MumuCli -VmIndex 1 -PackageName com.netease.yzs.hd
```

若直接运行 `.o` 后无法完成登录、更新或启动，继续使用官方 `launcher.exe` 即可，Tracker 仍会在游戏进程出现后自动连接：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_china_shadowverse.ps1 -Mode Launcher
```

当前已内置国服 Windows 11.9.0.1 配置（`GameAssembly.dll` SHA-256：`79BD3884CFA1B4989FDFF6273F64E5985D92E8A9FF702685E60936CC804E53E4`），版本配置按哈希匹配；客户端更新后如果显示“不支持当前 GameAssembly”，请保留该提示中的哈希并反馈。游戏和 Tracker 需要使用相同权限运行；若游戏以管理员权限启动，请也以管理员权限启动 Tracker。不要为了绕过启动器、更新或账号验证修改游戏文件。

国服部分卡牌在对局对象中使用 `862…` 运行时 ID，与牌组编辑器使用的全球卡牌 ID 不同。Tracker 会通过随程序附带的 `cn_card_ids.json` 自动转换，因此手牌、场面、抽牌和事件记录仍显示中文卡名；若新版本出现“未知卡牌”，通常是客户端新增了尚未收录的 ID，请连同 GameAssembly 哈希一并反馈。

## 主要功能

- 显示我方手牌、双方公开场面、生命值、PP 和牌库数量。
- 记录起手牌、换牌、每回合抽牌、使用卡牌、进化和爆牌。
- 根据已选择牌组维护剩余牌库；已抽空的卡牌会保留并标记为 `0/3`。
- 提供加载卡图的悬浮牌库窗口，方便在游戏中查看剩余牌。
- “我的卡组”页支持导入牌组、完整浏览卡图，并可选择任意卡牌作为牌组封面；当前牌组会显示 SVWB 职业标志。
- 默认开启本地胜负统计，提供总胜率、对手职业、先手/后手等数据；“详细统计”窗口可按牌组查看和重置记录。
- 主界面的“概率计算”窗口提供普通抽牌概率、对手当前/下回合 Key 牌概率，以及“天晶深渊”伤害概率计算；窗口支持竖向布局。
- “天晶深渊”按每个信仰点独立以 `1/3` 概率分配给 X/Y/Z 的二项分布计算 `P(Z≥下限)`。
- 自动按对局生成适合训练数据管线的紧凑回放记录；记录使用卡牌、进化、攻击、特效、
  抽牌、爆牌，以及从牌库/生成区直接进入战场的卡牌。

## 对局数据采集与上传

Tracker 会自动记录每局对局，不受“本地胜负统计”复选框影响。每局结束后写入：

```text
logs/training_matches.jsonl
```

每行是一局独立 JSON 对象：`dk`/`deck.k` 是牌组键，`deck` 保存完整牌组（卡牌 ID 与数量），`m` 保存起手
与换牌，`s` 是可直接定位的完整状态检查点（其中 `l` 是可用动作掩码，`b` 是牌库计数），`e` 是按顺序排列的事件。事件使用短键和数字
卡牌 ID，包含 `p` 使用、`ev` 进化、`a` 攻击、`fx` 特效、`df` 从牌库置入、`tk` 生成/置入、
`d` 抽牌、`sel` 选择、`ac` 启动卡牌效果、`out` 离场等类型；因此不需要另外查找本地牌组即可复盘整局。隐藏手牌仍以未知
槽位保存，不会把对手私有信息伪装成已知卡牌。记录不包含进程地址或进程 ID；`z=1` 表示已收到胜/负结果，`z=0` 表示在关闭或断线时保存的未完成回放。

上传没有预设服务器，只有用户明确配置后才会启用。将下面的环境变量设置给 Tracker：

```text
SHADOWVERSE_TRACKER_UPLOAD_URL=https://your-server.example/api/matches
SHADOWVERSE_TRACKER_UPLOAD_ENABLED=1
SHADOWVERSE_TRACKER_UPLOAD_TOKEN=（可选）
```

Tracker 会把同一份紧凑 JSON 通过 HTTP `POST` 发送；服务器返回 2xx 后才从队列移除。失败
或离线时数据保存在 `logs/training_upload_queue.jsonl`，下次启动自动重试。未设置地址或
未显式启用时不会向网络发送任何对局数据。

## 牌组管理

可以在“导入链接 / 牌组码”中导入官方牌组链接、hash 或四位牌组码，也可以在 Tracker 内搜索、编辑和保存牌组。四位牌组码通常只有短暂有效期，失效后请重新生成。

本地数据保存在：

```text
%LOCALAPPDATA%\ShadowverseTracker\decks.json
%LOCALAPPDATA%\ShadowverseTracker\matches.json
```

## Key 概率

Tracker 默认使用 `unknown`（未知策略）。这表示无法确定对手留下的是目标 Key，还是其他同样可能被保留的牌，因此不把换牌数量或“看到对手留牌”直接当作 Key 证据。

计算会把“剩余牌库 + 未知手牌”视为随机池。设剩余 Key 数为 `K`、剩余牌库为 `D`、未知手牌为 `H`，则当前至少有一张 Key 的概率为：

```text
1 - C(D, K) / C(D + H, K)
```

“对手下回合 Key 概率”会先模拟对手下一回合从牌库抽 1 张，再用抽牌后的牌库和未知手牌数量计算。只有在明确知道对手留牌规则时，才建议切换到 `known`。

## 常见问题

### 显示未连接或版本校验失败

请确认游戏已经启动，并让游戏与 Tracker 使用相同的权限运行。检测到未知 `GameAssembly.dll` 时，Tracker 会自动从项目 GitHub 获取已审核的版本配置并缓存在：

```text
%LOCALAPPDATA%\ShadowverseTracker\version_profiles
```

如果服务器尚未发布对应配置，但核心 IL2CPP 类指针与最近版本完全一致，Tracker 会显示“自动兼容”并继续只读运行；核心结构发生变化时仍会停止读取。自动更新需要能够访问 GitHub。

### 牌库数量不准确

请确认选择了正确的本地牌组。Token、生成牌、隐藏信息和未识别事件无法始终被准确推断；对局结束后会自动清理当前对局数据。

### 对手隐藏手牌

在线对局只显示游戏公开或能够从公开效果可靠推断出的信息，不会读取或显示对手隐藏手牌身份。

## 遇到 Bug 时如何反馈

为了方便定位问题，请尽量同时提供以下信息：

- `logs/app_session.jsonl`：Tracker 的读取日志。请截取出现问题前后相关时间段，或上传整个文件。
- 使用的 Tracker 版本，以及游戏版本号。
- 问题发生时的截图，最好同时包含 Tracker 界面和游戏内战场记录。
- 使用的牌组名称、模式、先手/后手，以及复现问题的具体回合和操作步骤。
- 如果是概率计算问题，请附上当时输入的参数和显示结果。

如果问题与牌组或对局记录有关，也可以一并提供：

```text
%LOCALAPPDATA%\ShadowverseTracker\decks.json
%LOCALAPPDATA%\ShadowverseTracker\matches.json
```

上传前请检查并删除 BattleModel 地址、进程信息、账号信息、好友名、房间号及其他不希望公开的内容。不要上传游戏安装目录、完整内存转储或包含账号凭据的文件。日志和训练记录可能包含卡牌 ID、牌组、对局时间和对局过程；只提交定位问题所需的最小范围。

如果问题涉及训练记录、攻击或特效识别，请同时提供 `logs/training_matches.jsonl`；如果启用了上传且发生网络失败，再提供 `logs/training_upload_queue.jsonl`。这些文件中的 `deck` 和事件流可以在不运行游戏的情况下重放问题。

## 免责声明

本项目是非官方的个人研究工具，与 Cygames、Shadowverse 或 Steam 无关。程序按“尽力而为”提供信息，不能保证读取结果、概率结果或对局记录始终准确，也不构成游戏策略、账号安全或竞技公平性的保证。

虽然 Tracker 设计为只读访问，但用户应自行确认游戏规则、平台规则和赛事规则是否允许使用外部辅助工具。请勿在禁止使用此类工具的环境中运行；因使用本程序造成的账号处罚、数据损失、兼容性问题或其他后果，由使用者自行承担。

程序主要在本机保存牌组和对局数据。版本配置自动更新只会向项目 GitHub 请求公开的 JSON 配置；对局数据只有在用户配置上传地址并显式启用后才会发送。请在分享日志、截图或训练数据前，自行检查其中是否包含个人信息或对局信息。

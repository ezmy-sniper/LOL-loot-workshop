# LoL Loot Workshop · 英雄碎片工坊

带原生桌面界面的英雄联盟战利品工具：连接正在运行的客户端，预览英雄碎片处理清单，再按规则顺序重随和分解。

界面采用深青黑玻璃面板、暗金金属边框、暖金文字与青蓝高亮。按钮、勾选框、标签页和确认弹窗使用同一套材质；所有纹理和徽记均由代码绘制。

默认规则：**分解价值低于630蓝色精萃的英雄碎片，每三个重随一次，再分解所得永久英雄；不足三个的余数保留。价值630及以上的碎片直接分解。** 不同英雄的碎片可以混合重随，优先消耗更便宜的碎片。

## 功能

- 中文桌面界面，英雄搜索、分组清单、库存余额、计划统计和执行进度。
- 阈值可调整；关闭重随后可以直接分解全部英雄碎片。
- 执行前确认具体计划，执行过程中逐笔检查库存与配方；防止同一用户的多个工具窗口同时执行。
- 支持同一英雄的多个碎片，以及重随额外返还蓝色精萃。
- 只分解本次重随新产生的永久英雄，保留之前已有的永久英雄物品。
- 完成当前组后停止，导出JSON结果和本地交易记录。
- 离线演示模式，使用内置合成数据，可完整体验处理流程。

## 使用

### Windows可执行文件

解压Windows发布包，运行 `LoLLootWorkshop.exe`。先登录英雄联盟客户端，再点击 **连接客户端 → 刷新库存 / 生成预览 → 执行预览计划**。

连接信息受权限限制时，点击 **以管理员权限重启**，并在Windows系统提示中确认。工具默认以标准权限运行。也可以选择客户端目录内的 `lockfile`；部分国服客户端的该文件为空，这时应使用自动连接。

使用 **体验演示** 可以在离线数据上试用界面；演示模式不会连接游戏客户端。

### 从源码运行

需要Windows、Python 3.10或更新版本，以及Python安装包附带的Tkinter。运行时仅使用Python标准库。

```powershell
python main.py
# 离线演示
python main.py --demo
```

也可以双击 `run.cmd`。请在登录客户端后连接，在排队、选人和对局之外使用。

## 交互流程

1. 连接客户端并读取当前账号库存。
2. 调整阈值、重随开关，重新生成预览。
3. 查看每种英雄的处理方式、消耗数量和保留数量。预计收益只包含直接分解部分，随机重随收益不预估。
4. 确认计划后开始处理。每组重随所得会立即分解，然后才处理下一组。
5. 完成后显示实际收益。点击刷新查看剩余碎片，也可导出结果。

分解和重随会消耗物品，无法撤销。执行时请保持客户端登录，避免同时手动处理战利品；库存变化会使工具停止。

### 未拥有的英雄

重随结果由客户端决定，可能自动解锁未拥有的英雄，这部分无法分解。默认会检查是否拥有全部英雄，无法确认时在发出操作前停止。若希望接受自动解锁，可以勾选界面中的对应选项，再重新预览和确认。

### 中断与记录

每笔操作先记录意图，再发送请求，收到响应后保存并核对实际库存。超时或响应异常时**不会自动重试**，因为客户端可能已经执行操作。

“完成当前组后停止”会完成当前组及其产出的分解，再停止后续操作。正常停止后，刷新库存即可为剩余碎片重新生成计划。

异常停止后，请先核对客户端和交易记录。如果存在尚未分解的重随所得，需要在客户端核对后手动处理。当前版本不自动恢复不确定的交易，也不会把已有永久英雄纳入新的批处理计划。

记录存放在 `%LOCALAPPDATA%\LoLLootWorkshop\history`，演示记录在其 `demo` 子目录。记录包含物品标识、数量、处理规则和账号标识的哈希，不包含连接令牌。记录仍可能反映个人库存，请勿直接提交到公开仓库。

## 构建与测试

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_gui.py
python scripts/smoke_theme.py
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

构建脚本安装PyInstaller、运行测试，再生成 `dist/LoLLootWorkshop.exe`。已安装构建依赖时可以传入 `-SkipInstall`。构建需要网络以获取依赖；运行工具本身不需要访问外部服务器。

## 发布到GitHub

项目仓库：[ezmy-sniper/LOL-loot-workshop](https://github.com/ezmy-sniper/LOL-loot-workshop)。

获取源码：

```powershell
git clone https://github.com/ezmy-sniper/LOL-loot-workshop.git
cd LOL-loot-workshop
python main.py
```

维护者更新源码并发布版本：

```powershell
git add .
git commit -m "Release v1.1.0"
git push origin main
git tag v1.1.0
git push origin v1.1.0
```

提交本目录内的源码和说明，避免提交个人库存文件。后续版本需同步修改版本号及 `RELEASE_NOTES.md`，并使用对应的新标签。

仓库包含Windows测试流程和打包流程。推送 `v*` 标签后，GitHub Actions会运行检查，构建Windows ZIP，并发布包含版本说明与SHA-256校验文件的Release。也可以在Actions里手动运行Windows release工作流，仅下载构建产物。

## 项目结构

| 文件 | 作用 |
| --- | --- |
| `loot_workshop/core.py` | 规则、计划和交易校验 |
| `loot_workshop/client.py` | 本地客户端发现、只连接回环地址的接口封装 |
| `loot_workshop/engine.py` | 顺序执行、停止、库存核对和交易记录 |
| `loot_workshop/gui.py` | Tkinter桌面界面 |
| `loot_workshop/demo.py` | 合成库存与离线客户端 |
| `tests/` | 规则、交易和执行异常测试 |
| `.github/workflows/` | 测试与Windows发布包构建 |

客户端请求仅发往 `https://127.0.0.1`。连接令牌只保留在进程内存中；本地自签名证书仅在专用回环连接中处理，不修改系统证书设置。工具没有账号密码输入、遥测或自动更新功能。操作通过客户端本地接口完成，不使用按键脚本或读取游戏内存。

## 兼容性与项目声明

Windows是当前支持的平台。其他系统的自动连接、可执行文件和界面布局未验证。客户端本地接口可能随版本变动；配方或响应格式不符时工具会停止，需要更新适配。

这是独立社区项目，与Riot Games、腾讯及WeGame没有隶属关系，未获其认可。League of Legends及相关名称和商标归各自权利人所有。公开分发前，请自行核对适用的第三方开发者政策：[Riot开发者文档](https://developer.riotgames.com/docs/lol)。

许可证：MIT，见 [LICENSE](LICENSE)。

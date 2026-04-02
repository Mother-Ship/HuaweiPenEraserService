# HuaweiPenEraserService

MateBook E 系列全应用双击切换橡皮。

## 本分支魔改说明

- 程序仅加载当前程序目录下的 `PenService-PCManager.dll`，感谢eiyooooo/MateBook-E-Pen。（由于原作者未考虑**不安装电脑管家**，只安装Pen App的场景，Pen App附带的DLL有权限问题和DLL函数缺失问题，去掉扫描 `HuaweiPenAPP` / `C:\Windows`的逻辑）。
- 启动时会检测管理员权限，非管理员会自动弹出 UAC 提权，这一步是为了给所有管理员权限的程序发送快捷键。
- 启动时会在程序目录自动释放/更新 `config.json`，可直接修改其中各绘图软件的笔/橡皮快捷键，以适配你的自定义快捷键。
- 托盘右键新增 `绘画软件兼容模式`（默认开启）：
  - 双击切换笔/橡皮擦时，除调用 DLL 外，还会检测前台进程并发送软件内快捷键。

## 配置说明

- `config.json` 位于程序同目录。
- `target_app_shortcuts` 的 key 是进程名，value 里包含 `pen` / `eraser` 两个快捷键。
- 快捷键支持单键和组合键，格式遵循 `keyboard` 库，例如：`b`、`ctrl+e`、`shift+alt+1`。

示例：

```json
{
  "target_app_shortcuts": {
    "sai.exe": {
      "pen": "b",
      "eraser": "e"
    },
    "photoshop.exe": {
      "pen": "b",
      "eraser": "shift+e"
    }
  }
}
```

## 单 EXE 打包（PyInstaller Onefile）

1. 安装依赖：

```bash
pip install -r requirements.txt
pip install pyinstaller
```

2. 直接命令打包：

```bash
pyinstaller --clean --noconfirm --onefile --windowed ^
  --icon "res\\Designcontest-Vintage-Eraser.ico" ^
  --add-data "res;res" ^
  --add-binary "PenService-PCManager.dll;." ^
  eraser_service.py
```

3. 或使用仓库内 `spec`：

```bash
pyinstaller --clean --noconfirm eraser_service.spec
```

4. 输出文件在 `dist/eraser_service.exe`。
5. 首次运行会触发 UAC 提权；允许后程序驻留托盘。

## 绘画兼容模式新增支持

### 新增支持（默认配置未改时）

- SAI / SAI2：笔 `B`，橡皮擦 `E`
- Photoshop：笔 `B`，橡皮擦 `E`
- CLIP STUDIO PAINT：笔 `P`，橡皮擦 `E`
- Concepts（Windows）：笔 `1`，橡皮擦 `E`（笔依赖工具槽位）

### 部分支持或不保证状态严格一致

- Krita：发送 `B/E` 可切工具，但 Krita 的橡皮擦机制可为“模式切换”语义，可能出现服务状态与画布实际状态短暂不一致。

### 不支持场景

- 前台窗口不是config.json里的作画软件进程（例如切到启动器、文件对话框等窗口，当然你也可以自己扩展代码和config.json，然后按上面的说明打包来支持你需要的软件）。
- 目标软件可执行文件名与内置识别名不一致。

## 原仓库原理分析



## 原作者的相关分析

博客：https://blog.qwq.ren/posts/huawei-matebook-e-pencil-eraser-whitelist-analysis-mitigation/

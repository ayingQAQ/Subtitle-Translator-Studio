# Subtitle Translator Studio (MVP)

本仓库是一个本地单用户字幕翻译工具，专注“翻译**已有字幕文件**”。  
This repository is a local single-user subtitle translation tool focused on translating **existing subtitle files**.  
このリポジトリは、**既存字幕ファイル**の翻訳に特化したローカル単一ユーザー向けツールです。

---

## 中文（简体）

### 最新使用说明：恢复、编码、编辑与一键启动

- **启动与停止**：双击 `start_subtitle_translator.bat`；不显示窗口时使用 `start_subtitle_translator_silent.vbs`。两个入口都使用 `launcher.py`，等待健康检查通过后才打开浏览器。重复启动复用本项目的已有服务。双击 `stop_subtitle_translator.bat` 停止服务。没有 PowerShell 启动脚本，也无需调整 PowerShell 执行策略。
- **启动日志**：服务输出在 `.data/server.log`，启动失败原因在 `.data/launcher-error.log`。默认只监听 `127.0.0.1:8501`。其他程序占用端口时会报错，不会关闭其他程序。
- **翻译恢复**：翻译在后台执行。可以取消；正在进行的请求结束后才会响应取消。已完成字幕保存在 `.data/jobs/` 的 JSON 检查点。失败项会列出，点击“继续未完成 / 仅重试失败项”只处理未完成行。重启后重新上传相同文件并使用相同配置，点击开始即可恢复。更换文件名、读取编码、接口、密钥、模型、语言或术语表会产生不同任务。
- **部分下载**：失败或取消后仍能预览和下载，未完成行保留原文，并有部分结果提示。请在发布字幕前检查是否全部完成。
- **编码检查**：上传后先检查原文预览；乱码时手动选择 UTF-8、UTF-8 BOM、CP932、GB18030、Big5 或 UTF-16。UTF-16 的换行在解码后识别。导出仍优先使用原编码，无法表示译文时回退到 UTF-8 BOM。
- **模型与连接**：测试连接获取模型列表，列表按 Provider、接口地址和密钥指纹隔离。另有“试译一句”验证当前模型能否生成译文，这一步可能计费。无法列举模型的兼容服务仍可手动填模型名并试译。
- **术语与记忆**：翻译记忆区分接口地址、术语表和提示版本；LLM 还区分原文上下文。更换术语表不会再误用原有配置的译文。原有旧命名空间记录不会删除，但新流程不会直接复用它们。
- **速度与上下文**：同时限制每批条数和字符数，默认 `APP_BATCH_SIZE=20`、`APP_MAX_BATCH_CHARS=6000`；超长单条会拆分可见文本。LLM 会收到批次前后少量字幕作为只读上下文。临时网络错误和限流会有限重试；不再对任意失败都重复发送无 JSON 参数的请求。
- **编辑译文**：可以在预览表编辑，或展开“按编号编辑字幕”使用文本框。点击应用后更新下载内容和检查点。样式标签与换行标记必须保留，否则拒绝应用。手工修改不写入全局翻译记忆，以免影响其他字幕。
- **Windows 密钥保护**：Fernet 数据密钥通过当前 Windows 用户的 DPAPI 保护，旧的明文密钥文件读取时自动迁移；迁移后不能只复制这两个文件到其他账号或系统使用。非 Windows 环境使用权限收紧的 Fernet 密钥文件。任何平台都应保护 `.data/` 和 `.env`；字幕记忆与任务检查点包含可读字幕文本。
- **清除密钥**：删除已保存密钥时同时清空当前输入、关闭自动记住并清空模型列表缓存。`.env` 中手动配置的密钥仍属于独立配置，下次新会话可能从该文件重新加载；要永久移除也应删除对应环境变量。

开发验证：

```powershell
uv sync --locked --all-groups
uv run playwright install chromium
uv run pytest -m "not e2e"
uv run pytest -m e2e --tracing retain-on-failure --screenshot only-on-failure
```

GitHub Actions 在推送和 PR 时运行 Windows/Linux 核心测试与 Linux Chromium 流程测试。浏览器测试使用本地模拟 API，无需真实密钥，不消耗付费余额；失败时上传截图与 trace。CI 通过不代表所有真实 Provider 或特效字幕都已验证。

### 0. 文档导览

本 README 按以下顺序提供三种语言说明：

1. 中文（本章节）
2. English
3. 日本語

如果你只想快速用起来，直接看：

1. [5. 快速开始（5 分钟）](#5-快速开始5-分钟)
2. [6. 启动方式（推荐双击）](#6-启动方式推荐双击)
3. [8. 实际使用流程](#8-实际使用流程)

---

### 1. 项目定位

这是一个“字幕文件翻译器”，不是“视频处理器”。

项目目标：

- 上传已有字幕文件（例如 `.srt`、`.ass`）
- 翻译为目标语言（中/英/日）
- 预览结果并导出字幕文件
- 尽可能保留原始结构、时间轴、标签和编码安全

明确不做：

- 不做视频抽轨
- 不做 OCR
- 不做封装解析（mkv/mp4 内嵌字幕提取）
- 不做图片字幕识别

---

### 2. 核心能力总览

- 本地网页 UI（Streamlit）
- UI 支持三语言切换：`中文 / 日本語 / English`
- 支持中英日互译，源语言可自动识别
- 多 Provider 翻译通道（官方 API + 无 key 方案）
- 连接测试按钮（先验证 API 再翻译）
- LLM Provider 支持“连接后拉取模型列表”
- 可选术语表（CSV）
- 本地翻译记忆库（SQLite）
- API Key 本地加密保存与自动回填
- 编码安全导出：原编码优先，不可写回自动切 `UTF-8 BOM`

---

### 3. 支持格式与限制

正式支持（稳定）：

- `SRT`
- `ASS`
- `SSA`
- `WebVTT (VTT)`

尽力支持（best effort）：

- `MicroDVD (.sub)`
- `TMP (.txt)`
- `TTML (.ttml)`
- `SAMI (.smi/.sami)`

明确排除：

- 图片字幕：`PGS/SUP`、`VobSub (.idx/.sub)` 等
- 其他非文本字幕

说明：

- `MicroDVD` 文件如果缺少 FPS 元信息，工具会明确报错并停止（避免错误时间轴）。

---

### 4. 技术栈

- Python `3.13+`
- 包管理与运行：`uv`
- Web UI：`streamlit`
- 字幕读写：`pysubs2`
- 网络请求：`httpx`
- LLM 接口：`openai` Python SDK（兼容 OpenAI 风格网关）
- Google 无 key 方案：`deep-translator`
- 编码检测：`charset-normalizer`
- 本地存储：`sqlite3`（翻译记忆）+ `cryptography`（API key 加密）

---

### 5. 快速开始（5 分钟）

#### 5.1 前置要求

- Windows 10/11（当前提供了 Windows 一键启动脚本）
- Python 3.13 或更高版本
- 已安装 `uv`

安装 uv（官方文档）：  
https://docs.astral.sh/uv/

#### 5.2 初始化项目

```powershell
uv sync --all-groups
```

```powershell
Copy-Item .env.example .env
```

#### 5.3 配置至少一个 Provider

你可以在 `.env` 配置 key，也可以在 UI 里直接填并“加密保存”。

常见最小配置示例（DeepSeek）：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

#### 5.4 启动

方式 A（命令行）：

```powershell
uv run streamlit run app.py
```

打开：

`http://localhost:8501`

---

### 6. 启动方式（推荐双击）

你可以不用每次开终端输入命令。

#### 6.1 双击启动（可见日志）

文件：`start_subtitle_translator.bat`

特点：

- 自动检查 `uv`
- 使用 `uv run --locked` 自动同步锁定依赖
- `.env` 可选，也可在界面填写密钥
- 自动打开浏览器
- 启动器显示状态；服务日志写入 `.data/server.log`

#### 6.2 双击启动（静默）

文件：`start_subtitle_translator_silent.vbs`

特点：

- 不弹终端窗口
- 后台启动 Streamlit
- 自动打开浏览器

---

### 7. 目录结构（关键文件）

```text
demo1_qwe/
├─ app.py
├─ .env.example
├─ start_subtitle_translator.bat
├─ start_subtitle_translator_silent.vbs
├─ .streamlit/config.toml
├─ src/subtitle_translator/
│  ├─ ui.py                 # 页面与交互流程
│  ├─ translator.py         # Provider 适配层 + 批量翻译逻辑
│  ├─ subtitle_io.py        # 字幕解析/回写/标签保护
│  ├─ encoding.py           # 编码识别与换行归一
│  ├─ glossary.py           # 术语表解析
│  ├─ memory.py             # 翻译记忆 SQLite
│  ├─ secret_store.py       # API key 加密存储
│  ├─ config.py             # 环境配置与路径
│  └─ models.py             # 核心数据结构
└─ .data/
   ├─ translation_memory.sqlite3
   ├─ secret_store.enc
   └─ secret_store.key
```

---

### 8. 实际使用流程

1. 左侧先选 UI 语言（中文/日本語/English）
2. 在左侧 Provider 区选择翻译通道
3. 填 API key（或使用无 key Provider）
4. 点击“测试连接”确认可用
5. 上传字幕文件
6. 选择源语言和目标语言
7. （可选）上传术语表 CSV
8. 点击“开始翻译”
9. 在预览表检查译文
10. 下载导出字幕

---

### 9. Provider 说明

#### 9.1 LLM 类（支持模型选择）

- `OpenAI`
- `Google Gemini (OpenAI-compatible)`
- `DeepSeek`
- `Qwen / DashScope (CN)`
- `Qwen / DashScope (Intl)`
- `Zhipu GLM`
- `Custom OpenAI-compatible`

行为说明：

- 先“测试连接”后可拉取实时模型列表
- 也支持手动输入模型名
- Custom 通道必须填写 Base URL

#### 9.2 机器翻译 API 类

- `DeepL API`

#### 9.3 无 key 类

- `Google Translate (deep-translator, no key)`

注意：

- 无 key 通道方便测试，但稳定性和可持续性不如官方 API。

---

### 10. 环境变量完整说明

#### 10.1 LLM / Provider 相关

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_BASE_URL`
- `GEMINI_MODEL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `DASHSCOPE_API_KEY`
- `DASHSCOPE_BASE_URL`
- `DASHSCOPE_MODEL`
- `DASHSCOPE_INTL_API_KEY`
- `DASHSCOPE_INTL_BASE_URL`
- `DASHSCOPE_INTL_MODEL`
- `ZHIPU_API_KEY`
- `ZHIPU_BASE_URL`
- `ZHIPU_MODEL`
- `CUSTOM_LLM_API_KEY`
- `CUSTOM_LLM_BASE_URL`
- `CUSTOM_LLM_MODEL`
- `DEEPL_API_KEY`
- `DEEPL_API_BASE_URL`

#### 10.2 应用运行参数

- `APP_DB_PATH`  
  翻译记忆数据库路径（默认 `.data/translation_memory.sqlite3`）
- `APP_SECRET_STORE_PATH`  
  加密 API key 数据文件路径（默认 `.data/secret_store.enc`）
- `APP_SECRET_KEY_PATH`  
  加密密钥文件路径（默认 `.data/secret_store.key`）
- `APP_BATCH_SIZE`  
  批量翻译条数（默认 `20`）
- `APP_MAX_BATCH_CHARS`
  每批字幕文本字符数上限（默认 `6000`，最小 `100`）
- `APP_MAX_FILE_SIZE_MB`  
  单文件大小上限 MB（默认 `5`）
- `APP_REQUEST_TIMEOUT_SECONDS`  
  请求超时秒数（默认 `60`）

---

### 11. 术语表 CSV 规范

文件必须是 CSV，列名固定：

```csv
source,target,notes
字幕,subtitle,UI term
姐姐,sister,dialog context
```

规则：

- `source`：源术语
- `target`：目标术语
- `notes`：可选备注

---

### 12. 编码策略与文本安全

读取：

1. 尝试 BOM
2. 编码检测
3. 回退策略（保证最大兼容）

写出：

- 优先保持原编码与原换行风格
- 如果译文无法安全写回原编码，自动改为 `utf-8-sig`（UTF-8 BOM）

标签保护：

- 保留 HTML 标签
- 保留 ASS/SSA 样式控制片段
- 使用占位符机制避免模型破坏控制标记

---

### 13. API Key 加密存储机制

你在 UI 中可选择“记住 API 密钥（加密保存）”。

实现逻辑：

- 明文不会直接写入配置文件
- 使用 `cryptography.fernet` 加密后写入 `secret_store.enc`
- Windows 下 `secret_store.key` 保存由当前用户 DPAPI 保护的数据密钥；非 Windows 为 Fernet 密钥文件

注意事项：

- `secret_store.enc` 和 `secret_store.key` 需要同时保留；Windows 下还依赖原 Windows 用户的 DPAPI 环境
- 如果 `secret_store.key` 丢失，历史加密内容无法解密
- 建议将 `.data/` 目录加入备份或按需清理

---

### 14. 翻译记忆库（Translation Memory）

用途：

- 同句重复时优先复用历史译文，减少请求次数和成本

存储：

- `APP_DB_PATH` 对应 SQLite 数据库

行为：

- 精确匹配复用
- 与 provider + model + 语言方向绑定

---

### 15. 导出规则

- 文件名：`原文件名.目标语言代码.原扩展名`
- 保持原格式导出（不跨格式转换）
- 保持时间轴、段落顺序与换行风格
- 导出时显示实际编码（便于排查乱码）

---

### 16. 常见问题排查（Troubleshooting）

#### 16.1 页面样式异常 / 看不清

- 强制刷新：`Ctrl + F5`
- 关闭旧页面后重新打开 `http://localhost:8501`
- 重启应用

#### 16.2 Provider 连接失败

- 先检查 key 是否有效、有余额、未过期
- 检查 Base URL 是否对应当前 provider
- 检查网络是否可达目标 API
- 先点“测试连接”，确认通过后再翻译

#### 16.3 字幕文件报不支持

- 检查扩展名是否在支持列表
- 图片字幕（`.sup`/`.idx`）不支持

#### 16.4 导出乱码

- 先看导出编码提示
- 若播放器不兼容，尝试播放器侧切换编码
- 工具已自动在必要时切 `UTF-8 BOM`

---

### 17. 安全与隐私说明

- 本项目为本地运行，不强制上传到第三方服务器
- 但翻译请求会发送到你选择的 Provider API
- 请遵守字幕内容版权和平台合规要求
- 生产环境建议对 `.env` 与 `.data` 做访问控制

---

### 18. 已知限制

- 仅支持文本字幕，不支持图片字幕 OCR
- 大文件翻译速度依赖网络与 Provider 响应
- 无 key 通道稳定性不保证
- 当前主要面向单用户本地使用

---

### 19. 命令速查

安装依赖：

```powershell
uv sync --all-groups
```

手动启动：

```powershell
uv run streamlit run app.py
```

---

## English

### Updated workflow: recovery, encoding, editing and launch

- **Launch/stop**: double-click `start_subtitle_translator.bat` or the silent `.vbs` entry. Both call `launcher.py`, wait for readiness and reuse an existing server from this project. Stop with `stop_subtitle_translator.bat`. No PowerShell script or execution-policy change is required. The server binds to loopback only. A port occupied by another process is reported, never terminated.
- **Logs**: `.data/server.log` contains server output; `.data/launcher-error.log` records launcher failures.
- **Recovery**: background jobs checkpoint completed lines in `.data/jobs/`. Cancel takes effect after the current request returns. Resume/retry processes unfinished lines only. After restarting, upload the same file with the same settings and start again to resume. A different filename, encoding, endpoint, key, model, language or glossary creates a different task. Partial downloads keep source text for unfinished lines and display a warning.
- **Encoding**: check the source preview and override detection with UTF-8, UTF-8 BOM, CP932, GB18030, Big5 or UTF-16 when necessary. UTF-16 newlines are detected after decoding. Output falls back to UTF-8 BOM if the original encoding cannot represent the translation.
- **Connections**: model lists are isolated by provider, endpoint and credential fingerprint. A separate sample-translation button verifies generation using the selected model and may incur cost. Manual model entry remains available for gateways without model listing.
- **Memory and batching**: memory distinguishes endpoint, glossary and prompt version, plus source context for LLMs. Old namespace records remain on disk but are not reused by the new namespace. `APP_BATCH_SIZE=20` and `APP_MAX_BATCH_CHARS=6000` bound requests; oversized visible text is split. LLM requests include a small amount of neighboring source context. Transient HTTP failures receive bounded retries.
- **Editing**: use the editable preview or expand “Edit one subtitle”. Apply updates to regenerate the download and save the checkpoint. Protected tags and newline markers must remain intact. Manual edits do not overwrite global translation memory.
- **Credentials**: Windows protects the Fernet data key with current-user DPAPI and migrates legacy key files on read. Copying both files to a different account/system is insufficient after migration. Other platforms use a restricted-permission Fernet key file. Clearing credentials empties the current field, disables remembering and clears model cache; independently configured environment keys may reload in a new session. Translation memory/checkpoints contain readable subtitle text.

Run verification:

```powershell
uv sync --locked --all-groups
uv run playwright install chromium
uv run pytest -m "not e2e"
uv run pytest -m e2e --tracing retain-on-failure --screenshot only-on-failure
```

GitHub Actions runs Windows/Linux core checks and Linux Chromium workflows on pushes and pull requests. Browser tests use a local fake API without real credentials or paid calls. Failures retain screenshots and traces. These tests do not certify every live provider or subtitle effect.

### 0. Reading Order

This README is intentionally arranged in this order:

1. Chinese
2. English (this section)
3. Japanese

If you want a fast path:

1. Read **5. Quick Start (5 minutes)**
2. Use **6. Launch Methods** (double-click startup)
3. Follow **8. User Workflow**

---

### 1. Project Scope

This is a subtitle translator, not a video processing pipeline.

What it does:

- Translates existing subtitle files
- Preserves subtitle structure as much as possible
- Exports translated subtitle files safely

What it does not do:

- No video demux/extraction
- No OCR
- No image subtitle recognition

---

### 2. Key Features

- Local web UI (Streamlit)
- Trilingual UI: `中文 / 日本語 / English`
- Translation among Chinese / English / Japanese
- Multiple provider backends (official APIs + no-key options)
- “Test Connection” before translation
- Live model fetch for LLM providers
- Optional glossary CSV
- Local translation memory (SQLite)
- Encrypted API key storage with auto-fill
- Encoding-safe export with UTF-8 BOM fallback

---

### 3. Supported Formats

Officially supported:

- `SRT`, `ASS`, `SSA`, `VTT`

Best effort:

- `MicroDVD (.sub)`, `TMP (.txt)`, `TTML`, `SAMI`

Excluded:

- Image-based subtitles such as `.sup`, `.idx/.sub` (VobSub/PGS-like)

---

### 4. Stack

- Python 3.13+
- uv
- Streamlit
- pysubs2
- openai SDK
- httpx
- deep-translator
- charset-normalizer
- sqlite3
- cryptography

---

### 5. Quick Start (5 minutes)

Install dependencies:

```powershell
uv sync --all-groups
```

Create `.env`:

```powershell
Copy-Item .env.example .env
```

Start app:

```powershell
uv run streamlit run app.py
```

Open:

`http://localhost:8501`

---

### 6. Launch Methods

Visible launcher:

- `start_subtitle_translator.bat`
- Opens browser automatically
- Keeps terminal logs visible

Silent launcher:

- `start_subtitle_translator_silent.vbs`
- Starts in background
- Opens browser automatically

---

### 7. Important Files

- `src/subtitle_translator/ui.py`: UI and workflow
- `src/subtitle_translator/translator.py`: provider adapters and translation service
- `src/subtitle_translator/subtitle_io.py`: parsing/export/tag protection
- `src/subtitle_translator/encoding.py`: decode/normalize/newline handling
- `src/subtitle_translator/memory.py`: translation memory
- `src/subtitle_translator/secret_store.py`: encrypted API key storage
- `src/subtitle_translator/config.py`: env and runtime paths

---

### 8. User Workflow

1. Select UI language
2. Select provider in sidebar
3. Enter API key (or use a no-key provider)
4. Click **Test Connection**
5. Upload subtitle file
6. Select source and target languages
7. Optionally upload glossary CSV
8. Click **Start Translation**
9. Preview result
10. Download output file

---

### 9. Providers

LLM providers:

- OpenAI
- Gemini (OpenAI-compatible endpoint)
- DeepSeek
- Qwen DashScope CN/Intl
- Zhipu GLM
- Custom OpenAI-compatible

Machine translation API providers:

- DeepL API

No-key options:

- Google Translate via deep-translator

---

### 10. Environment Variables

Provider variables:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
- `GEMINI_API_KEY`, `GEMINI_BASE_URL`, `GEMINI_MODEL`
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`
- `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODEL`
- `DASHSCOPE_INTL_API_KEY`, `DASHSCOPE_INTL_BASE_URL`, `DASHSCOPE_INTL_MODEL`
- `ZHIPU_API_KEY`, `ZHIPU_BASE_URL`, `ZHIPU_MODEL`
- `CUSTOM_LLM_API_KEY`, `CUSTOM_LLM_BASE_URL`, `CUSTOM_LLM_MODEL`
- `DEEPL_API_KEY`, `DEEPL_API_BASE_URL`

App variables:

- `APP_DB_PATH`
- `APP_SECRET_STORE_PATH`
- `APP_SECRET_KEY_PATH`
- `APP_BATCH_SIZE`
- `APP_MAX_BATCH_CHARS` (default `6000`, minimum `100`)
- `APP_MAX_FILE_SIZE_MB`
- `APP_REQUEST_TIMEOUT_SECONDS`

---

### 11. Glossary CSV

Required columns:

```csv
source,target,notes
```

Example:

```csv
source,target,notes
subtitle,subtitle,UI term
sister,sister,dialog context
```

---

### 12. Encoding and Text Safety

Read path:

- BOM + detection + fallback decode

Write path:

- Reuse original encoding/newline if possible
- Fallback to `utf-8-sig` when original encoding cannot represent translated text

Safety:

- ASS/SSA tags and HTML-like tags are protected by placeholders
- Tag order is validated after translation

---

### 13. Encrypted API Key Storage

When “Remember API key (encrypted)” is enabled:

- Keys are encrypted into `secret_store.enc`
- `secret_store.key` contains the data key protected by current-user DPAPI on Windows; other platforms use a Fernet key file
- Auto-fill works on next app start

Important:

- Keep both files; Windows also requires the original user's DPAPI environment
- Losing `secret_store.key` means old encrypted values cannot be decrypted

---

### 14. Translation Memory

- Stored in SQLite (`APP_DB_PATH`)
- Exact-match reuse for repeated lines
- Bound to provider/model and language direction

---

### 15. Output Behavior

- Output file name pattern: `originalName.targetLang.originalExt`
- Original subtitle format is preserved
- Timeline/order/newline style are preserved
- Actual output encoding is shown in UI

---

### 16. Troubleshooting

UI hard to read:

- `Ctrl+F5` hard refresh
- Restart app and reopen page

Provider connection fails:

- Verify key validity and quota
- Verify base URL
- Verify network access

Unsupported file:

- Check extension support
- Image subtitle formats are excluded

---

### 17. Security Notes

- App runs locally
- Translation content is still sent to your selected provider API
- Protect `.env` and `.data` in shared environments

---

### 18. Known Limits

- Text subtitles only
- No OCR for image subtitles
- No-key providers may be unstable
- Designed for local single-user scenario

---

## 日本語

### 更新された操作：再開・文字コード・編集・起動

- **起動と停止**：`start_subtitle_translator.bat` または静かな `.vbs` を実行します。両方とも `launcher.py` を使用し、正常起動を確認してからブラウザを開きます。重複起動時は本プロジェクトの既存サーバーを再利用します。停止は `stop_subtitle_translator.bat`。PowerShell スクリプトや実行ポリシーの変更は不要です。ループバックのみで待ち受け、他のプロセスがポートを使用している場合は終了させずエラーを表示します。
- **ログ**：サーバーログは `.data/server.log`、起動失敗は `.data/launcher-error.log` です。
- **タスク再開**：バックグラウンド翻訳の完了行を `.data/jobs/` に保存します。中止は実行中リクエストの終了後に反映されます。再開ボタンは未完了行のみ処理します。再起動後も同じファイル・設定でアップロードして開始すると再開できます。ファイル名、文字コード、接続先、キー、モデル、言語、用語集が異なると別タスクになります。部分結果の未完了行は原文のままで、警告が表示されます。
- **文字コード**：原文プレビューを確認し、必要なら UTF-8、UTF-8 BOM、CP932、GB18030、Big5、UTF-16 を選択します。UTF-16 の改行はデコード後に検出します。元の文字コードで書き出せない訳文は UTF-8 BOM に切り替えます。
- **接続とモデル**：一覧キャッシュはプロバイダー・接続先・キーの指紋で分離します。別の試し翻訳ボタンで選択モデルの生成機能を確認できます。この操作は課金される場合があります。一覧 API のないサービスではモデル名を手動入力できます。
- **メモリと速度**：翻訳メモリは接続先・用語集・プロンプト版で区別し、LLM では原文の文脈も区別します。旧メモリは削除せず、新しい名前空間では直接再利用しません。既定は `APP_BATCH_SIZE=20`、`APP_MAX_BATCH_CHARS=6000`。長すぎる可視テキストを分割し、LLM に前後の原文を少量渡します。一時的 HTTP エラーには回数制限付きで再試行します。
- **編集**：プレビュー表または「番号で字幕を編集」から修正します。適用後、ダウンロードとチェックポイントを更新します。保護タグ・改行マーカーは維持してください。手動修正は全体の翻訳メモリを書き換えません。
- **キー保護**：Windows では現在のユーザーの DPAPI で Fernet データキーを保護し、旧ファイルは読み込み時に移行します。移行後はファイルを別ユーザー・別システムにコピーするだけでは復号できません。他の環境では権限を制限した Fernet キーファイルを使用します。削除操作は現在の入力も空にし、自動保存とモデルキャッシュを解除します。環境変数のキーは独立した設定で、新しいセッションで再読み込みされる場合があります。翻訳メモリとタスクファイルには読める字幕テキストが含まれます。

検証コマンド：

```powershell
uv sync --locked --all-groups
uv run playwright install chromium
uv run pytest -m "not e2e"
uv run pytest -m e2e --tracing retain-on-failure --screenshot only-on-failure
```

GitHub Actions は push/PR 時に Windows/Linux のコアテストと Linux Chromium の操作テストを実行します。ブラウザテストはローカル模擬 API を使用し、実際のキーや有料 API 呼び出しは不要です。失敗時にはスクリーンショットと trace を保存します。すべての実サービスや字幕効果の動作保証ではありません。

### 0. 読み方

この README は次の順序です。

1. 中文
2. English
3. 日本語（本セクション）

最短手順は以下です。

1. **5. クイックスタート**
2. **6. 起動方法**
3. **8. 使い方**

---

### 1. プロジェクトの範囲

本ツールは「既存字幕ファイルの翻訳」に特化しています。

対応内容：

- 既存字幕ファイルの翻訳
- 構造・タイムライン・タグの保護
- 安全な文字コードでの書き出し

非対応：

- 動画からの字幕抽出
- OCR
- 画像字幕の認識

---

### 2. 主な機能

- ローカル Web UI（Streamlit）
- UI 言語切替：`中文 / 日本語 / English`
- 中日英の翻訳
- 複数プロバイダー対応（公式 API / 無 key）
- 接続テスト
- LLM のモデル一覧を接続後に取得
- 用語集 CSV（任意）
- 翻訳メモリ（SQLite）
- API キー暗号化保存と自動入力
- 文字コード安全なエクスポート

---

### 3. 対応字幕形式

正式対応：

- `SRT`, `ASS`, `SSA`, `VTT`

ベストエフォート：

- `MicroDVD (.sub)`, `TMP (.txt)`, `TTML`, `SAMI`

非対応：

- 画像字幕（`.sup`、`.idx/.sub` など）

---

### 4. 技術スタック

- Python 3.13+
- uv
- Streamlit
- pysubs2
- openai SDK
- httpx
- deep-translator
- charset-normalizer
- sqlite3
- cryptography

---

### 5. クイックスタート

依存関係インストール：

```powershell
uv sync --all-groups
```

`.env` 作成：

```powershell
Copy-Item .env.example .env
```

起動：

```powershell
uv run streamlit run app.py
```

ブラウザ：

`http://localhost:8501`

---

### 6. 起動方法

表示あり（ログ確認向け）：

- `start_subtitle_translator.bat`

表示なし（静かに起動）：

- `start_subtitle_translator_silent.vbs`

---

### 7. 主要ファイル

- `ui.py`: UI と操作フロー
- `translator.py`: プロバイダー層と翻訳実行
- `subtitle_io.py`: 読み込み・書き出し・タグ保護
- `encoding.py`: 文字コード処理
- `memory.py`: 翻訳メモリ
- `secret_store.py`: API キー暗号化保存
- `config.py`: 環境変数とパス

---

### 8. 使い方

1. UI 言語を選択
2. サイドバーでプロバイダー選択
3. API キー入力（または無 key プロバイダー）
4. **接続テスト**
5. 字幕ファイルをアップロード
6. 入力言語・出力言語を選択
7. 必要なら用語集 CSV を追加
8. **翻訳開始**
9. プレビュー確認
10. ダウンロード

---

### 9. プロバイダー

LLM 系：

- OpenAI
- Gemini（OpenAI 互換）
- DeepSeek
- Qwen DashScope（CN/Intl）
- Zhipu GLM
- Custom OpenAI-compatible

翻訳 API 系：

- DeepL API

無 key 系：

- Google Translate（deep-translator）

---

### 10. 環境変数

主な項目：

- 各プロバイダーの `*_API_KEY`, `*_BASE_URL`, `*_MODEL`
- `APP_DB_PATH`
- `APP_SECRET_STORE_PATH`
- `APP_SECRET_KEY_PATH`
- `APP_BATCH_SIZE`
- `APP_MAX_FILE_SIZE_MB`
- `APP_REQUEST_TIMEOUT_SECONDS`

詳細は `.env.example` を参照してください。

追加設定：`APP_MAX_BATCH_CHARS` は既定 `6000`、最小 `100` です。

---

### 11. 用語集 CSV

必須カラム：

```csv
source,target,notes
```

---

### 12. 文字コードと安全性

読み込み：

- BOM/検出/フォールバックでデコード

書き出し：

- 可能なら元の文字コード・改行を維持
- 不可能なら `utf-8-sig` へ自動フォールバック

保護：

- ASS/SSA タグや HTML 風タグをプレースホルダーで保護

---

### 13. API キー暗号化保存

保存先：

- `secret_store.enc`
- `secret_store.key`

注意：

- 2つのファイルをセットで保持してください。Windows では元ユーザーの DPAPI 環境も必要です
- `secret_store.key` 紛失時、過去データは復号不可です

---

### 14. 翻訳メモリ

- SQLite に保存
- 同文の再翻訳を抑制
- プロバイダー/モデル/言語方向ごとに管理

---

### 15. 出力仕様

- ファイル名：`元ファイル名.言語コード.拡張子`
- 形式は元字幕形式を維持
- タイムライン・順序・改行を維持
- 実際の出力エンコードを UI に表示

---

### 16. トラブルシューティング

見づらい・表示崩れ：

- `Ctrl+F5` で再読み込み
- アプリ再起動

接続エラー：

- API キー
- Base URL
- ネットワーク

対応外ファイル：

- 拡張子を確認
- 画像字幕は非対応

---

### 17. セキュリティ

- ローカル実行が前提
- 翻訳時は選択プロバイダーへテキスト送信
- `.env` と `.data` の保護を推奨

---

### 18. 既知の制限

- テキスト字幕のみ
- 画像字幕 OCR 非対応
- 無 key プロバイダーは不安定な場合あり
- 単一ユーザー向け設計

---

End of README.

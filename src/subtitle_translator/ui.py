from __future__ import annotations

import copy
import hashlib

import streamlit as st

from subtitle_translator.config import AppConfig
from subtitle_translator.glossary import GlossaryFormatError, parse_glossary_csv
from subtitle_translator.identity import connection_identity
from subtitle_translator.jobs import TranslationJob, restore_checkpoint, save_checkpoint
from subtitle_translator.secret_store import SecretStore, SecretStoreError
from subtitle_translator.subtitle_io import (
    IMAGE_SUBTITLE_EXTENSIONS,
    SubtitleIOError,
    export_subtitle_document,
    format_timestamp,
    load_subtitle_document,
    apply_subtitle_edits,
)
from subtitle_translator.translator import (
    ProviderSettings,
    TranslationError,
    build_translator_provider,
    get_provider_spec,
    get_provider_specs,
    probe_provider_connection,
)


SOURCE_LANGUAGE_OPTIONS = {
    "zh": {
        "自动识别": "auto",
        "日语": "ja",
        "中文": "zh",
        "英语": "en",
    },
    "ja": {
        "自動判定": "auto",
        "日本語": "ja",
        "中国語": "zh",
        "英語": "en",
    },
    "en": {
        "Auto-detect": "auto",
        "Japanese": "ja",
        "Chinese": "zh",
        "English": "en",
    },
}

TARGET_LANGUAGE_OPTIONS = {
    "zh": {
        "日语": "ja",
        "中文": "zh",
        "英语": "en",
    },
    "ja": {
        "日本語": "ja",
        "中国語": "zh",
        "英語": "en",
    },
    "en": {
        "Japanese": "ja",
        "Chinese": "zh",
        "English": "en",
    },
}

SUPPORTED_EXTENSIONS = [
    "ass",
    "ssa",
    "srt",
    "vtt",
    "sub",
    "txt",
    "ttml",
    "smi",
    "sami",
]

THEME_CSS = """
<style>
    :root {
        --bg-main: #f3f6fa;
        --bg-surface: #ffffff;
        --ink-main: #0f172a;
        --ink-soft: #334155;
        --border: #d8e0ea;
        --hero-a: #0f172a;
        --hero-b: #134164;
        --shadow-soft: 0 10px 24px rgba(15, 23, 42, 0.08);
    }

    [data-testid="stAppViewContainer"] {
        background: var(--bg-main);
    }

    [data-testid="stSidebar"] {
        background: #171f2f;
        border-right: 1px solid #263248;
    }

    [data-testid="stSidebar"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #e8edf6 !important;
    }

    [data-testid="stSidebar"] div[data-baseweb="select"] > div,
    [data-testid="stSidebar"] div[data-baseweb="base-input"] {
        background-color: #1e293b !important;
        border-color: #3a4760 !important;
    }
    
    [data-testid="stSidebar"] div[data-baseweb="select"] *,
    [data-testid="stSidebar"] div[data-baseweb="base-input"] * {
        color: #e8edf6 !important;
        -webkit-text-fill-color: #e8edf6 !important;
    }

    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] [data-testid="stLinkButton"] > a {
        border: 1px solid #3a4760 !important;
        background: #111827 !important;
        color: #f8fafc !important;
        text-decoration: none !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover,
    [data-testid="stSidebar"] [data-testid="stLinkButton"] > a:hover {
        border-color: #6b7280 !important;
        background: #1f2937 !important;
        color: #ffffff !important;
    }

    [data-testid="stSidebar"] [data-testid="stLinkButton"] p {
        color: inherit !important;
    }

    .main .block-container {
        max-width: 1120px;
        padding-top: 1.2rem;
    }

    .main .block-container :is(h1, h2, h3, p, label, span, legend) {
        color: var(--ink-main);
    }

    .hero {
        border-radius: 16px;
        padding: 24px 26px;
        background: linear-gradient(135deg, var(--hero-a), var(--hero-b));
        box-shadow: var(--shadow-soft);
        margin-bottom: 14px;
    }

    .hero h1 {
        margin: 0 0 6px 0;
        color: #ffffff !important;
    }

    .hero p {
        margin: 0;
        color: #e2e8f0 !important;
        opacity: 1;
    }

    .card {
        border-radius: 14px;
        border: 1px solid var(--border);
        background: var(--bg-surface);
        box-shadow: var(--shadow-soft);
        padding: 14px 16px;
        margin-bottom: 10px;
    }

    .metric-chip {
        display: inline-block;
        border-radius: 999px;
        border: 1px solid #c7d2fe;
        background: #eef2ff;
        color: #3730a3 !important;
        padding: 4px 12px;
        font-size: 12px;
        margin-right: 8px;
    }

    .kicker {
        color: var(--ink-soft) !important;
        font-size: 13px;
        margin-bottom: 8px;
    }

    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploaderDropzone"] * {
        color: var(--ink-main) !important;
    }
</style>
"""


def _tr(ui_lang: str, zh_text: str, ja_text: str, en_text: str | None = None) -> str:
    if ui_lang == "zh":
        return zh_text
    if ui_lang == "ja":
        return ja_text
    return en_text or zh_text


def _get_uploader_localization_css(ui_lang: str) -> str:
    if ui_lang == "en":
        return ""
        
    drag_text = "拖拽文件至此处" if ui_lang == "zh" else "ここにファイルをドラッグ＆ドロップ"
    limit_text = "单个文件上限 200MB" if ui_lang == "zh" else "ファイル上限 200MB"
    browse_text = "浏览文件" if ui_lang == "zh" else "ファイルを参照"

    return f"""
<style>
    [data-testid="stFileUploadDropzone"] > div > div > span {{
        font-size: 0;
    }}
    [data-testid="stFileUploadDropzone"] > div > div > span::after {{
        content: "{drag_text}";
        font-size: 14px;
        color: var(--ink-main);
    }}
    
    [data-testid="stFileUploadDropzone"] > div > div > small {{
        font-size: 0;
    }}
    [data-testid="stFileUploadDropzone"] > div > div > small::after {{
        content: "{limit_text} • ASS, SSA, SRT, VTT, SUB, TXT, TTML, SMI, SAMI";
        font-size: 13px;
        color: var(--ink-soft);
    }}

    [data-testid="stFileUploadDropzone"] button * {{
        display: none !important;
    }}
    [data-testid="stFileUploadDropzone"] button::after {{
        content: "{browse_text}";
        font-size: 14px;
        color: inherit;
    }}
</style>
"""


def _render_ui_language_switch(default_ui_lang: str) -> str:
    lang_label_map = {"中文": "zh", "日本語": "ja", "English": "en"}
    reverse_lang_label = {"zh": "中文", "ja": "日本語", "en": "English"}
    options = ["中文", "日本語", "English"]

    selected_label = st.selectbox(
        "UI Language",
        options,
        index=options.index(reverse_lang_label.get(default_ui_lang, "中文")),
        key="ui_lang_switch",
        label_visibility="collapsed",
    )

    return lang_label_map[selected_label]


def run() -> None:
    st.set_page_config(page_title="Subtitle Translator", page_icon="ST", layout="wide")
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    default_ui_lang = st.session_state.get("ui_lang", "zh")
    
    col_empty, col_lang = st.columns([10, 2])
    with col_lang:
        ui_lang = _render_ui_language_switch(default_ui_lang)
        
    st.session_state["ui_lang"] = ui_lang
    st.markdown(_get_uploader_localization_css(ui_lang), unsafe_allow_html=True)

    hero_title = _tr(ui_lang, "字幕翻译工作台", "字幕翻訳スタジオ", "Subtitle Translator Studio")
    hero_desc = _tr(
        ui_lang,
        "本地网页工具（localhost），支持多 Provider API，翻译已有字幕并自动处理编码回写。",
        "localhost で動くローカルWebツール。複数プロバイダーAPIで既存字幕を翻訳し、文字コードも安全に再出力します。",
        "Local web app on localhost. Translate existing subtitle files with multi-provider APIs and safe encoding write-back.",
    )
    st.markdown(
        """
        <section class="hero">
            <h1>{hero_title}</h1>
            <p>{hero_desc}</p>
        </section>
        """.format(hero_title=hero_title, hero_desc=hero_desc),
        unsafe_allow_html=True,
    )

    config = AppConfig.from_env()
    config.ensure_runtime_dirs()
    secret_store = SecretStore(
        encrypted_path=config.secret_store_path,
        key_path=config.secret_key_path,
    )

    provider_spec, provider_settings = _render_provider_panel(config, ui_lang, secret_store)

    uploaded_file = st.file_uploader(
        _tr(ui_lang, "上传字幕文件", "字幕ファイルをアップロード", "Upload subtitle file"),
        type=SUPPORTED_EXTENSIONS,
        help=_tr(
            ui_lang,
            "仅支持文本字幕，.sup / .idx 等图片字幕不会处理。",
            "テキスト字幕のみ対応。 .sup / .idx など画像字幕は対象外です。",
            "Text subtitles only. Image subtitles like .sup / .idx are excluded.",
        ),
    )
    if uploaded_file is None:
        _render_support_notes(ui_lang)
        return

    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    if len(file_bytes) > config.max_file_size_bytes:
        st.error(_tr(ui_lang, "文件超过当前 MVP 大小限制。", "ファイルサイズが現在のMVP上限を超えています。", "File exceeds current MVP size limit."))
        return

    if any(uploaded_file.name.lower().endswith(ext) for ext in IMAGE_SUBTITLE_EXTENSIONS):
        st.error(_tr(ui_lang, "图片字幕格式不在此项目支持范围。", "画像字幕形式はこのプロジェクトではサポート対象外です。", "Image subtitle formats are not supported in this project."))
        return

    encoding_options = ['Auto', 'utf-8-sig', 'utf-8', 'cp932', 'gb18030', 'big5', 'utf-16', 'utf-16-le', 'utf-16-be']
    selected_encoding = st.selectbox(
        _tr(ui_lang, '读取编码', '入力エンコード', 'Input encoding'), encoding_options,
        help=_tr(ui_lang, '原文乱码时手动选择编码。', '文字化け時は手動で選択。', 'Choose manually if the source preview is garbled.'),
    )
    forced_encoding = None if selected_encoding == 'Auto' else selected_encoding
    document, parse_error = _get_cached_document(uploaded_file.name, file_bytes, file_hash, forced_encoding)
    if parse_error:
        st.error(parse_error)
        return
    assert document is not None
    with st.expander(_tr(ui_lang, '原文预览（请先检查乱码）', '原文プレビュー', 'Source preview (check encoding)'), expanded=True):
        st.caption(f'{document.encoding} | {repr(document.newline)}')
        st.dataframe([{'#': s.index + 1, 'Source': s.plain_text} for s in document.segments[:5]], hide_index=True)

    source_col, target_col = st.columns([1, 1])
    source_options = SOURCE_LANGUAGE_OPTIONS[ui_lang]
    target_options = TARGET_LANGUAGE_OPTIONS[ui_lang]
    target_values = list(target_options.values())
    target_default_index = target_values.index("zh") if "zh" in target_values else 0
    with source_col:
        source_label = st.selectbox(_tr(ui_lang, "源语言", "入力言語", "Source language"), list(source_options), index=0)
    with target_col:
        target_label = st.selectbox(
            _tr(ui_lang, "目标语言", "出力言語", "Target language"),
            list(target_options),
            index=target_default_index,
        )

    glossary_upload = st.file_uploader(_tr(ui_lang, "可选术语表 CSV", "任意の用語集 CSV", "Optional glossary CSV"), type=["csv"])
    glossary_hash = hashlib.sha256(glossary_upload.getvalue()).hexdigest() if glossary_upload is not None else "no-glossary"

    glossary_terms = []
    if glossary_upload is not None:
        glossary_terms, glossary_error = _get_cached_glossary(glossary_upload.getvalue(), glossary_hash)
        if glossary_error:
            st.error(glossary_error)
            return
        st.success(_tr(ui_lang, f"术语表已载入：{len(glossary_terms)} 条", f"用語集を読み込みました: {len(glossary_terms)} 件", f"Glossary loaded: {len(glossary_terms)} terms"))

    _render_file_summary(document, ui_lang)

    request_signature = _build_request_signature(
        file_hash=hashlib.sha256((file_hash + uploaded_file.name + document.encoding + connection_identity(provider_settings)).encode()).hexdigest(),
        source_language=source_options[source_label],
        target_language=target_options[target_label],
        provider_id=provider_spec.provider_id,
        model_name=provider_settings.model_name,
        base_url=provider_settings.base_url or "",
        glossary_hash=glossary_hash,
    )
    _reset_result_if_request_changed(request_signature)
    if (config.db_path.parent / 'jobs' / f'{request_signature}.json').exists():
        st.caption(_tr(ui_lang, '检测到已保存任务，开始翻译会继续未完成部分。', '保存済みタスクから再開します。', 'Saved task found. Start Translation resumes unfinished items.'))

    active_job = st.session_state.get('translation_job')
    if active_job and active_job['signature'] != request_signature and active_job['job'].snapshot()['status'] == 'running':
        st.warning(_tr(ui_lang, '上一任务仍在运行，请先取消后再更换配置。', '前のタスクを中止してください。', 'Cancel the running task before changing configuration.'))
        if st.button(_tr(ui_lang, '取消上一任务', '前のタスクを中止', 'Cancel previous task')):
            active_job['job'].cancel()
        return

    missing_requirements = _validate_provider_settings(provider_settings, provider_spec, require_model=True, ui_lang=ui_lang)
    if missing_requirements:
        st.warning(missing_requirements)

    with st.container(border=True):
        start_disabled = bool(missing_requirements)
        running = bool(active_job and active_job['job'].snapshot()['status'] == 'running')
        start_clicked = st.button(_tr(ui_lang, "开始翻译", "翻訳開始", "Start Translation"), type="primary", disabled=start_disabled or running)
        if start_clicked:
            _run_translation(
                config=config,
                provider_spec=provider_spec,
                provider_settings=provider_settings,
                document=document,
                source_language=source_options[source_label],
                target_language=target_options[target_label],
                glossary_terms=glossary_terms,
                request_signature=request_signature,
                ui_lang=ui_lang,
            )

    active_job = st.session_state.get('translation_job')
    if active_job and active_job['signature'] == request_signature:
        _render_job(active_job, config, provider_spec, provider_settings, document,
                    source_options[source_label], target_options[target_label], glossary_terms, ui_lang)


def _render_provider_panel(config: AppConfig, ui_lang: str, secret_store: SecretStore):
    specs = get_provider_specs()
    label_to_id = {spec.display_name: spec.provider_id for spec in specs}

    with st.sidebar:
        st.markdown(f"### {_tr(ui_lang, 'Provider 设置', 'プロバイダー設定', 'Provider Setup')}")
        probe_notice = st.session_state.pop("provider_probe_notice", None)
        if probe_notice:
            st.success(probe_notice)
        selected_label = st.selectbox(_tr(ui_lang, "预设", "プリセット", "Preset"), list(label_to_id), index=2)
        provider_id = label_to_id[selected_label]
        spec = get_provider_spec(provider_id)
        st.caption(spec.help_text)
        if spec.docs_url:
            st.link_button(
                _tr(ui_lang, "打开 API 文档", "API ドキュメントを開く", "Open API Docs"),
                spec.docs_url,
                use_container_width=True,
            )

        st.markdown("---")
        with st.expander(_tr(ui_lang, "运行参数", "実行設定", "Runtime settings"), expanded=False):
            st.markdown(f"`DB`: {config.db_path}")
            st.markdown(f"`Batch`: {config.batch_size}")
            st.markdown(f"`Max size`: {config.max_file_size_bytes // (1024 * 1024)} MB")
            st.markdown(f"`Secrets`: {config.secret_store_path}")

        key_store_error = ""
        stored_key = ""
        secret_id = _provider_secret_id(provider_id)
        try:
            stored_key = secret_store.get(secret_id)
        except SecretStoreError as exc:
            key_store_error = str(exc)

        api_key_default = config.get(spec.api_key_env_var) if spec.api_key_env_var else ""
        if not api_key_default and stored_key:
            api_key_default = stored_key

        api_key_label = (
            _tr(ui_lang, "API 密钥", "API キー", "API key")
            if spec.api_key_required
            else _tr(ui_lang, "API 密钥（可选）", "API キー（任意）", "API key (optional)")
        )
        api_key_help = (
            None
            if spec.api_key_required
            else _tr(
                ui_lang,
                "该通道可无密钥运行。",
                "このプロバイダーはキーなしでも実行できます。",
                "This provider can run without an API key.",
            )
        )
        api_key = st.text_input(
            api_key_label,
            value=api_key_default,
            type="password",
            key=f"{provider_id}_api_key",
            help=api_key_help,
        )
        if key_store_error:
            st.warning(
                _tr(
                    ui_lang,
                    f"加密存储读取失败：{key_store_error}",
                    f"暗号化ストア読み込み失敗: {key_store_error}",
                    f"Encrypted store read failed: {key_store_error}",
                )
            )

        model_name = ""
        base_url = ""

        if spec.family == "llm":
            model_default = config.get(spec.model_env_var, spec.default_model) or spec.default_model
            base_default = config.get(spec.base_url_env_var, spec.default_base_url) or spec.default_base_url
            base_url = st.text_input("Base URL", value=base_default, key=f"{provider_id}_base_url")

            model_cache = st.session_state.get("provider_model_cache", {})
            model_identity = connection_identity(ProviderSettings(provider_id, api_key, base_url=base_url))
            fetched_models = model_cache.get(model_identity, [])
            if fetched_models:
                custom_label = _tr(ui_lang, "自定义输入...", "手動入力...", "Custom input...")
                selector_options = fetched_models + [custom_label]
                selected_default = model_default if model_default in fetched_models else fetched_models[0]
                selected_model = st.selectbox(
                    _tr(ui_lang, "模型（已从接口获取）", "モデル（API 取得済み）", "Model (from API)"),
                    selector_options,
                    index=selector_options.index(selected_default),
                    key=f"model_selector_{model_identity}",
                )
                if selected_model == custom_label:
                    model_name = st.text_input(
                        _tr(ui_lang, "模型名（手动）", "モデル名（手動）", "Model name (manual)"),
                        value=model_default,
                        key=f"{provider_id}_model",
                    )
                else:
                    model_name = selected_model
                st.caption(
                    _tr(
                        ui_lang,
                        f"已获取 {len(fetched_models)} 个模型。",
                        f"{len(fetched_models)} 件のモデルを取得済み。",
                        f"Fetched {len(fetched_models)} models.",
                    )
                )
            else:
                st.info(
                    _tr(
                        ui_lang,
                        "先点击“测试连接”获取实时模型列表；你也可以先手动输入模型名。",
                        "まず「接続テスト」で最新モデル一覧を取得してください。先に手動入力も可能です。",
                        "Click Test Connection to fetch live models first, or type model name manually.",
                    )
                )
                model_name = st.text_input(
                    _tr(ui_lang, "模型名（手动）", "モデル名（手動）", "Model name (manual)"),
                    value=model_default,
                    key=f"{provider_id}_model",
                )
        elif spec.family == "deepl":
            base_default = config.get(spec.base_url_env_var, spec.default_base_url) or spec.default_base_url
            base_url = st.text_input(_tr(ui_lang, "DeepL API URL", "DeepL API URL"), value=base_default, key=f"{provider_id}_base_url")

        remember_key = st.checkbox(
            _tr(
                ui_lang,
                "记住 API 密钥（加密保存）",
                "API キーを記憶（暗号化保存）",
                "Remember API key (encrypted)",
            ),
            value=True,
            key=f"{provider_id}_remember_key",
        )
        save_col, clear_col = st.columns(2)
        with save_col:
            save_now = st.button(
                _tr(ui_lang, "保存密钥", "キー保存", "Save key"),
                use_container_width=True,
                disabled=not api_key.strip(),
                key=f"{provider_id}_save_key_now",
            )
        with clear_col:
            clear_now = st.button(
                _tr(ui_lang, "清除密钥", "キー削除", "Clear key"),
                use_container_width=True,
                key=f"{provider_id}_clear_key_now",
                on_click=_clear_saved_key,
                args=(secret_store, secret_id, provider_id),
            )

        if save_now:
            try:
                secret_store.set(secret_id, api_key.strip())
                st.success(
                    _tr(
                        ui_lang,
                        "API 密钥已加密保存。",
                        "API キーを暗号化保存しました。",
                        "API key saved in encrypted storage.",
                    )
                )
            except SecretStoreError as exc:
                st.error(str(exc))
        if clear_now:
            try:
                secret_store.delete(secret_id)
                st.success(
                    _tr(
                        ui_lang,
                        "已清除已保存的 API 密钥。",
                        "保存済み API キーを削除しました。",
                        "Saved API key cleared.",
                    )
                )
            except SecretStoreError as exc:
                st.error(str(exc))

        settings = ProviderSettings(
            provider_id=provider_id,
            api_key=api_key,
            model_name=model_name,
            base_url=base_url or None,
            timeout_seconds=config.request_timeout_seconds,
        )

        test_disabled = bool(_validate_provider_settings(settings, spec, require_model=False, ui_lang=ui_lang))
        if st.button(_tr(ui_lang, "测试连接", "接続テスト", "Test Connection"), use_container_width=True, disabled=test_disabled):
            with st.spinner(_tr(ui_lang, "正在测试连接...", "接続をテスト中...", "Testing connection...")):
                ok, message, elapsed_ms, models = probe_provider_connection(settings)
            if ok:
                if remember_key and api_key.strip():
                    try:
                        secret_store.set(secret_id, api_key.strip())
                    except SecretStoreError as exc:
                        st.warning(
                            _tr(
                                ui_lang,
                                f"连接成功，但密钥保存失败：{exc}",
                                f"接続成功。ただしキー保存に失敗: {exc}",
                                f"Connected, but key save failed: {exc}",
                            )
                        )
                if spec.family == "llm" and models:
                    model_cache = st.session_state.get("provider_model_cache", {})
                    model_cache[connection_identity(settings)] = models
                    st.session_state["provider_model_cache"] = model_cache
                    st.session_state["provider_probe_notice"] = _tr(
                        ui_lang,
                        f"{message} 已载入 {len(models)} 个模型。({elapsed_ms:.0f} ms)",
                        f"{message} {len(models)} 件のモデルを読み込みました。({elapsed_ms:.0f} ms)",
                        f"{message} Loaded {len(models)} models. ({elapsed_ms:.0f} ms)",
                    )
                    st.rerun()
                else:
                    st.success(f"{message} ({elapsed_ms:.0f} ms)")
            else:
                st.error(
                    _tr(
                        ui_lang,
                        f"连接失败：{message} ({elapsed_ms:.0f} ms)",
                        f"接続失敗: {message} ({elapsed_ms:.0f} ms)",
                        f"Connection failed: {message} ({elapsed_ms:.0f} ms)",
                    )
                )

        if st.button(_tr(ui_lang, '试译一句（可能计费）', '試し翻訳（課金の場合あり）', 'Test translation (may incur cost)'),
                     disabled=bool(_validate_provider_settings(settings, spec, ui_lang=ui_lang))):
            provider = None
            try:
                provider = build_translator_provider(settings)
                sample = provider.translate_batch(['Hello, how are you?'], source_language='en', target_language='zh', glossary=[])
                st.success(sample[0])
            except Exception as exc:
                st.error(str(exc) if isinstance(exc, TranslationError) else type(exc).__name__)
            finally:
                if provider and hasattr(provider, '_client'):
                    provider._client.close()

    return spec, settings


def _clear_saved_key(store, secret_id, provider_id):
    try:
        store.delete(secret_id)
        st.session_state[f'{provider_id}_api_key'] = ''
        st.session_state[f'{provider_id}_remember_key'] = False
        st.session_state['provider_model_cache'] = {}
    except SecretStoreError as exc:
        st.session_state['provider_probe_notice'] = str(exc)


def _run_translation(
    *,
    config: AppConfig,
    provider_spec,
    provider_settings: ProviderSettings,
    document,
    source_language: str,
    target_language: str,
    glossary_terms,
    request_signature: str,
    ui_lang: str,
) -> None:
    checkpoint = config.db_path.parent / 'jobs' / f'{request_signature}.json'
    try:
        restored, _ = restore_checkpoint(checkpoint, copy.deepcopy(document))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        st.error(f'Cannot restore task checkpoint: {exc}')
        return
    try:
        job = TranslationJob(restored, provider_settings, config, source_language,
                             target_language, glossary_terms, checkpoint).start()
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        st.error(f'Cannot resume task: {exc}')
        return
    st.session_state.pop('translation_result', None)
    st.session_state['translation_job'] = {
        'signature': request_signature, 'job': job, 'target': target_language,
    }
    st.rerun()


@st.fragment(run_every=1)
def _render_job(active, config, spec, settings, document, source, target, glossary, ui_lang):
    snapshot = active['job'].snapshot()
    status = snapshot['status']
    total = snapshot['total']
    st.progress(snapshot['completed'] / total if total else 0,
                text=f"{snapshot['completed']}/{total}")
    labels = {
        'running': ('正在翻译', '翻訳中', 'Translating'),
        'completed': ('翻译完成', '翻訳完了', 'Translation completed'),
        'failed': ('有失败项，可重试', '失敗した字幕を再試行できます', 'Failed items can be retried'),
        'cancelled': ('已取消，完成结果已保存', '中止済み・結果保存済み', 'Cancelled; completed results saved'),
    }
    st.info(_tr(ui_lang, *labels[status]))
    if snapshot['error']:
        st.error(snapshot['error'])
    if status == 'running':
        if snapshot['cancelling']:
            st.info(_tr(ui_lang, '正在取消，等待当前请求返回…', 'リクエスト終了後に中止します…', 'Cancelling after current request...'))
        elif st.button(_tr(ui_lang, '取消翻译', '翻訳を中止', 'Cancel translation')):
            active['job'].cancel()
            st.rerun(scope='fragment')
        return
    if snapshot['failures']:
        st.dataframe([{'#': i + 1, 'Error': error} for i, error in snapshot['failures'].items()], hide_index=True)
    if status in ('cancelled', 'failed'):
        if st.button(_tr(ui_lang, '继续未完成 / 仅重试失败项', '未完了・失敗項目を再試行', 'Resume / retry failed items')):
            _run_translation(config=config, provider_spec=spec, provider_settings=settings,
                             document=document, source_language=source, target_language=target,
                             glossary_terms=glossary, request_signature=active['signature'], ui_lang=ui_lang)
    completed_doc = snapshot['document']
    result = st.session_state.get('translation_result')
    if not result or result['request_signature'] != active['signature']:
        checkpoint = config.db_path.parent / 'jobs' / f"{active['signature']}.json"
        try:
            completed_doc, _ = restore_checkpoint(checkpoint, completed_doc)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            st.error(f'Cannot read saved edits: {exc}')
            return
        result = {'request_signature': active['signature'], 'document': completed_doc,
                  'exported': export_subtitle_document(completed_doc, target_language=target),
                  'provider_name': spec.display_name, 'target': target,
                  'checkpoint': checkpoint,
                  'failures': snapshot['failures']}
        st.session_state['translation_result'] = result
    if status != 'completed':
        st.warning(_tr(ui_lang, '部分结果：未完成行仍保留原文。', '未完了行は原文です。', 'Partial result: unfinished lines retain source text.'))
    _render_result(result['document'], result['exported'], result['provider_name'], ui_lang)


def _render_result(translated_document, exported, provider_name: str, ui_lang: str) -> None:
    st.subheader(_tr(ui_lang, "预览", "プレビュー", "Preview"))
    st.caption(_tr(ui_lang, f"Provider: {provider_name}", f"プロバイダー: {provider_name}", f"Provider: {provider_name}"))

    rows = [
        {
            "#": segment.index + 1,
            "Start": format_timestamp(segment.start_ms),
            "End": format_timestamp(segment.end_ms),
            "Source": segment.plain_text,
            "Translation": segment.translated_raw_text if segment.translated_raw_text is not None else segment.raw_text,
        }
        for segment in translated_document.segments
        if segment.is_translatable
    ]
    max_rows = len(rows)
    default_rows = min(300, max_rows) if max_rows > 0 else 0
    preview_count = st.slider(_tr(ui_lang, "预览行数", "プレビュー行数", "Preview rows"), min_value=0, max_value=max(1, max_rows), value=default_rows, step=1)
    st.caption(_tr(ui_lang, '可编辑译文；保留行内样式标签和换行标记。', '訳文を編集できます。タグを維持してください。', 'Edit translations; preserve inline tags and newline markers.'))
    edited = st.data_editor(rows[:preview_count], disabled=['#', 'Start', 'End', 'Source'],
                            hide_index=True, height=460,
                            key='translation_editor_' + st.session_state['translation_result']['request_signature'])
    if st.button(_tr(ui_lang, '应用修改并更新下载', '変更を適用', 'Apply edits and update download')):
        try:
            exported = _save_user_edits(translated_document, {row['#'] - 1: row['Translation'] for row in edited})
            st.success(_tr(ui_lang, '修改已应用。', '適用しました。', 'Edits applied.'))
        except (SubtitleIOError, TypeError, OSError) as exc:
            st.error(str(exc))

    if rows:
        with st.expander(_tr(ui_lang, '按编号编辑字幕', '番号で字幕を編集', 'Edit one subtitle')):
            number = st.selectbox(_tr(ui_lang, '字幕编号', '字幕番号', 'Subtitle number'), [row['#'] for row in rows])
            segment = translated_document.segments[number - 1]
            signature = st.session_state['translation_result']['request_signature']
            text = st.text_area(_tr(ui_lang, '译文文本', '訳文テキスト', 'Translation text'),
                                value=segment.translated_raw_text if segment.translated_raw_text is not None else segment.raw_text,
                                key=f'line_editor_{signature}_{number}')
            if st.button(_tr(ui_lang, '应用单条修改', 'この字幕に適用', 'Apply single edit')):
                try:
                    exported = _save_user_edits(translated_document, {number - 1: text})
                    st.success(_tr(ui_lang, '修改已应用。', '適用しました。', 'Edits applied.'))
                except (SubtitleIOError, TypeError, OSError) as exc:
                    st.error(str(exc))

    st.download_button(
        label=_tr(ui_lang, f"下载 {exported.file_name}", f"ダウンロード {exported.file_name}", f"Download {exported.file_name}"),
        data=exported.content,
        file_name=exported.file_name,
        mime="text/plain",
    )
    st.caption(_tr(ui_lang, f"导出编码：`{exported.encoding}`", f"出力エンコード: `{exported.encoding}`", f"Export encoding: `{exported.encoding}`"))


def _save_user_edits(document, edits):
    working = copy.deepcopy(document)
    apply_subtitle_edits(working, edits)
    result = st.session_state['translation_result']
    exported = export_subtitle_document(working, target_language=result['target'])
    remaining = {i: message for i, message in result['failures'].items()
                 if working.segments[i].translated_raw_text is None}
    save_checkpoint(result['checkpoint'], working, remaining)
    result['document'] = working
    result['exported'] = exported
    return exported


def _render_file_summary(document, ui_lang: str) -> None:
    st.markdown('<section class="card">', unsafe_allow_html=True)
    st.markdown(f'<p class="kicker">{_tr(ui_lang, "文件检测结果", "検出されたファイル情報", "Detected File Profile")}</p>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <span class="metric-chip">{_tr(ui_lang, "格式", "形式", "Format")}: {document.format}</span>
        <span class="metric-chip">{_tr(ui_lang, "编码", "文字コード", "Encoding")}: {document.encoding}</span>
        <span class="metric-chip">{_tr(ui_lang, "换行", "改行", "Newline")}: {repr(document.newline)}</span>
        <span class="metric-chip">{_tr(ui_lang, "片段数", "セグメント数", "Segments")}: {sum(1 for s in document.segments if s.is_translatable)}</span>
        """,
        unsafe_allow_html=True,
    )
    for warning in document.warnings:
        st.warning(warning)
    st.markdown("</section>", unsafe_allow_html=True)


def _render_support_notes(ui_lang: str) -> None:
    st.markdown('<section class="card">', unsafe_allow_html=True)
    st.markdown(f"### {_tr(ui_lang, '支持字幕类型', '対応字幕形式', 'Supported Subtitles')}")
    st.write(_tr(ui_lang, "正式支持：`SRT`、`ASS`、`SSA`、`VTT`", "正式対応: `SRT`, `ASS`, `SSA`, `VTT`", "Official: `SRT`, `ASS`, `SSA`, `VTT`"))
    st.write(_tr(ui_lang, "尽力支持：`SUB (MicroDVD)`、`MPL2`、`TMP`、`TTML`、`SAMI`", "ベストエフォート: `SUB (MicroDVD)`, `MPL2`, `TMP`, `TTML`, `SAMI`", "Best effort: `SUB (MicroDVD)`, `MPL2`, `TMP`, `TTML`, `SAMI`"))
    st.write(_tr(ui_lang, "不支持：`SUP`、`IDX/SUB` 等图片字幕", "非対応: `SUP`, `IDX/SUB` など画像字幕", "Excluded: image subtitles such as `SUP`, `IDX/SUB`"))
    st.info(_tr(ui_lang, "运行命令后浏览器打开 `http://localhost:8501`。", "実行後にブラウザで `http://localhost:8501` を開いてください。", "Run command and open `http://localhost:8501` in your browser."))
    st.markdown("</section>", unsafe_allow_html=True)


def _validate_provider_settings(settings: ProviderSettings, spec, *, require_model: bool = True, ui_lang: str = "zh") -> str | None:
    if spec.api_key_required and not settings.api_key:
        return _tr(ui_lang, "请填写当前 Provider 的 API 密钥。", "このプロバイダーの API キーを入力してください。", "Please enter the API key for this provider.")
    if require_model and spec.family == "llm" and not settings.model_name.strip():
        return _tr(ui_lang, "LLM Provider 必须填写模型名。", "LLM プロバイダーではモデル名が必須です。", "Model name is required for LLM providers.")
    if settings.provider_id == "custom-openai" and not (settings.base_url or "").strip():
        return _tr(ui_lang, "自定义 OpenAI 兼容通道必须填写 Base URL。", "カスタム OpenAI 互換では Base URL が必須です。", "Base URL is required for custom OpenAI-compatible provider.")
    if spec.family == "deepl" and not (settings.base_url or "").strip():
        return _tr(ui_lang, "DeepL 必须填写 API URL。", "DeepL では API URL が必須です。", "DeepL API URL is required.")
    return None


def _build_request_signature(
    *,
    file_hash: str,
    source_language: str,
    target_language: str,
    provider_id: str,
    model_name: str,
    base_url: str,
    glossary_hash: str,
) -> str:
    raw = "|".join(
        [
            file_hash,
            source_language,
            target_language,
            provider_id,
            model_name,
            base_url,
            glossary_hash,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _provider_secret_id(provider_id: str) -> str:
    return f"provider::{provider_id}::api_key"


def _reset_result_if_request_changed(request_signature: str) -> None:
    result = st.session_state.get("translation_result")
    if result and result.get("request_signature") != request_signature:
        st.session_state.pop("translation_result", None)


def _get_cached_document(file_name: str, file_bytes: bytes, file_hash: str, encoding: str | None = None):
    cache = st.session_state.get("document_cache", {})
    cache_key = (file_name, file_hash, encoding)
    if cache_key in cache:
        return cache[cache_key], None
    try:
        document = load_subtitle_document(file_name, file_bytes, encoding)
    except SubtitleIOError as exc:
        return None, str(exc)
    cache[cache_key] = document
    if len(cache) > 3:
        first_key = next(iter(cache))
        cache.pop(first_key, None)
    st.session_state["document_cache"] = cache
    return document, None


def _get_cached_glossary(file_bytes: bytes, glossary_hash: str):
    cache = st.session_state.get("glossary_cache", {})
    if glossary_hash in cache:
        return cache[glossary_hash], None
    try:
        terms = parse_glossary_csv(file_bytes)
    except GlossaryFormatError as exc:
        return [], str(exc)
    cache[glossary_hash] = terms
    if len(cache) > 5:
        first_key = next(iter(cache))
        cache.pop(first_key, None)
    st.session_state["glossary_cache"] = cache
    return terms, None

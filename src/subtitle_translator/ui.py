from __future__ import annotations

import copy
import hashlib

import streamlit as st

from subtitle_translator.config import AppConfig
from subtitle_translator.glossary import GlossaryFormatError, parse_glossary_csv
from subtitle_translator.memory import TranslationMemory
from subtitle_translator.subtitle_io import (
    IMAGE_SUBTITLE_EXTENSIONS,
    SubtitleIOError,
    export_subtitle_document,
    format_timestamp,
    load_subtitle_document,
)
from subtitle_translator.translator import (
    ProviderSettings,
    TranslationError,
    TranslationService,
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
        --bg-0: #f8fafc;
        --bg-1: #f1f5f9;
        --card-bg: rgba(255, 255, 255, 0.90);
        --ink-1: #0f172a;
        --ink-2: #334155;
        --accent-a: #0ea5e9;
        --accent-b: #14b8a6;
        --border: #dbe2ea;
        --shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }

    .stApp {
        background:
            radial-gradient(circle at 15% -5%, rgba(14, 165, 233, 0.18), transparent 35%),
            radial-gradient(circle at 90% 0%, rgba(20, 184, 166, 0.16), transparent 35%),
            linear-gradient(180deg, var(--bg-0), var(--bg-1));
    }

    .hero {
        border-radius: 20px;
        padding: 26px 28px;
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.97), rgba(8, 47, 73, 0.97));
        color: #f8fafc;
        box-shadow: var(--shadow);
        margin-bottom: 14px;
    }

    .hero h1 {
        margin: 0 0 6px 0;
        letter-spacing: 0.2px;
    }

    .hero p {
        margin: 0;
        opacity: 0.9;
    }

    .card {
        border-radius: 18px;
        border: 1px solid var(--border);
        background: var(--card-bg);
        box-shadow: var(--shadow);
        padding: 14px 16px;
        margin-bottom: 10px;
    }

    .metric-chip {
        display: inline-block;
        border-radius: 999px;
        border: 1px solid #bfdbfe;
        background: #eff6ff;
        color: #1d4ed8;
        padding: 4px 12px;
        font-size: 12px;
        margin-right: 8px;
    }

    .kicker {
        color: var(--ink-2);
        font-size: 13px;
        margin-bottom: 8px;
    }
</style>
"""


def _tr(ui_lang: str, zh_text: str, ja_text: str) -> str:
    return zh_text if ui_lang == "zh" else ja_text


def run() -> None:
    st.set_page_config(page_title="字幕翻译器", page_icon="ST", layout="wide")
    st.markdown(THEME_CSS, unsafe_allow_html=True)
    default_ui_lang = st.session_state.get("ui_lang", "zh")
    switch_cols = st.columns([4, 1.1])
    with switch_cols[1]:
        ui_lang_label = st.selectbox(
            "界面语言 / UI",
            ["中文", "日本語"],
            index=0 if default_ui_lang == "zh" else 1,
            key="ui_lang_select",
        )
    ui_lang = "zh" if ui_lang_label == "中文" else "ja"
    st.session_state["ui_lang"] = ui_lang

    hero_title = _tr(ui_lang, "字幕翻译工作台", "字幕翻訳スタジオ")
    hero_desc = _tr(
        ui_lang,
        "本地网页工具（localhost），支持多 Provider API，翻译已有字幕并自动处理编码回写。",
        "localhost で動くローカルWebツール。複数プロバイダーAPIで既存字幕を翻訳し、文字コードも安全に再出力します。",
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

    provider_spec, provider_settings = _render_provider_panel(config, ui_lang)

    uploaded_file = st.file_uploader(
        _tr(ui_lang, "上传字幕文件", "字幕ファイルをアップロード"),
        type=SUPPORTED_EXTENSIONS,
        help=_tr(
            ui_lang,
            "仅支持文本字幕，.sup / .idx 等图片字幕不会处理。",
            "テキスト字幕のみ対応。 .sup / .idx など画像字幕は対象外です。",
        ),
    )
    if uploaded_file is None:
        _render_support_notes(ui_lang)
        return

    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    if len(file_bytes) > config.max_file_size_bytes:
        st.error(_tr(ui_lang, "文件超过当前 MVP 大小限制。", "ファイルサイズが現在のMVP上限を超えています。"))
        return

    if any(uploaded_file.name.lower().endswith(ext) for ext in IMAGE_SUBTITLE_EXTENSIONS):
        st.error(_tr(ui_lang, "图片字幕格式不在此项目支持范围。", "画像字幕形式はこのプロジェクトではサポート対象外です。"))
        return

    document, parse_error = _get_cached_document(uploaded_file.name, file_bytes, file_hash)
    if parse_error:
        st.error(parse_error)
        return
    assert document is not None

    source_col, target_col = st.columns([1, 1])
    source_options = SOURCE_LANGUAGE_OPTIONS[ui_lang]
    target_options = TARGET_LANGUAGE_OPTIONS[ui_lang]
    target_values = list(target_options.values())
    target_default_index = target_values.index("zh") if "zh" in target_values else 0
    with source_col:
        source_label = st.selectbox(_tr(ui_lang, "源语言", "入力言語"), list(source_options), index=0)
    with target_col:
        target_label = st.selectbox(
            _tr(ui_lang, "目标语言", "出力言語"),
            list(target_options),
            index=target_default_index,
        )

    glossary_upload = st.file_uploader(_tr(ui_lang, "可选术语表 CSV", "任意の用語集 CSV"), type=["csv"])
    glossary_hash = hashlib.sha256(glossary_upload.getvalue()).hexdigest() if glossary_upload is not None else "no-glossary"

    glossary_terms = []
    if glossary_upload is not None:
        glossary_terms, glossary_error = _get_cached_glossary(glossary_upload.getvalue(), glossary_hash)
        if glossary_error:
            st.error(glossary_error)
            return
        st.success(_tr(ui_lang, f"术语表已载入：{len(glossary_terms)} 条", f"用語集を読み込みました: {len(glossary_terms)} 件"))

    _render_file_summary(document, ui_lang)

    request_signature = _build_request_signature(
        file_hash=file_hash,
        source_language=source_options[source_label],
        target_language=target_options[target_label],
        provider_id=provider_spec.provider_id,
        model_name=provider_settings.model_name,
        base_url=provider_settings.base_url or "",
        glossary_hash=glossary_hash,
    )
    _reset_result_if_request_changed(request_signature)

    missing_requirements = _validate_provider_settings(provider_settings, provider_spec, require_model=True)
    if missing_requirements:
        st.warning(missing_requirements)

    with st.container(border=True):
        start_disabled = bool(missing_requirements)
        start_clicked = st.button(_tr(ui_lang, "开始翻译", "翻訳開始"), type="primary", disabled=start_disabled)
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

    result = st.session_state.get("translation_result")
    if result and result.get("request_signature") == request_signature:
        _render_result(result["document"], result["exported"], result["provider_name"], ui_lang)


def _render_provider_panel(config: AppConfig, ui_lang: str):
    specs = get_provider_specs()
    label_to_id = {spec.display_name: spec.provider_id for spec in specs}

    with st.sidebar:
        st.markdown(f"### {_tr(ui_lang, 'Provider 设置', 'プロバイダー設定')}")
        selected_label = st.selectbox(_tr(ui_lang, "预设", "プリセット"), list(label_to_id), index=2)
        provider_id = label_to_id[selected_label]
        spec = get_provider_spec(provider_id)
        st.caption(spec.help_text)
        if spec.docs_url:
            st.link_button(_tr(ui_lang, "打开 API 文档", "API ドキュメントを開く"), spec.docs_url, use_container_width=True)

        st.markdown("---")
        st.markdown(f"`DB`: {config.db_path}")
        st.markdown(f"`Batch`: {config.batch_size}")
        st.markdown(f"`Max size`: {config.max_file_size_bytes // (1024 * 1024)} MB")

        api_key_default = config.get(spec.api_key_env_var) if spec.api_key_env_var else ""
        api_key_label = _tr(ui_lang, "API 密钥", "API キー") if spec.api_key_required else _tr(ui_lang, "API 密钥（可选）", "API キー（任意）")
        api_key_help = None if spec.api_key_required else _tr(ui_lang, "该通道可无密钥运行。", "このプロバイダーはキーなしでも実行できます。")
        api_key = st.text_input(
            api_key_label,
            value=api_key_default,
            type="password",
            key=f"{provider_id}_api_key",
            help=api_key_help,
        )

        model_name = ""
        base_url = ""

        if spec.family == "llm":
            model_default = config.get(spec.model_env_var, spec.default_model) or spec.default_model
            base_default = config.get(spec.base_url_env_var, spec.default_base_url) or spec.default_base_url
            base_url = st.text_input("Base URL", value=base_default, key=f"{provider_id}_base_url")

            model_cache_key = _build_model_cache_key(provider_id, api_key, base_url)
            model_cache = st.session_state.get("provider_model_cache", {})
            fetched_models = model_cache.get(model_cache_key, [])
            if fetched_models:
                custom_label = _tr(ui_lang, "自定义输入...", "手動入力...")
                selector_options = fetched_models + [custom_label]
                selected_default = model_default if model_default in fetched_models else custom_label
                selected_model = st.selectbox(
                    _tr(ui_lang, "模型（已从接口获取）", "モデル（API 取得済み）"),
                    selector_options,
                    index=selector_options.index(selected_default),
                    key=f"{provider_id}_model_selector",
                )
                if selected_model == custom_label:
                    model_name = st.text_input(_tr(ui_lang, "模型名（手动）", "モデル名（手動）"), value=model_default, key=f"{provider_id}_model")
                else:
                    model_name = selected_model
                st.caption(_tr(ui_lang, f"已获取 {len(fetched_models)} 个模型。", f"{len(fetched_models)} 件のモデルを取得済み。"))
            else:
                st.info(
                    _tr(
                        ui_lang,
                        "先点击“测试连接”获取实时模型列表；你也可以先手动输入模型名。",
                        "まず「接続テスト」で最新モデル一覧を取得してください。先に手動入力も可能です。",
                    )
                )
                model_name = st.text_input(_tr(ui_lang, "模型名（手动）", "モデル名（手動）"), value=model_default, key=f"{provider_id}_model")
        elif spec.family == "deepl":
            base_default = config.get(spec.base_url_env_var, spec.default_base_url) or spec.default_base_url
            base_url = st.text_input(_tr(ui_lang, "DeepL API URL", "DeepL API URL"), value=base_default, key=f"{provider_id}_base_url")

        settings = ProviderSettings(
            provider_id=provider_id,
            api_key=api_key,
            model_name=model_name,
            base_url=base_url or None,
            timeout_seconds=config.request_timeout_seconds,
        )

        test_disabled = bool(_validate_provider_settings(settings, spec, require_model=False))
        if st.button(_tr(ui_lang, "测试连接", "接続テスト"), use_container_width=True, disabled=test_disabled):
            with st.spinner("Testing connection..."):
                ok, message, elapsed_ms, models = probe_provider_connection(settings)
            if ok:
                if spec.family == "llm" and models:
                    model_cache = st.session_state.get("provider_model_cache", {})
                    model_cache[_build_model_cache_key(provider_id, api_key, base_url)] = models
                    st.session_state["provider_model_cache"] = model_cache
                    st.success(_tr(ui_lang, f"{message} 已载入 {len(models)} 个模型。({elapsed_ms:.0f} ms)", f"{message} {len(models)} 件のモデルを読み込みました。({elapsed_ms:.0f} ms)"))
                else:
                    st.success(f"{message} ({elapsed_ms:.0f} ms)")
            else:
                st.error(_tr(ui_lang, f"连接失败：{message} ({elapsed_ms:.0f} ms)", f"接続失敗: {message} ({elapsed_ms:.0f} ms)"))

    return spec, settings


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
    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    progress_bar = st.progress(0.0, text=_tr(ui_lang, "准备中...", "準備中..."))

    def on_progress(completed: int, total: int, message: str) -> None:
        ratio = completed / total if total else 1.0
        progress_bar.progress(ratio, text=_tr(ui_lang, f"{completed}/{total} 已完成", f"{completed}/{total} 完了"))
        status_placeholder.info(message)

    try:
        provider = build_translator_provider(provider_settings)
        working_doc = copy.deepcopy(document)
        with TranslationMemory(config.db_path) as memory:
            service = TranslationService(provider, memory, batch_size=config.batch_size)
            translated_document = service.translate_document(
                working_doc,
                source_language=source_language,
                target_language=target_language,
                glossary=glossary_terms,
                progress_callback=on_progress,
            )
        exported = export_subtitle_document(translated_document, target_language=target_language)
    except (TranslationError, SubtitleIOError) as exc:
        progress_placeholder.empty()
        st.error(str(exc))
        return

    progress_placeholder.success(_tr(ui_lang, "翻译完成。", "翻訳が完了しました。"))
    st.session_state["translation_result"] = {
        "request_signature": request_signature,
        "document": translated_document,
        "exported": exported,
        "provider_name": provider_spec.display_name,
    }


def _render_result(translated_document, exported, provider_name: str, ui_lang: str) -> None:
    st.subheader(_tr(ui_lang, "预览", "プレビュー"))
    st.caption(_tr(ui_lang, f"Provider: {provider_name}", f"プロバイダー: {provider_name}"))

    rows = [
        {
            "#": segment.index + 1,
            "Start": format_timestamp(segment.start_ms),
            "End": format_timestamp(segment.end_ms),
            "Source": segment.plain_text,
            "Translation": segment.translated_text or "",
        }
        for segment in translated_document.segments
        if segment.is_translatable
    ]
    max_rows = len(rows)
    default_rows = min(300, max_rows) if max_rows > 0 else 0
    preview_count = st.slider(_tr(ui_lang, "预览行数", "プレビュー行数"), min_value=0, max_value=max_rows, value=default_rows, step=50)
    st.dataframe(rows[:preview_count], use_container_width=True, height=460)

    st.download_button(
        label=_tr(ui_lang, f"下载 {exported.file_name}", f"ダウンロード {exported.file_name}"),
        data=exported.content,
        file_name=exported.file_name,
        mime="text/plain",
    )
    st.caption(_tr(ui_lang, f"导出编码：`{exported.encoding}`", f"出力エンコード: `{exported.encoding}`"))


def _render_file_summary(document, ui_lang: str) -> None:
    st.markdown('<section class="card">', unsafe_allow_html=True)
    st.markdown(f'<p class="kicker">{_tr(ui_lang, "文件检测结果", "検出されたファイル情報")}</p>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <span class="metric-chip">{_tr(ui_lang, "格式", "形式")}: {document.format}</span>
        <span class="metric-chip">{_tr(ui_lang, "编码", "文字コード")}: {document.encoding}</span>
        <span class="metric-chip">{_tr(ui_lang, "换行", "改行")}: {repr(document.newline)}</span>
        <span class="metric-chip">{_tr(ui_lang, "片段数", "セグメント数")}: {sum(1 for s in document.segments if s.is_translatable)}</span>
        """,
        unsafe_allow_html=True,
    )
    for warning in document.warnings:
        st.warning(warning)
    st.markdown("</section>", unsafe_allow_html=True)


def _render_support_notes(ui_lang: str) -> None:
    st.markdown('<section class="card">', unsafe_allow_html=True)
    st.markdown(f"### {_tr(ui_lang, '支持字幕类型', '対応字幕形式')}")
    st.write(_tr(ui_lang, "正式支持：`SRT`、`ASS`、`SSA`、`VTT`", "正式対応: `SRT`, `ASS`, `SSA`, `VTT`"))
    st.write(_tr(ui_lang, "尽力支持：`SUB (MicroDVD)`、`MPL2`、`TMP`、`TTML`、`SAMI`", "ベストエフォート: `SUB (MicroDVD)`, `MPL2`, `TMP`, `TTML`, `SAMI`"))
    st.write(_tr(ui_lang, "不支持：`SUP`、`IDX/SUB` 等图片字幕", "非対応: `SUP`, `IDX/SUB` など画像字幕"))
    st.info(_tr(ui_lang, "运行命令后浏览器打开 `http://localhost:8501`。", "実行後にブラウザで `http://localhost:8501` を開いてください。"))
    st.markdown("</section>", unsafe_allow_html=True)


def _validate_provider_settings(settings: ProviderSettings, spec, *, require_model: bool = True) -> str | None:
    if spec.api_key_required and not settings.api_key:
        return "Please provide an API key for the selected provider."
    if require_model and spec.family == "llm" and not settings.model_name.strip():
        return "Model is required for LLM providers."
    if settings.provider_id == "custom-openai" and not (settings.base_url or "").strip():
        return "Base URL is required for custom OpenAI-compatible provider."
    if spec.family == "deepl" and not (settings.base_url or "").strip():
        return "DeepL API URL is required."
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


def _build_model_cache_key(provider_id: str, api_key: str, base_url: str) -> str:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12] if api_key else "no-key"
    return "|".join([provider_id, base_url.strip(), key_hash])


def _reset_result_if_request_changed(request_signature: str) -> None:
    result = st.session_state.get("translation_result")
    if result and result.get("request_signature") != request_signature:
        st.session_state.pop("translation_result", None)


def _get_cached_document(file_name: str, file_bytes: bytes, file_hash: str):
    cache = st.session_state.get("document_cache", {})
    if file_hash in cache:
        return cache[file_hash], None
    try:
        document = load_subtitle_document(file_name, file_bytes)
    except SubtitleIOError as exc:
        return None, str(exc)
    cache[file_hash] = document
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

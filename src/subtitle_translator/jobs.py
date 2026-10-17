"""Background translation with atomic, credential-free checkpoints."""
import copy
import json
import threading
import time
from pathlib import Path

from subtitle_translator.memory import TranslationMemory
from subtitle_translator.translator import TranslationCancelled, TranslationService, build_translator_provider

_RUNNING = {}
_REGISTRY_LOCK = threading.Lock()


def save_checkpoint(path, document, failures):
    import tempfile
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'translated': {str(s.index): s.translated_raw_text for s in document.segments
                              if s.translated_raw_text is not None}, 'failures': failures}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, encoding='utf-8', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def restore_checkpoint(path, document):
    if not path.exists():
        return document, {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    for index, raw in payload.get('translated', {}).items():
        segment = document.segments[int(index)]
        document.subtitles[int(index)].text = raw
        segment.translated_raw_text = raw
        segment.translated_text = document.subtitles[int(index)].plaintext
    return document, {int(k): v for k, v in payload.get('failures', {}).items()}


class TranslationJob:
    def __init__(self, document, settings, config, source, target, glossary, checkpoint):
        self._document = copy.deepcopy(document)
        self._settings = settings
        self._config = config
        self._source, self._target = source, target
        self._glossary = glossary
        self._checkpoint = Path(checkpoint)
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._last_publish = 0.0
        self._state = {'status': 'running', 'completed': 0, 'total': 0,
                       'document': copy.deepcopy(document), 'failures': {}, 'error': '', 'cancelling': False}
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        key = str(self._checkpoint.resolve())
        with _REGISTRY_LOCK:
            existing = _RUNNING.get(key)
            if existing and existing.thread.is_alive():
                return existing
            # Reload after taking the registry lock so a just-finished job's
            # checkpoint cannot be overwritten by a stale browser snapshot.
            self._document, _ = restore_checkpoint(self._checkpoint, self._document)
            _RUNNING[key] = self
            self.thread.start()
        return self

    def cancel(self):
        self._cancel.set()
        with self._lock:
            self._state['cancelling'] = True

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _publish(self, service, completed=None, total=None):
        now = time.monotonic()
        if completed is not None:
            with self._lock:
                self._state.update(completed=completed, total=total)
            if completed != total and now - self._last_publish < 0.5:
                return
        self._last_publish = now
        with self._lock:
            self._state.update(document=copy.deepcopy(self._document), failures=dict(service.failures))
            if completed is not None:
                self._state.update(completed=completed, total=total)
        save_checkpoint(self._checkpoint, self._document, service.failures)

    def _run(self):
        provider = None
        try:
            provider = build_translator_provider(self._settings)
            with TranslationMemory(self._config.db_path) as memory:
                service = TranslationService(provider, memory, batch_size=self._config.batch_size,
                                             max_batch_chars=getattr(self._config, 'max_batch_chars', 6000))
                try:
                    service.translate_document(
                        self._document, source_language=self._source, target_language=self._target,
                        glossary=self._glossary, cancel_requested=self._cancel.is_set,
                        progress_callback=lambda done, total, message: self._publish(service, done, total),
                    )
                    status = 'failed' if service.failures else 'completed'
                except TranslationCancelled:
                    status = 'cancelled'
                finally:
                    self._publish(service)
            with self._lock:
                self._state['status'] = status
        except Exception as exc:
            with self._lock:
                self._state.update(status='failed', error=str(exc))
        finally:
            try:
                if provider and hasattr(provider, '_client'):
                    provider._client.close()
            finally:
                self._settings = None
                with _REGISTRY_LOCK:
                    key = str(self._checkpoint.resolve())
                    if _RUNNING.get(key) is self:
                        _RUNNING.pop(key, None)

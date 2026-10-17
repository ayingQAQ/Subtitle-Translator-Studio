"""Background translation with atomic, credential-free checkpoints."""
import copy
import json
import threading
from pathlib import Path

from subtitle_translator.memory import TranslationMemory
from subtitle_translator.translator import TranslationCancelled, TranslationService, build_translator_provider


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
        self._state = {'status': 'running', 'completed': 0, 'total': 0,
                       'document': copy.deepcopy(document), 'failures': {}, 'error': ''}
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def cancel(self):
        self._cancel.set()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _publish(self, service, completed=None, total=None):
        with self._lock:
            self._state.update(document=copy.deepcopy(self._document), failures=dict(service.failures))
            if completed is not None:
                self._state.update(completed=completed, total=total)
        self._checkpoint.parent.mkdir(parents=True, exist_ok=True)
        payload = {'translated': {str(s.index): s.translated_raw_text for s in self._document.segments
                                  if s.translated_raw_text is not None},
                   'failures': service.failures}
        temporary = self._checkpoint.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self._checkpoint)

    def _run(self):
        provider = None
        try:
            provider = build_translator_provider(self._settings)
            with TranslationMemory(self._config.db_path) as memory:
                service = TranslationService(provider, memory, batch_size=self._config.batch_size)
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
            if provider and hasattr(provider, '_client'):
                provider._client.close()
            self._settings = None

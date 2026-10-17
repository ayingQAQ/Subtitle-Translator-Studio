import hashlib
import json
from dataclasses import asdict


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def connection_identity(settings) -> str:
    return digest([settings.provider_id, (settings.base_url or '').strip().rstrip('/'),
                   digest(settings.api_key.strip())])


def memory_identity(provider, glossary, document) -> str:
    context = [segment.raw_text for segment in document.segments] if hasattr(provider, 'context') else None
    return provider.provider_name + ':' + digest({
        'endpoint': (getattr(provider, 'base_url', None) or getattr(provider, 'endpoint', '')).rstrip('/'),
        'glossary': [asdict(term) for term in glossary], 'prompt': 'subtitle-v2', 'context': context,
    })

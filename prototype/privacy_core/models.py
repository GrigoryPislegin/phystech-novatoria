"""Public model artifacts, pinned by digest. Runtime never downloads weights."""
import hashlib
from pathlib import Path

MODELS = {
    'slovnet_ner_news_v1.tar': (
        'https://storage.yandexcloud.net/natasha-slovnet/packs/slovnet_ner_news_v1.tar',
        '16c3343a6572ddf0e2b2fc1923113de15a7f5ca5bde90e780dd590418665603e', 2_385_920),
    'navec_news_v1_1B_250K_300d_100q.tar': (
        'https://storage.yandexcloud.net/natasha-navec/packs/navec_news_v1_1B_250K_300d_100q.tar',
        'f07270833d78523edc5781538d67038e95b43975e4a7ae757c693b687f9cbfca', 26_634_240),
}


def verify(path, name):
    path = Path(path)
    _, digest, size = MODELS[name]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise RuntimeError('privacy_models_missing_or_invalid')
    with path.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != digest:
            raise RuntimeError('privacy_models_missing_or_invalid')
    return path


def load(directory):
    paths = [verify(Path(directory)/name, name) for name in MODELS]
    # Imported only after artifact validation, with no core/DB/network dependency.
    from navec import Navec
    from slovnet import NER
    ner = NER.load(str(paths[0]))
    ner.navec(Navec.load(str(paths[1])))
    return ner

from pathlib import Path

import pytest
from google.api_core.exceptions import PreconditionFailed

from kis_portfolio.adapters.outbound.gcs_object_store import GCSObjectStore


class FakeBlob:
    def __init__(self, name, objects):
        self.name = name
        self.objects = objects

    def upload_from_string(self, payload, **kwargs):
        if self.name in self.objects:
            raise PreconditionFailed("already exists")
        assert kwargs["if_generation_match"] == 0
        self.objects[self.name] = payload

    def download_to_filename(self, path):
        Path(path).write_bytes(self.objects[self.name])


class FakeBucket:
    def __init__(self):
        self.objects = {}

    def blob(self, name):
        return FakeBlob(name, self.objects)


class FakeClient:
    def __init__(self):
        self.value = FakeBucket()

    def bucket(self, _):
        return self.value


def test_gcs_store_is_content_addressed_idempotent_and_verified(tmp_path):
    store = GCSObjectStore("private", client=FakeClient())
    first = store.put_bytes(b"payload", dataset_id="dataset.test", partition="2026-08-28", media_type="application/json")
    second = store.put_bytes(b"payload", dataset_id="dataset.test", partition="2026-08-28", media_type="application/json")
    assert first.created is True and second.created is False
    restored = store.download(first.uri, tmp_path / "value", expected_sha256=first.content_hash)
    assert restored.read_bytes() == b"payload"
    with pytest.raises(ValueError, match="SHA-256"):
        store.download(first.uri, tmp_path / "bad", expected_sha256="0" * 64)

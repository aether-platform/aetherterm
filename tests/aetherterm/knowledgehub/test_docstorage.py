"""Tests for LocalDocumentStorage."""

import pytest

from aetherterm.knowledgehub.docstorage import LocalDocumentStorage


@pytest.fixture
def store(tmp_path):
    return LocalDocumentStorage(str(tmp_path / "docs"))


def test_save_and_load(store):
    meta = store.save("t1", "doc1", "manual.pdf", b"PDF content", content_type="application/pdf")
    assert meta.document_id == "doc1"
    assert meta.tenant_id == "t1"
    assert meta.filename == "manual.pdf"
    assert meta.size_bytes == len(b"PDF content")
    assert meta.version == 1

    data = store.load("t1", "doc1")
    assert data == b"PDF content"


def test_load_nonexistent(store):
    assert store.load("t1", "nope") is None


def test_get_metadata(store):
    store.save("t1", "doc1", "file.txt", b"hello")
    meta = store.get_metadata("t1", "doc1")
    assert meta is not None
    assert meta.filename == "file.txt"


def test_get_metadata_nonexistent(store):
    assert store.get_metadata("t1", "nope") is None


def test_re_save_increments_version(store):
    store.save("t1", "doc1", "v1.txt", b"version 1")
    meta = store.save("t1", "doc1", "v2.txt", b"version 2")
    assert meta.version == 2
    assert meta.filename == "v2.txt"
    assert meta.size_bytes == len(b"version 2")

    data = store.load("t1", "doc1")
    assert data == b"version 2"


def test_save_with_tags(store):
    meta = store.save("t1", "doc1", "file.txt", b"data", tags=["policy", "hr"])
    assert meta.tags == ["policy", "hr"]


def test_update_metadata(store):
    store.save("t1", "doc1", "file.txt", b"data")
    updated = store.update_metadata("t1", "doc1", chunk_count=42)
    assert updated is not None
    assert updated.chunk_count == 42

    reloaded = store.get_metadata("t1", "doc1")
    assert reloaded.chunk_count == 42


def test_update_metadata_nonexistent(store):
    assert store.update_metadata("t1", "nope", chunk_count=1) is None


def test_delete(store):
    store.save("t1", "doc1", "file.txt", b"data")
    assert store.delete("t1", "doc1") is True
    assert store.load("t1", "doc1") is None
    assert store.get_metadata("t1", "doc1") is None


def test_delete_nonexistent(store):
    assert store.delete("t1", "nope") is False


def test_list_documents(store):
    for i in range(3):
        store.save("t1", f"doc{i}", f"file{i}.txt", f"content {i}".encode())
    docs = store.list_documents("t1")
    assert len(docs) == 3
    assert {d.document_id for d in docs} == {"doc0", "doc1", "doc2"}


def test_list_documents_empty(store):
    assert store.list_documents("nonexistent") == []


def test_list_documents_tenant_isolation(store):
    store.save("t1", "doc1", "file.txt", b"t1 data")
    store.save("t2", "doc2", "file.txt", b"t2 data")
    assert len(store.list_documents("t1")) == 1
    assert len(store.list_documents("t2")) == 1


def test_purge_tenant(store):
    for i in range(5):
        store.save("t1", f"doc{i}", f"file{i}.txt", b"data")
    store.save("t2", "other", "other.txt", b"data")

    count = store.purge_tenant("t1")
    assert count == 5
    assert store.list_documents("t1") == []
    assert len(store.list_documents("t2")) == 1  # t2 untouched


def test_purge_nonexistent_tenant(store):
    assert store.purge_tenant("nonexistent") == 0


def test_get_file_path(store):
    store.save("t1", "doc1", "report.pdf", b"pdf data")
    path = store.get_file_path("t1", "doc1")
    assert path is not None
    assert path.endswith(".pdf")


def test_get_file_path_nonexistent(store):
    assert store.get_file_path("t1", "nope") is None

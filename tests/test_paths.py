from context_engine.utils import paths


def test_to_posix_mount_from_windows():
    assert paths.to_posix_mount("C:\\corpus\\a.md") == "/mnt/c/corpus/a.md"
    assert paths.to_posix_mount("D:/x/y.md") == "/mnt/d/x/y.md"


def test_to_posix_mount_idempotent_on_posix():
    assert paths.to_posix_mount("/mnt/c/x/a.md") == "/mnt/c/x/a.md"


def test_to_windows_from_mount():
    assert paths.to_windows("/mnt/c/corpus/a.md") == "C:\\corpus\\a.md"
    # Git-bash style /c/... is also recognized.
    assert paths.to_windows("/c/x/a.md") == "C:\\x\\a.md"


def test_to_windows_from_windows():
    assert paths.to_windows("c:/x/a.md") == "C:\\x\\a.md"


def test_normalize_for_store_styles():
    win = "C:\\corpus\\a.md"
    assert paths.normalize_for_store(win, "posix") == "/mnt/c/corpus/a.md"
    assert paths.normalize_for_store("/mnt/c/corpus/a.md", "windows") == win


def test_normalize_for_store_unknown_style():
    import pytest
    with pytest.raises(ValueError):
        paths.normalize_for_store("x", "klingon")


def test_to_local_returns_str():
    # On any host, to_local should return a usable string for an absolute path.
    assert isinstance(paths.to_local("/mnt/c/x/a.md"), str)
    assert isinstance(paths.to_local("C:\\x\\a.md"), str)

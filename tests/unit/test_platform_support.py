import multiprocessing
import os
import threading
import time
from pathlib import Path

from core.file_lock import exclusive_file_lock, lock_file, unlock_file
from core.platform_support import find_libreoffice, user_config_dir, virtualenv_python


def _hold_process_lock(path, acquired, release):
    with exclusive_file_lock(path):
        acquired.set()
        release.wait(timeout=5)


def _acquire_process_lock(path, acquired):
    with exclusive_file_lock(path):
        acquired.set()


def test_user_config_dir_uses_native_windows_profile_location():
    result = user_config_dir(environ={"APPDATA": r"C:\Users\Person\AppData\Roaming"}, platform_name="nt")
    assert os.path.normpath(result) == os.path.normpath(r"C:\Users\Person\AppData\Roaming\aimaos")


def test_user_config_dir_honors_xdg_location():
    result = user_config_dir(environ={"XDG_CONFIG_HOME": "/srv/config"}, platform_name="posix")
    assert result == os.path.join("/srv/config", "aimaos")


def test_find_libreoffice_checks_common_windows_install_location(tmp_path):
    executable = tmp_path / "LibreOffice" / "program" / "soffice.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")

    result = find_libreoffice(
        environ={"ProgramFiles": str(tmp_path)},
        platform_name="nt",
        which=lambda _name: None,
    )

    assert result == str(executable)


def test_find_libreoffice_prefers_path_lookup():
    result = find_libreoffice(
        environ={},
        platform_name="nt",
        which=lambda name: r"C:\Tools\soffice.exe" if name == "soffice" else None,
    )
    assert result == r"C:\Tools\soffice.exe"


def test_virtualenv_python_uses_host_layout(tmp_path):
    result = Path(virtualenv_python(tmp_path))
    expected = Path(".venv/Scripts/python.exe") if os.name == "nt" else Path(".venv/bin/python3")
    assert result == tmp_path / expected


def test_text_mode_lock_api_supports_existing_state_mutators(tmp_path):
    lock_path = tmp_path / "state.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        lock_file(handle)
        unlock_file(handle)


def test_exclusive_file_lock_serializes_threads(tmp_path):
    lock_path = tmp_path / "state.lock"
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()

    def first_worker():
        with exclusive_file_lock(lock_path):
            first_acquired.set()
            release_first.wait(timeout=2)

    def second_worker():
        first_acquired.wait(timeout=2)
        with exclusive_file_lock(lock_path):
            second_acquired.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    second.start()
    assert first_acquired.wait(timeout=2)
    time.sleep(0.1)
    assert not second_acquired.is_set()
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive()
    assert not second.is_alive()
    assert second_acquired.is_set()


def test_exclusive_file_lock_serializes_processes(tmp_path):
    context = multiprocessing.get_context("spawn")
    first_acquired = context.Event()
    release_first = context.Event()
    second_acquired = context.Event()
    lock_path = str(tmp_path / "state.lock")
    first = context.Process(target=_hold_process_lock, args=(lock_path, first_acquired, release_first))
    second = context.Process(target=_acquire_process_lock, args=(lock_path, second_acquired))
    first.start()
    assert first_acquired.wait(timeout=5)
    second.start()
    time.sleep(0.2)
    assert not second_acquired.is_set()
    release_first.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert first.exitcode == 0
    assert second.exitcode == 0
    assert second_acquired.is_set()

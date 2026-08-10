import os
import subprocess

import pytest

from slackbackup import channel_lock


def _dead_pid() -> int:
    """A pid guaranteed not to be alive right now: spawn and wait it out."""
    proc = subprocess.run(["true"])
    return proc.pid if hasattr(proc, "pid") else _spawn_and_wait()


def _spawn_and_wait() -> int:
    proc = subprocess.Popen(["true"])
    pid = proc.pid
    proc.wait()
    return pid


def test_acquire_and_release_removes_lock_file(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    with channel_lock.channel_lock(channel_dir):
        assert channel_lock.lock_path_for(channel_dir).exists()
    assert not channel_lock.lock_path_for(channel_dir).exists()


def test_lock_file_records_current_pid(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    with channel_lock.channel_lock(channel_dir):
        content = channel_lock.lock_path_for(channel_dir).read_text()
        assert content.splitlines()[0] == str(os.getpid())


def test_second_acquire_while_held_raises(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    with channel_lock.channel_lock(channel_dir):
        with pytest.raises(channel_lock.ChannelLockedError) as excinfo:
            with channel_lock.channel_lock(channel_dir):
                pass
    assert str(os.getpid()) in str(excinfo.value)


def test_lock_released_even_if_block_raises(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    with pytest.raises(ValueError):
        with channel_lock.channel_lock(channel_dir):
            raise ValueError("boom")
    assert not channel_lock.lock_path_for(channel_dir).exists()
    # A fresh acquire must succeed - nothing left dangling.
    with channel_lock.channel_lock(channel_dir):
        pass


def test_stale_lock_from_dead_pid_is_reclaimed(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    channel_dir.mkdir(parents=True)
    dead_pid = _spawn_and_wait()
    channel_lock.lock_path_for(channel_dir).write_text(f"{dead_pid}\n2020-01-01T00:00:00Z\n")

    with channel_lock.channel_lock(channel_dir):
        content = channel_lock.lock_path_for(channel_dir).read_text()
        assert content.splitlines()[0] == str(os.getpid())


def test_corrupt_lock_file_is_treated_as_stale(tmp_path):
    channel_dir = tmp_path / "f3test" / "general"
    channel_dir.mkdir(parents=True)
    channel_lock.lock_path_for(channel_dir).write_text("not-a-pid\n")

    with channel_lock.channel_lock(channel_dir):
        assert channel_lock.lock_path_for(channel_dir).read_text().splitlines()[0] == str(os.getpid())


def test_release_does_not_clobber_a_lock_taken_by_someone_else(tmp_path):
    # Simulates: our lock's finally-block runs after something else has
    # already reclaimed the (by-then-stale) lock and is using it - must not
    # delete a lock that isn't ours.
    channel_dir = tmp_path / "f3test" / "general"
    with channel_lock.channel_lock(channel_dir):
        lock_path = channel_lock.lock_path_for(channel_dir)
        lock_path.write_text("999999999\nsomeone-else\n")
    # Our context manager's cleanup must not have removed the other holder's
    # lock file.
    assert channel_lock.lock_path_for(channel_dir).exists()

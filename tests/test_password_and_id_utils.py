"""cloudoll.utils.password and cloudoll.utils.snowflake are the utilities an
application reaches for when it stores a secret or hands out an order id, so their
guarantees (and their limits) are pinned here rather than assumed."""

import hashlib
import secrets
import string
import sys
import threading
import time

import pytest
from cryptography.fernet import Fernet, InvalidToken

from cloudoll.utils.password import CryFernet, generator
from cloudoll.utils.password import hash as keyed_hash
from cloudoll.utils.snowflake import IdWorker


def test_fernet_round_trips_text():
    crypt = CryFernet(Fernet.generate_key().decode())
    token = crypt.encrypt("密码123")
    assert isinstance(token, str)
    assert crypt.decrypt(token) == "密码123"
    assert crypt.decrypt(crypt.encrypt("")) == ""
    # A fresh timestamp and IV per call, so the same value never repeats a token.
    assert crypt.encrypt("同一句") != crypt.encrypt("同一句")


def test_fernet_needs_a_key_and_only_accepts_its_own_tokens():
    with pytest.raises(ValueError, match="url-safe base64"):
        CryFernet("too-short")
    crypt = CryFernet(Fernet.generate_key().decode())
    other = CryFernet(Fernet.generate_key().decode())
    token = crypt.encrypt("payload")
    with pytest.raises(InvalidToken):
        other.decrypt(token)
    with pytest.raises(InvalidToken):
        crypt.decrypt(token[:-2] + "AA")


def test_keyed_hash_is_sha256_of_value_then_key():
    assert keyed_hash("abc", "") == hashlib.sha256(b"abc").hexdigest()
    assert keyed_hash("abc", "pepper") == hashlib.sha256(b"abcpepper").hexdigest()
    # A missing key reads back as no pepper instead of raising on None.
    assert keyed_hash("abc", None) == keyed_hash("abc", "")
    digest = keyed_hash("张三", "pepper")
    assert len(digest) == 64 and digest == digest.lower()
    assert keyed_hash("张三", "other") != digest
    assert keyed_hash("张三", "pepper") == digest


def test_generator_builds_a_callable_alphabet(monkeypatch):
    drawn = []
    monkeypatch.setattr(
        secrets, "choice", lambda alphabet: (drawn.append(alphabet), alphabet[0])[1]
    )
    generator()()
    assert drawn[-1] == string.ascii_letters + string.digits
    generator(8, True)()
    assert drawn[-1] == string.ascii_letters + string.digits + string.punctuation


def test_generator_size_and_randomness():
    make = generator(24)
    values = [make() for _ in range(50)]
    assert {len(value) for value in values} == {24}
    assert len(set(values)) == len(values)
    assert set(generator(64)()) <= set(string.ascii_letters + string.digits)
    assert [len(generator(size)()) for size in (4, 16)] == [4, 16]


def test_id_worker_bits_name_the_worker():
    worker = IdWorker(worker_id=3, datacenter_id=5)
    before = int(time.time() * 1000)
    value = worker.next_id()
    after = int(time.time() * 1000)
    assert value & 0xFFF == 0
    assert (value >> 12) & 0x1F == 3
    assert (value >> 17) & 0x1F == 5
    assert before <= (value >> 22) + worker.twepoch <= after
    # Fits the BigInt column an application would store it in.
    assert 0 < value < 2**63


def test_id_worker_ids_increase_and_stay_unique():
    worker = IdWorker(worker_id=7, datacenter_id=9)
    values = [worker.next_id() for _ in range(5000)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_id_worker_waits_for_the_next_millisecond_when_the_sequence_runs_out(
    monkeypatch,
):
    worker = IdWorker(worker_id=1, datacenter_id=1)
    now = int(time.time() * 1000)
    calls = {"count": 0}

    def frozen_clock() -> int:
        # A clock that does not move on its own, so the only way forward is the
        # worker waiting for the next millisecond after its 4096 sequence slots.
        calls["count"] += 1
        return now if calls["count"] <= 4097 else now + 1

    monkeypatch.setattr(worker, "_time_gen", frozen_clock)
    values = [worker.next_id() for _ in range(4096)]
    assert len(set(values)) == 4096
    following = worker.next_id()
    assert following > values[-1]
    assert (following >> 22) == (values[-1] >> 22) + 1
    assert following & 0xFFF == 0


def test_id_worker_is_thread_safe():
    worker = IdWorker(worker_id=1, datacenter_id=1)
    produced: list[int] = []
    lock = threading.Lock()

    def generate() -> None:
        batch = [worker.next_id() for _ in range(400)]
        with lock:
            produced.extend(batch)

    # Force thread switches inside the id calculation, which is where an
    # unguarded sequence and timestamp update would lose an id.
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.000001)
    try:
        threads = [threading.Thread(target=generate) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(original_interval)
    assert len(produced) == 1600
    assert len(set(produced)) == len(produced)


def test_id_worker_rejects_an_out_of_range_identity():
    for worker_id, datacenter_id in ((32, 0), (-1, 0), (0, 32), (0, -1)):
        with pytest.raises(ValueError, match="must be between 0 and 31"):
            IdWorker(worker_id=worker_id, datacenter_id=datacenter_id)


def test_id_worker_refuses_to_run_the_clock_backwards():
    worker = IdWorker(worker_id=1, datacenter_id=1)
    worker.last_timestamp = int(time.time() * 1000) + 10_000
    with pytest.raises(Exception, match="Clock moved backwards"):
        worker.next_id()

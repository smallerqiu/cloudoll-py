"""Start isolated local MySQL/PostgreSQL instances, test, and stop them.

Never uses system service data directories. Requires server binaries locally.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-bin", default="/opt/homebrew/opt/mysql@8.4/bin")
    parser.add_argument("--postgres-bin", default="/opt/homebrew/opt/postgresql@16/bin")
    parser.add_argument("--python", action="append", dest="interpreters")
    parser.add_argument("--test-file", choices=["tests/integration/test_databases.py", "tests/integration/test_streaming.py"], default="tests/integration/test_databases.py")
    options = parser.parse_args()
    mysql_bin, pg_bin = Path(options.mysql_bin), Path(options.postgres_bin)
    # Do not resolve venv interpreter symlinks: that would bypass their packages.
    interpreters = [str(Path(p).absolute()) for p in options.interpreters or []] or [sys.executable]
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="cloudoll-db-") as directory:
        tmp = Path(directory)
        mysql_data, pg_data = tmp / "mysql", tmp / "pg"
        mysql_port, pg_port = free_port(), free_port()
        processes = []
        try:
            subprocess.run([str(mysql_bin / "mysqld"), "--no-defaults", "--initialize-insecure",
                            "--datadir=" + str(mysql_data)], check=True, timeout=90, capture_output=True)
            subprocess.run([str(pg_bin / "initdb"), "-D", str(pg_data), "-A", "trust", "-U", "cloudoll"],
                           check=True, timeout=60, capture_output=True)
            with (tmp / "servers.log").open("w+") as log:
                processes.append(subprocess.Popen([
                    str(mysql_bin / "mysqld"), "--no-defaults", "--datadir=" + str(mysql_data),
                    "--bind-address=127.0.0.1", "--port=" + str(mysql_port),
                    "--socket=" + str(tmp / "mysql.sock"), "--mysqlx=OFF",
                    "--pid-file=" + str(tmp / "mysql.pid"),
                ], stdout=log, stderr=log))
                processes.append(subprocess.Popen([
                    str(pg_bin / "postgres"), "-D", str(pg_data), "-h", "127.0.0.1",
                    "-p", str(pg_port), "-k", str(tmp),
                ], stdout=log, stderr=log))
                deadline = time.monotonic() + 45
                for port in (mysql_port, pg_port):
                    while True:
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=1):
                                break
                        except OSError:
                            if time.monotonic() > deadline or any(p.poll() is not None for p in processes):
                                log.seek(0)
                                raise RuntimeError(log.read())
                            time.sleep(0.2)
                subprocess.run([str(mysql_bin / "mysql"), "--no-defaults", "--protocol=TCP", "-h127.0.0.1",
                                "-P" + str(mysql_port), "-uroot", "-e", "CREATE DATABASE cloudoll_test"], check=True)
                env = dict(os.environ,
                           CLOUDOLL_TEST_MYSQL_URL=f"mysql://root@127.0.0.1:{mysql_port}/cloudoll_test",
                           CLOUDOLL_TEST_POSTGRES_URL=f"postgres://cloudoll@127.0.0.1:{pg_port}/postgres")
                for python in interpreters:
                    print("Integration runtime:", python, flush=True)
                    subprocess.run([python, "-m", "pytest", "-q", options.test_file],
                                   cwd=root, env=env, check=True, timeout=180)
        except subprocess.CalledProcessError as exc:
            if exc.stderr:
                print(exc.stderr.decode(errors="replace"), file=sys.stderr)
            raise
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    main()

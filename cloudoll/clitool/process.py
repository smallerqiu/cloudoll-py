import json
import os
import platform
import re
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, Optional

import click
import psutil
import portalocker
from tabulate import tabulate


class ProcessManager:
    @staticmethod
    @contextmanager
    def service_lock(name: str) -> Iterator[None]:
        """Hold a cross-process lock for the entire production service lifetime."""
        path = ProcessManager.get_pid_path(name).with_suffix(".lock")
        if path.is_symlink():
            raise click.ClickException("Refusing symlink service lock")
        lock = portalocker.Lock(str(path), mode="a", timeout=0)
        try:
            lock.acquire()
        except portalocker.exceptions.LockException as exc:
            raise click.ClickException(
                f"Service {name} is already running or starting"
            ) from exc
        try:
            yield
        finally:
            # Never unlink: another process may already hold this same lock inode.
            lock.release()

    @staticmethod
    def ensure_runtime_dir() -> None:
        """make sure runtime directory exists"""
        try:
            run_dir = ProcessManager.get_run_dir()
            run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        except (IOError, PermissionError) as e:
            click.echo(f"⚠️ Unable to create runtime directory: {e}", err=True)
            raise click.Abort()

    @staticmethod
    def get_run_dir() -> Path:
        home = Path.home()
        if platform.system() == "Windows":
            run_dir = home / "AppData/Local/cloudoll"
        else:
            run_dir = home / ".cloudoll"

        try:
            run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except (PermissionError, OSError) as exc:
            raise click.ClickException(
                f"Cannot create private runtime directory: {exc}"
            ) from exc
        if run_dir.is_symlink():
            raise click.ClickException("Runtime directory must not be a symlink")
        if os.name != "nt":
            if run_dir.stat().st_uid != os.getuid():
                raise click.ClickException("Runtime directory belongs to another user")
            run_dir.chmod(0o700)
        return run_dir

    @staticmethod
    def get_pid_path(name: str) -> Path:
        ProcessManager.validate_name(name)
        run_dir = ProcessManager.get_run_dir()
        return run_dir / f"{name}.pid"

    @staticmethod
    def validate_name(name: str) -> None:
        if name.upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise click.ClickException("Reserved service name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
            raise click.ClickException(
                "Service name must contain only letters, digits, '_' or '-' (1–64 characters)"
            )

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        import tempfile

        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cloudoll-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def save_pid(name: str, pid: int) -> None:
        """save pid file"""
        try:
            app_pid_file = ProcessManager.get_pid_path(name)
            proc = psutil.Process(pid)
            ProcessManager._write_json(
                app_pid_file,
                {
                    "pid": pid,
                    "created": proc.create_time(),
                    "cmdline": proc.cmdline(),
                },
            )
        except (IOError, PermissionError) as e:
            raise click.ClickException(f"Cannot save process identity: {e}") from e

    @staticmethod
    def safe_exit(service_name: str) -> None:
        pid: Optional[int] = None
        try:
            pid = ProcessManager.get_running_pid(service_name)
            if not pid:
                click.echo("⚠️  Cloudoll server not running.")
                return

            proc = psutil.Process(pid)
            if not ProcessManager._valid_process(pid, service_name):
                raise click.ClickException(
                    "Process identity changed; refusing to stop it"
                )
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except psutil.TimeoutExpired:
                # psutil also guards against PID reuse when signalling this object.
                if ProcessManager._valid_process(pid, service_name):
                    proc.kill()
                    proc.wait(timeout=5)

            ProcessManager.cleanup(service_name, expected_pid=pid)
            click.echo(f"🛑 Already stop service (PID: {pid})")
        except (ProcessLookupError, psutil.NoSuchProcess):
            ProcessManager.cleanup(service_name, expected_pid=pid)
        except (PermissionError, psutil.AccessDenied):
            click.echo(f"❌ No permission to operate the process {pid}", err=True)
            raise click.Abort()

    @staticmethod
    def get_running_pid(service_name: str) -> Optional[int]:
        """safe to read PID and verify process status"""
        try:
            app_pid_file = ProcessManager.get_pid_path(service_name)
            if not os.path.exists(app_pid_file):
                return None

            if app_pid_file.is_symlink():
                raise click.ClickException("Refusing symlink PID file")
            data = json.loads(app_pid_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                if type(data) is not int or data <= 0:
                    raise click.ClickException(
                        "Invalid legacy PID; inspect the record manually"
                    )
                if not psutil.pid_exists(data):
                    app_pid_file.unlink()
                    return None
                raise click.ClickException(
                    f"Legacy PID {data} still exists but has no saved process identity; "
                    "verify the process manually before stopping the old service and removing its PID file"
                )
            pid = data.get("pid")
            if type(pid) is not int or pid <= 0:
                raise click.ClickException("Invalid process identity")

            # valid process is running
            if not ProcessManager._valid_process(pid, service_name):
                os.unlink(app_pid_file)
                return None
            return pid
        except (ValueError, IOError, PermissionError):
            return None

    @staticmethod
    def _valid_process(pid: int, service_name: str) -> bool:
        """valid process"""
        try:
            path = ProcessManager.get_pid_path(service_name)
            if path.is_symlink():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("pid") != pid:
                return False
            proc = psutil.Process(pid)
            cmdline = proc.cmdline()
            matches_name = any(
                (
                    argument in {"--name", "-n"}
                    and index + 1 < len(cmdline)
                    and cmdline[index + 1] == service_name
                )
                or argument == f"--name={service_name}"
                for index, argument in enumerate(cmdline)
            )
            return (
                bool(proc.is_running())
                and proc.status() != psutil.STATUS_ZOMBIE
                and matches_name
                and proc.create_time() == data.get("created")
                and cmdline == data.get("cmdline")
            )
        except psutil.AccessDenied as exc:
            raise click.ClickException(
                "Cannot verify process identity; refusing operation"
            ) from exc
        except (psutil.NoSuchProcess, OSError, ValueError):
            return False

    @staticmethod
    def cleanup(service_name: str, *, expected_pid: Optional[int] = None) -> None:
        """Cleaning up residual PID files"""
        app_pid_file = ProcessManager.get_pid_path(service_name)
        if os.path.exists(app_pid_file):
            try:
                if expected_pid is not None:
                    data = json.loads(app_pid_file.read_text(encoding="utf-8"))
                    if not isinstance(data, dict) or data.get("pid") != expected_pid:
                        return
                os.unlink(app_pid_file)
            except (IOError, PermissionError, ValueError):
                pass

    @staticmethod
    def handle_shutdown(service_name: str) -> NoReturn:
        """Elegant Closure Processing"""
        ProcessManager.cleanup(service_name)
        os._exit(0)

    @staticmethod
    def register_signal_handlers(service_name: str) -> None:
        """register signal"""

        def guarded_shutdown(signum: int, frame: Optional[FrameType]) -> None:
            current_pid = os.getpid()
            try:
                # Double validation to prevent false triggers
                if not ProcessManager._valid_process(current_pid, service_name):
                    return

                ProcessManager.handle_shutdown(service_name)
            except Exception:
                os._exit(1)

        sigmap = (
            {
                signal.SIGINT: "SIGINT",
                signal.SIGTERM: "SIGTERM",
            }
            if platform.system() != "Windows"
            else {
                signal.SIGINT: "SIGINT",
                getattr(signal, "CTRL_C_EVENT"): "CTRL_C_EVENT",
            }
        )

        for sig, name in sigmap.items():
            try:
                signal.signal(sig, guarded_shutdown)
                # click.echo(f"register signal: {name}")
            except (ValueError, AttributeError) as e:
                click.echo(f"can't register signal {name}: {e}")

    @staticmethod
    def save_start_args(service_name: str, args: list[str]) -> None:
        """Save startup parameters to file"""
        args_file = ProcessManager.get_pid_path(service_name).with_suffix(".args")
        ProcessManager._write_json(args_file, {"args": args, "cwd": str(Path.cwd())})

    @staticmethod
    def load_start_args(service_name: str) -> list[str]:
        return ProcessManager.load_start_context(service_name)[0]

    @staticmethod
    def load_start_context(service_name: str) -> tuple[list[str], str]:
        """Read saved startup parameters"""
        args_file = ProcessManager.get_pid_path(service_name).with_suffix(".args")
        try:
            if args_file.is_symlink():
                raise click.ClickException("Refusing symlink startup file")
            data = json.loads(args_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise click.ClickException(
                    "Legacy startup arguments have no project directory; start the service again explicitly"
                )
            args, cwd = data.get("args"), data.get("cwd")
            if (
                not isinstance(args, list)
                or not all(isinstance(arg, str) for arg in args)
                or not isinstance(cwd, str)
                or not Path(cwd).is_absolute()
            ):
                raise click.ClickException("Invalid saved startup context")
            return args, cwd
        except (FileNotFoundError, json.JSONDecodeError):
            return [], ""

    @staticmethod
    def is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)  # 不发送信号，只检测是否存在
            return True
        except ProcessLookupError:
            return False

    @staticmethod
    def list() -> None:
        pid_dir = ProcessManager.get_run_dir()
        if not pid_dir.exists():
            click.echo("No services running.")
            return

        fmt = "{:<15} {:<8} {:<8} {:<12} {:<8} {:<10} {:<15}"
        headers = [
            "Services",
            "PID",
            "Status",
            "Env",
            "RunTime",
            "CPU%",
            "Mem(MB)",
            "Process",
        ]
        rows: list[list[Any]] = []
        for pid_file in sorted(pid_dir.glob("*.pid")):
            service = pid_file.stem
            try:
                pid = ProcessManager.get_running_pid(service)
                if pid is None:
                    rows.append([service, pid, "🔴 Exited", "-", "-", "-", "-"])
                    continue

                proc = psutil.Process(pid)
                cpu_percent = proc.cpu_percent(interval=0.1)  # 采样
                mem_mb = proc.memory_info().rss / 1024 / 1024
                name = proc.name()

                # runtime (current time - start time)
                start_time = datetime.fromtimestamp(proc.create_time())
                uptime = datetime.now() - start_time
                runtime = str(uptime).split(".")[0]

                "env"
                args = ProcessManager.load_start_args(service)
                env_value = "-"
                if "-env" in args:
                    index = args.index("-env")
                    if index + 1 < len(args):
                        env_value = args[index + 1]
                rows.append(
                    [
                        service,
                        pid,
                        "🟢 Running",
                        env_value,
                        runtime,
                        f"{cpu_percent:.1f}",
                        f"{mem_mb:.1f}",
                        name,
                    ]
                )
            except Exception as e:
                rows.append([service, "???", "error", "-", "-", "-", str(e)])

        click.echo(tabulate(rows, headers=headers, tablefmt="rounded_grid"))

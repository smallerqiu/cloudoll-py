import json
import os
import platform
import signal
import time
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import NoReturn, Optional, cast

import click
import psutil
from tabulate import tabulate


class ProcessManager:
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
        except (PermissionError, OSError):
            run_dir = Path("/tmp/cloudoll")
            run_dir.mkdir(parents=True, exist_ok=True, mode=0o777)
        return run_dir

    @staticmethod
    def get_pid_path(name: str) -> Path:
        run_dir = ProcessManager.get_run_dir()
        return run_dir / f"{name}.pid"

    @staticmethod
    def save_pid(name: str, pid: int) -> None:
        """save pid file"""
        try:
            app_pid_file = ProcessManager.get_pid_path(name)
            os.makedirs(os.path.dirname(app_pid_file), exist_ok=True)
            with open(app_pid_file, "w") as f:
                f.write(str(pid))
            os.chmod(app_pid_file, 0o644)  # 设置合理权限
        except (IOError, PermissionError) as e:
            click.echo(f"⚠️ can't save pid file: {e}", err=True)

    @staticmethod
    def safe_exit(service_name: str) -> None:
        pid: Optional[int] = None
        try:
            pid = ProcessManager.get_running_pid(service_name)
            if not pid:
                click.echo("⚠️  Cloudoll server not running.")
                return

            if platform.system() == "Windows":
                os.kill(pid, getattr(signal, "CTRL_C_EVENT"))
            else:
                os.kill(pid, signal.SIGTERM)

            # wait to exit
            for _ in range(10):
                if not ProcessManager._valid_process(pid, service_name):
                    break
                time.sleep(1)
            else:
                os.kill(pid, signal.SIGKILL)

            ProcessManager.cleanup(service_name)
            click.echo(f"🛑 Already stop service (PID: {pid})")
        except ProcessLookupError:
            ProcessManager.cleanup(service_name)
        except PermissionError:
            click.echo(f"❌ No permission to operate the process {pid}", err=True)
            raise click.Abort()

    @staticmethod
    def get_running_pid(service_name: str) -> Optional[int]:
        """safe to read PID and verify process status"""
        try:
            app_pid_file = ProcessManager.get_pid_path(service_name)
            if not os.path.exists(app_pid_file):
                return None

            with open(app_pid_file) as f:
                pid = int(f.read().strip())

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
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    @staticmethod
    def cleanup(service_name: str) -> None:
        """Cleaning up residual PID files"""
        app_pid_file = ProcessManager.get_pid_path(service_name)
        if os.path.exists(app_pid_file):
            try:
                os.unlink(app_pid_file)
            except (IOError, PermissionError):
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
        run_dir = ProcessManager.get_run_dir()
        args_file = run_dir / f"{service_name}.args"
        with open(args_file, "w") as f:
            json.dump(args, f)

    @staticmethod
    def load_start_args(service_name: str) -> list[str]:
        """Read saved startup parameters"""
        run_dir = ProcessManager.get_run_dir()
        args_file = run_dir / f"{service_name}.args"
        try:
            with open(args_file) as f:
                return cast(list[str], json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

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
        rows = []
        for pid_file in sorted(pid_dir.glob("*.pid")):
            service = pid_file.stem
            try:
                pid = int(pid_file.read_text())
                if not psutil.pid_exists(pid):
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

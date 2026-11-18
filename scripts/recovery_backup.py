"""Daily encrypted TurboTears recovery copies for macOS and Windows."""
import argparse
from datetime import date, time
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile

CONFIG = Path(__file__).with_name("backup-f1.json")
STATE = Path.home() / ".turbotears-backup"
LABEL = "ru.turbotears.backup-f1"
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def expand(value):
    return Path(os.path.expandvars(value)).expanduser()


class Backup:
    def __init__(self, config, device):
        self.config = config.resolve()
        self.device = device
        settings = json.loads(config.read_text(encoding="utf-8-sig"))
        options = settings[device]
        self.destination = expand(options["destination"])
        self.identity = expand(options["ssh_identity"])
        self.age = str(expand(options["age"]))
        self.age_identity = expand(options["recovery_identity"]) if options.get("recovery_identity") else None
        keygen = "age-keygen.exe" if device == "windows" else "age-keygen"
        self.age_keygen = str(Path(self.age).with_name(keygen))
        self.time = time.fromisoformat(options["time"])
        self.recipient = settings["age_recipient"]
        self.server = f'{settings["user"]}@{settings["host"]}'
        if not re.fullmatch(r"[A-Za-z0-9_]+@[A-Za-z0-9.-]+", self.server):
            raise ValueError("Invalid SSH server")
        hosts = config.parent / expand(settings["known_hosts"])
        self.ssh = [
            "ssh", "-T", "-p", str(int(settings["port"])),
            "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=yes",
            "-o", f'UserKnownHostsFile="{hosts.as_posix()}"',
            "-o", "GlobalKnownHostsFile=none",
        ]

    def public_key(self):
        self.identity.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.identity.exists():
            subprocess.run([
                "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
                f"turbotears-backup-{self.device}", "-f", str(self.identity),
            ], check=True)
        output = subprocess.check_output(["ssh-keygen", "-y", "-f", str(self.identity)], text=True)
        return " ".join(output.split()[:2])

    def register(self):
        public = self.public_key()
        # Send only the public key during the one-time interactive root login.
        subprocess.run([
            *self.ssh, self.server,
            "/usr/local/sbin/turbotears-register-backup-key " + shlex.quote(public),
        ], check=True)
        self.destination.mkdir(parents=True, exist_ok=True)

    def init_recovery_identity(self):
        if self.age_identity is None:
            raise ValueError("Set recovery_identity in the backup configuration")
        self.age_identity.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.age_identity.exists():
            subprocess.run([self.age_keygen, "-o", str(self.age_identity)], check=True)

    def pull(self):
        if not self.destination.is_dir():
            raise FileNotFoundError("Backup destination is unavailable")
        if not re.fullmatch(r"age1[0-9a-z]+", self.recipient):
            raise ValueError("Set age_recipient in the backup configuration")
        target = self.destination / f"backup_f1-{self.device}-{date.today().isoformat()}.tar.gz.age"
        if target.is_file():
            logging.info("Today's backup already exists: %s", target.name)
            return
        recipients = ["--recipient", self.recipient]
        if self.age_identity is not None:
            recovery_recipient = subprocess.check_output(
                [self.age_keygen, "-y", str(self.age_identity)],
                text=True, timeout=10, creationflags=HIDDEN,
            ).strip()
            recipients.extend(["--recipient", recovery_recipient])
        with tempfile.NamedTemporaryFile(
            dir=self.destination, prefix=f".backup_f1-{self.device}-", suffix=".partial", delete=False,
        ) as output, tempfile.TemporaryFile() as ssh_errors:
            temporary = Path(output.name)
            try:
                with subprocess.Popen([
                    *self.ssh, "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                    "-i", str(self.identity), self.server,
                ], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=ssh_errors,
                   creationflags=HIDDEN) as transport:
                    try:
                        subprocess.run(
                            [self.age, "--encrypt", *recipients],
                            stdin=transport.stdout, stdout=output, stderr=subprocess.DEVNULL,
                            timeout=1200, check=True, creationflags=HIDDEN,
                        )
                        transport.stdout.close()
                        if transport.wait(timeout=20):
                            raise RuntimeError("SSH backup export failed")
                    finally:
                        if transport.poll() is None:
                            transport.kill()
                output.flush()
                os.fsync(output.fileno())
                output.close()
                os.replace(temporary, target)
                logging.info("Encrypted backup saved: %s (%d bytes)", target.name, target.stat().st_size)
            finally:
                output.close()
                temporary.unlink(missing_ok=True)

    def install_mac(self):
        directory = Path.home() / "Library/LaunchAgents"
        directory.mkdir(parents=True, exist_ok=True)
        agent = directory / f"{LABEL}.plist"
        agent.write_bytes(plistlib.dumps({
            "Label": LABEL,
            "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "--config", str(self.config)],
            "StartCalendarInterval": {"Hour": self.time.hour, "Minute": self.time.minute},
            "RunAtLoad": True,
            "ProcessType": "Background",
            "StandardOutPath": str(STATE / "launchd.log"),
            "StandardErrorPath": str(STATE / "launchd.log"),
        }))
        domain = f"gui/{os.getuid()}"
        if subprocess.run(["launchctl", "print", f"{domain}/{LABEL}"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], check=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(agent)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="pull",
                        choices=("pull", "public-key", "register", "init-recovery", "install-mac"))
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--device", choices=("mac", "windows"),
                        default="windows" if sys.platform == "win32" else "mac")
    args = parser.parse_args()
    try:
        backup = Backup(args.config, args.device)
        if args.action == "public-key":
            print(backup.public_key())
        elif args.action == "register":
            backup.register()
        elif args.action == "init-recovery":
            backup.init_recovery_identity()
        elif args.action == "install-mac":
            STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
            backup.install_mac()
        else:
            STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
            logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", handlers=[
                RotatingFileHandler(STATE / "backup.log", maxBytes=256_000, backupCount=2, encoding="utf-8")
            ])
            backup.pull()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Keep SSH output and archive data out of the logs.
        logging.error("Backup operation failed (%s): %s", type(error).__name__,
                      str(error) if type(error) is RuntimeError else "")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

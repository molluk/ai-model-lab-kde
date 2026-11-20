"""Optional per-user Pi Office Bridge installer. Never rewrites Pi's configuration."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

import core

BRIDGE_FILENAME = 'ai-model-lab-office.js'


def bridge_file() -> Path:
    path = core.ROOT / 'extensions' / 'pi-office-bridge.js'
    if not path.is_file():
        raise FileNotFoundError('Pi Office Bridge отсутствует в установленном AI Model Lab: ' + str(path))
    return path.resolve()


def extension_target(agent_dir: Path | None = None) -> Path:
    directory = Path(agent_dir) if agent_dir is not None else core.HOME / '.pi' / 'agent'
    return directory / 'extensions' / BRIDGE_FILENAME


def is_bridge_installed(agent_dir: Path | None = None) -> bool:
    target = extension_target(agent_dir)
    return target.is_symlink() and target.resolve() == bridge_file()


def needs_explicit_extension(agent_dir: Path | None = None) -> bool:
    # If an existing file with our reserved filename is present, don't inject a
    # second observer into the same Pi runtime (even if it's not our symlink).
    target = extension_target(agent_dir)
    return not (target.exists() or target.is_symlink())


def install_global() -> Path:
    src = bridge_file()
    dest = extension_target()
    if dest.exists() or dest.is_symlink():
        if is_bridge_installed():
            return dest
        raise FileExistsError(f'Не перезаписываем существующее расширение: {dest}')
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.symlink_to(src)
    return dest


def uninstall_global() -> bool:
    dest = extension_target()
    if not dest.is_symlink():
        if dest.exists():
            raise FileExistsError('Расширение существует, но создано не нами; удаление отменено')
        return False
    if not is_bridge_installed():
        raise FileExistsError('Ссылка не указывает на установленный Pi Office Bridge; удаление отменено')
    dest.unlink()
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description='Управление наблюдателем Pi → Agent Office')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--status', action='store_true', help='показать состояние (ничего не менять)')
    modes.add_argument('--install', action='store_true', help='установить ссылку в ~/.pi/agent/extensions')
    modes.add_argument('--uninstall', action='store_true', help='удалить только собственную ссылку')
    args = parser.parse_args(argv)
    try:
        if args.status:
            print('Pi Office Bridge:', 'установлен' if is_bridge_installed() else 'не установлен глобально')
            print('Источник:', bridge_file())
            print('Ссылка:', extension_target())
        elif args.install:
            print('Установлено:', install_global())
            print('Перезапусти Pi; существующие сессии будут видны после новых событий.')
        elif args.uninstall:
            print('Удалено:', uninstall_global())
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Ошибка: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

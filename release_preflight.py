#!/usr/bin/env python3
"""No-Qt preflight: catch malformed Python f-string CSS before installation."""
from __future__ import annotations
import ast
from pathlib import Path
import sys


def check_source(root):
    for name in ('gui.py', 'core.py', 'multi.py', 'model_catalog.py', 'model_maintenance.py', 'version_info.py', 'bench.py', 'client_launcher.py', 'pi_bridge_manager.py', 'custom_services.py', 'shutdown_manager.py', 'service_browser.py'):
        path = root / name
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')

    tree = ast.parse((root / 'gui.py').read_text(encoding='utf-8'))
    color_node = style_node = None
    for item in tree.body:
        if not isinstance(item, ast.Assign):
            continue
        for t in item.targets:
            if isinstance(t, ast.Name) and t.id == 'COLORS':
                color_node = item.value
            if isinstance(t, ast.Name) and t.id == 'STYLE':
                style_node = item.value
    if color_node is None or style_node is None:
        raise RuntimeError('Не найдены COLORS / STYLE в gui.py')
    colors = ast.literal_eval(color_node)
    if not isinstance(style_node, ast.JoinedStr):
        raise RuntimeError('STYLE должен быть f-string')
    # Only `COLORS["name"]` interpolation is expected; reject unexpected expressions.
    for part in style_node.values:
        if not isinstance(part, ast.FormattedValue):
            continue
        expr = part.value
        if (not isinstance(expr, ast.Subscript) or not isinstance(expr.value, ast.Name)
                or expr.value.id != 'COLORS' or not isinstance(expr.slice, ast.Constant)
                or not isinstance(expr.slice.value, str) or expr.slice.value not in colors):
            raise RuntimeError('Небезопасный или ошибочный CSS placeholder в STYLE')
    result = eval(compile(ast.Expression(style_node), str(root/'gui.py'), 'eval'),
                  {'__builtins__': {}}, {'COLORS': colors})
    if 'QPushButton#Danger {' not in result or 'QPushButton#Slim {' not in result:
        raise RuntimeError('Отсутствуют стили кнопок')
    if "background:#63333b" not in result:
        raise RuntimeError('Отсутствует фон Danger')
    return result


def main():
    try:
        check_source(Path(__file__).resolve().parent)
        print('Release preflight: OK (Python + CSS f-string)')
        return 0
    except Exception as exc:
        print(f'Release preflight FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

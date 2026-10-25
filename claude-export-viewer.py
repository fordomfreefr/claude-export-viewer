#!/usr/bin/env python3
"""Run claude-export-viewer straight from this folder, without installing it.

    python3 claude-export-viewer.py ~/Téléchargements/conversations-000.zip -o ~/claude_site

Needs: jinja2, mistune, pydantic, pygments
    Debian / Ubuntu:  sudo apt install python3-jinja2 python3-mistune python3-pydantic python3-pygments
    Windows:          py -m pip install jinja2 mistune pydantic pygments
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from claude_export_viewer.cli import main
except ImportError as exc:
    from claude_export_viewer import i18n, system  # (standard library only)

    for flag in ("--langue", "--lang"):
        if flag in sys.argv[:-1]:
            i18n.set_language(i18n.normalize(sys.argv[sys.argv.index(flag) + 1]) or i18n.language())

    sys.exit(f"{i18n.t('cli.missing_module', module=exc.name)}\n{i18n.t('cli.install_with')}\n  {system.install_hint()}")

if __name__ == "__main__":
    main()

"""HOME temporal para los tests que tocan cache o entorno."""

from __future__ import annotations

import os
import tempfile
from unittest import mock


class IsolatedHomeMixin:
    """AUTONOMA_CLI_HOME a una carpeta temporal: ni lee ni escribe la cache real."""

    tmp: tempfile.TemporaryDirectory[str]

    def make_home(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(
            os.environ,
            {"AUTONOMA_CLI_HOME": self.tmp.name},
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)

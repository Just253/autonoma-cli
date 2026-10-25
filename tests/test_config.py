from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autonoma_cli import config


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(
            os.environ,
            {"AUTONOMA_CLI_HOME": self.tmp.name},
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        for key in ("AUTONOMA_USER", "AUTONOMA_PASSWORD", "AUTONOMA_BASE_URL"):
            os.environ.pop(key, None)

    def test_home_uses_override(self) -> None:
        self.assertEqual(config.home(), Path(self.tmp.name))

    def test_credentials_roundtrip(self) -> None:
        config.save_credentials("9000000001", "secreto")
        loaded = config.load_credentials()
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.username, "9000000001")
        self.assertEqual(loaded.password, "secreto")
        self.assertIn(loaded.method, {"dpapi", "plain"})

    def test_password_is_not_plaintext_with_dpapi(self) -> None:
        saved = config.save_credentials("alumno", "secreto-muy-largo")
        raw = config.credentials_path().read_text(encoding="utf-8")
        if saved.method == "dpapi":
            self.assertNotIn("secreto-muy-largo", raw)
            self.assertIn("blob", raw)

    def test_metadata_hides_password(self) -> None:
        config.save_credentials("alumno", "secreto")
        info = config.credentials_info()
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info["username"], "alumno")
        self.assertNotIn("password", info)
        self.assertNotIn("secreto", json.dumps(info))

    def test_env_credentials_have_priority(self) -> None:
        config.save_credentials("archivo", "guardado")
        os.environ["AUTONOMA_USER"] = "entorno"
        os.environ["AUTONOMA_PASSWORD"] = "desde-env"
        loaded = config.load_credentials()
        assert loaded is not None
        self.assertEqual(loaded.username, "entorno")
        self.assertEqual(loaded.method, "env")

    def test_clear_credentials(self) -> None:
        config.save_credentials("alumno", "secreto")
        self.assertTrue(config.clear_credentials())
        self.assertIsNone(config.load_credentials())
        self.assertFalse(config.clear_credentials())

    @unittest.skipIf(os.name == "nt", "los permisos POSIX no aplican en Windows")
    def test_posix_permissions(self) -> None:
        config.save_credentials("alumno", "secreto")
        mode = stat.S_IMODE(config.credentials_path().stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_settings_defaults_and_overrides(self) -> None:
        settings = config.load_settings()
        self.assertEqual(settings.base_url, config.DEFAULT_BASE_URL)
        os.environ["AUTONOMA_DELAY"] = "1.5"
        os.environ["AUTONOMA_WORKERS"] = "2"
        updated = config.load_settings()
        self.assertEqual(updated.delay, 1.5)
        self.assertEqual(updated.workers, 2)

    def test_save_settings_persists(self) -> None:
        config.save_settings(timeout=45, workers=8)
        settings = config.load_settings()
        self.assertEqual(settings.timeout, 45)
        self.assertEqual(settings.workers, 8)


class PlainCredentialsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(
            os.environ,
            {"AUTONOMA_CLI_HOME": self.tmp.name},
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        for key in ("AUTONOMA_USER", "AUTONOMA_PASSWORD"):
            os.environ.pop(key, None)
        self.path = config.plain_credentials_path()

    def write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def test_template_is_created_once(self) -> None:
        path, created = config.create_plain_credentials_file()
        self.assertTrue(created)
        self.assertEqual(path, self.path)
        self.assertIn("usuario=", path.read_text(encoding="utf-8"))
        _, again = config.create_plain_credentials_file()
        self.assertFalse(again)

    def test_empty_template_does_not_shadow_saved_credentials(self) -> None:
        config.save_credentials("archivo", "guardado")
        config.create_plain_credentials_file()
        loaded = config.load_credentials()
        assert loaded is not None
        self.assertEqual(loaded.method, "dpapi" if os.name == "nt" else "plain")

    def test_plain_file_has_priority(self) -> None:
        config.save_credentials("archivo", "guardado")
        self.write("usuario=editado\npassword=clave-editada\n")
        loaded = config.load_credentials()
        assert loaded is not None
        self.assertEqual(loaded.username, "editado")
        self.assertEqual(loaded.password, "clave-editada")
        self.assertEqual(loaded.method, "plain_file")

    def test_aliases_and_quotes(self) -> None:
        self.write("# comentario\nuser = \"otro\"\nclave: 'secreta'\n")
        loaded = config.load_credentials()
        assert loaded is not None
        self.assertEqual(loaded.username, "otro")
        self.assertEqual(loaded.password, "secreta")

    def test_incomplete_file_falls_back(self) -> None:
        self.write("usuario=solo-usuario\npassword=\n")
        self.assertIsNone(config.load_credentials())
        info = config.credentials_info()
        assert info is not None
        self.assertEqual(info["method"], "plain_file")
        self.assertFalse(info["complete"])

    def test_info_points_to_txt(self) -> None:
        self.write("usuario=alumno\npassword=clave\n")
        info = config.credentials_info()
        assert info is not None
        self.assertEqual(info["path"], str(self.path))
        self.assertIn("texto plano", info["label"])
        self.assertNotIn("clave", json.dumps(info))

    def test_clear_plain_file(self) -> None:
        self.write("usuario=alumno\npassword=clave\n")
        self.assertTrue(config.clear_plain_credentials())
        self.assertFalse(config.clear_plain_credentials())
        self.assertIsNone(config.load_credentials())


if __name__ == "__main__":
    unittest.main()

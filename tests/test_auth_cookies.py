from __future__ import annotations

import os
import stat
import tempfile
import unittest
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from autonoma_cli.auth.cookies import CookieStore

DOMAIN = "campus-de-ejemplo.edu"


def _cookie(name: str, value: str, expires: int | None = None) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=DOMAIN,
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=expires,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )


class CookieStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config" / "session.cookies"
        self.jar = LWPCookieJar(str(self.path))
        self.store = CookieStore(self.jar, str(self.path))

    def test_save_creates_the_parent_folder(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        self.store.save()
        self.assertTrue(self.path.exists())

    def test_load_reads_the_saved_cookie(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        self.store.save()
        other = CookieStore(LWPCookieJar(str(self.path)), str(self.path))
        self.assertTrue(other.load())

    def test_load_fails_without_a_file(self) -> None:
        self.assertFalse(self.store.load())
        self.assertEqual(list(self.jar), [])

    def test_expired_cookies_do_not_count_as_a_session(self) -> None:
        self.jar.set_cookie(_cookie("vieja", "1", expires=1))
        self.store.save()
        self.assertFalse(self.store.load())

    def test_clear_removes_the_file_once(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        self.store.save()
        self.assertTrue(self.store.clear())
        self.assertFalse(self.path.exists())
        self.assertFalse(self.store.clear())

    def test_clear_empties_the_jar(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        self.store.clear()
        self.assertEqual(list(self.jar), [])

    def test_header_joins_the_vigent_cookies(self) -> None:
        self.jar.set_cookie(_cookie("uno", "1"))
        self.jar.set_cookie(_cookie("dos", "2"))
        self.jar.set_cookie(_cookie("vieja", "3", expires=1))
        self.assertEqual(self.store.header(), "uno=1; dos=2")

    def test_header_is_empty_without_cookies(self) -> None:
        self.assertEqual(self.store.header(), "")

    def test_names_lists_every_cookie(self) -> None:
        self.jar.set_cookie(_cookie("uno", "1"))
        self.jar.set_cookie(_cookie("dos", "2"))
        self.assertEqual(self.store.names(), ["uno", "dos"])


class CookiePermissionTests(unittest.TestCase):
    """En POSIX la cookie y su carpeta quedan cerradas como la config."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config" / "session.cookies"
        self.jar = LWPCookieJar(str(self.path))
        self.store = CookieStore(self.jar, str(self.path))

    def test_posix_save_closes_the_folder_and_the_file(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        chmod = mock.Mock()
        fake_os = SimpleNamespace(name="posix", chmod=chmod)
        with mock.patch("autonoma_cli.auth.cookies.os", fake_os):
            self.store.save()
        modes = {str(call.args[0]): call.args[1] for call in chmod.call_args_list}
        self.assertEqual(modes[str(self.path.parent)], 0o700)
        self.assertEqual(modes[str(self.path)], 0o600)

    def test_windows_save_does_not_touch_the_permissions(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        chmod = mock.Mock()
        fake_os = SimpleNamespace(name="nt", chmod=chmod)
        with mock.patch("autonoma_cli.auth.cookies.os", fake_os):
            self.store.save()
        chmod.assert_not_called()

    @unittest.skipIf(os.name == "nt", "los permisos POSIX no existen en Windows")
    def test_posix_modes_on_disk(self) -> None:
        self.jar.set_cookie(_cookie("ASP.NET_SessionId", "abc"))
        self.store.save()
        folder = stat.S_IMODE(self.path.parent.stat().st_mode)
        self.assertEqual(folder, 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()

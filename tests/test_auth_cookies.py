from __future__ import annotations

import tempfile
import unittest
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()

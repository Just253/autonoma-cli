from __future__ import annotations

import ssl
import unittest
from urllib.error import URLError

from autonoma_cli import config
from autonoma_cli.client import CampusClient
from autonoma_cli.net import cert_mismatch
from support.home import IsolatedHomeMixin
from support.session import COOKIE_NAME, FakeSession, save_cookie

BASE = "https://campus-de-ejemplo.edu"
HOME_URL = f"{BASE}/Campus/Default.aspx"


class CertificateMismatchTests(unittest.TestCase):
    """El ALB del campus rota IPs: una IP vieja responde con otro certificado."""

    def test_hostname_mismatch_is_detected(self) -> None:
        error = ssl.SSLCertVerificationError(
            1,
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "Hostname mismatch, certificate is not valid for "
            "'virtual.autonoma.edu.pe'. (_ssl.c:1006)",
        )
        self.assertTrue(cert_mismatch(URLError(error)))

    def test_connection_refused_is_not_a_mismatch(self) -> None:
        self.assertFalse(cert_mismatch(URLError(ConnectionRefusedError(10061, "refused"))))


class DelegationTests(IsolatedHomeMixin, unittest.TestCase):
    """El cliente toma de la sesion el referer, el timeout, el delay y el cierre."""

    def setUp(self) -> None:
        self.make_home()

    def test_timeout_y_delay_salen_de_la_sesion(self) -> None:
        client = CampusClient(session=FakeSession(timeout=12.5, delay=0))
        self.assertEqual(client.timeout, 12.5)
        self.assertEqual(client.delay, 0)

    def test_sin_inyeccion_se_arma_la_sesion_del_campus(self) -> None:
        client = CampusClient(base_url=BASE, timeout=12.5, delay=0)
        self.assertEqual(client.timeout, 12.5)
        self.assertEqual(client.delay, 0)
        self.assertEqual(client.describe()["cookies_file"], str(config.cookies_path()))
        self.assertEqual(client.referer, HOME_URL)

    def test_la_sesion_inyectada_manda_sobre_los_argumentos(self) -> None:
        session = FakeSession(timeout=3.0, delay=0.25)
        client = CampusClient(
            BASE, timeout=99.0, delay=9.0, cookies_file="otra.cookies",
            retries=5, session=session,
        )
        self.assertEqual(client.base_url, BASE)
        self.assertEqual(client.retries, 5)
        self.assertEqual(client.timeout, 3.0)
        self.assertEqual(client.delay, 0.25)
        self.assertEqual(client.describe()["cookies_file"], session.cookies_path)

    def test_referer_sigue_el_home_de_la_sesion(self) -> None:
        fake = FakeSession(home_url=HOME_URL)
        client = CampusClient(session=fake)
        self.assertEqual(client.referer, HOME_URL)
        fake.home_url = f"{BASE}/Campus/Otra.aspx"
        self.assertEqual(client.referer, fake.home_url)

    def test_close_cierra_la_sesion(self) -> None:
        fake = FakeSession()
        client = CampusClient(session=fake)
        client.close()
        self.assertTrue(fake.closed)

    def test_describe_lista_las_cookies_del_jar(self) -> None:
        fake = FakeSession()
        save_cookie(fake)
        client = CampusClient(session=fake)
        self.assertEqual(client.describe()["cookie_names"], [COOKIE_NAME])


if __name__ == "__main__":
    unittest.main()

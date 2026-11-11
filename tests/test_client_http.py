from __future__ import annotations

import ssl
import unittest
from unittest import mock
from urllib.error import URLError

from autonoma_cli.client import CampusClient
from autonoma_cli.net import cert_mismatch
from support.home import IsolatedHomeMixin


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
        client = CampusClient(timeout=12.5, delay=0)
        self.assertEqual(client.timeout, 12.5)
        self.assertEqual(client.timeout, client._session.timeout)
        self.assertEqual(client.delay, 0)
        self.assertEqual(client.delay, client._session.delay)

    def test_referer_sigue_el_home_de_la_sesion(self) -> None:
        client = CampusClient(delay=0)
        self.assertEqual(client.referer, client._session.home_url)
        client._session.home_url = "https://campus-de-ejemplo.edu/Campus/Default.aspx"
        self.assertEqual(client.referer, client._session.home_url)

    def test_close_cierra_la_sesion(self) -> None:
        client = CampusClient(delay=0)
        with mock.patch.object(client._session, "close") as close:
            client.close()
        close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

"""Superficie y salida de `autonoma entregar`, sin red."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import build_parser, main

from support import FOLDER, TASK, IsolatedHomeMixin, UploadClient


class EntregarCommandTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "entrega.zip"
        self.file.write_bytes(b"PK\x03\x04 datos de ejemplo")
        self.client = UploadClient()

    def run_main(self, *argv: str, client: UploadClient | None = None) -> tuple[int, str]:
        patcher = mock.patch(
            "autonoma_cli.commands.client_for", return_value=client or self.client
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(list(argv))
        return code, output.getvalue()

    def base(self, *extra: str) -> list[str]:
        return [
            "entregar",
            "90000001",
            str(self.file),
            "--titulo",
            "ENTREGA DE EJEMPLO",
            "--descripcion",
            "Trabajo de ejemplo",
            *extra,
        ]

    def test_seco_muestra_el_plan_y_no_sube(self) -> None:
        code, out = self.run_main(*self.base("--carpeta", str(FOLDER), "--seco"))
        self.assertEqual(code, 0)
        self.assertEqual(self.client.uploads, [])
        self.assertEqual(self.client.calls, [])
        self.assertIn("semana 10", out)
        self.assertIn("no se subio nada", out)

    def test_seco_json_es_estable(self) -> None:
        code, out = self.run_main(*self.base("--tarea", str(TASK), "--seco", "--json"))
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["dry_run"])
        self.assertIsNone(payload["result"])
        self.assertEqual(payload["target"], {"kind": "tarea", "number": TASK, "session": 0})
        self.assertEqual(payload["course"]["code"], "PISOP00001")
        self.assertEqual(payload["file"]["extension"], "zip")
        self.assertIsNone(payload["param0"])

    def test_sin_seco_ni_confirmar_es_error_de_uso(self) -> None:
        code, out = self.run_main(*self.base("--tarea", str(TASK)))
        self.assertEqual(code, 2)
        self.assertEqual(self.client.uploads, [])
        self.assertIn("--confirmar", out)

    def test_tarea_confirma_una_subida_y_un_registro(self) -> None:
        code, out = self.run_main(*self.base("--tarea", str(TASK), "--confirmar", "--json"))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.client.uploads), 1)
        self.assertEqual([name for name, _ in self.client.calls], ["Alu_InsertarTarea"])
        payload = json.loads(out)
        self.assertEqual(payload["result"]["task_id"], 2099011)
        self.assertEqual(payload["result"]["saved_name"], "209901_ENTREGA.zip")
        self.assertIsNone(payload["result"]["synced"])
        xml = self.client.calls[0][1]["xml"]
        self.assertIn(f"<nDocLinNum>{TASK}</nDocLinNum>", xml)
        self.assertIn("<nRespTarea>0</nRespTarea>", xml)

    def test_sin_param0_se_conserva_el_nombre(self) -> None:
        self.run_main(*self.base("--tarea", str(TASK), "--confirmar"))
        self.assertNotIn(b'name="param0"', self.client.uploads[0])

    def test_param0_cambia_el_nombre_base(self) -> None:
        self.run_main(*self.base("--tarea", str(TASK), "--confirmar", "--param0", "Alumno"))
        self.assertIn(b'name="param0"', self.client.uploads[0])
        self.assertIn(b"\r\nAlumno\r\n", self.client.uploads[0])

    def test_carpeta_rechazada_sale_con_error_y_no_cae_a_tarea(self) -> None:
        client = UploadClient(resource_state=0)
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--confirmar"), client=client
        )
        self.assertEqual(code, 4)
        self.assertEqual([name for name, _ in client.calls], ["Doc_InsertarRecurso"])
        self.assertIn("nUAEstado", out)
        self.assertIn("--tarea", out)

    def test_carpeta_sincroniza_y_avisa_si_falla(self) -> None:
        client = UploadClient(sync_error="el campus no responde")
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--confirmar", "--json"), client=client
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            [name for name, _ in client.calls],
            ["Doc_InsertarRecurso", "setCarpetaRecurso"],
        )
        payload = json.loads(out)
        self.assertEqual(payload["result"]["resource_id"], 209903)
        self.assertFalse(payload["result"]["synced"])
        self.assertIn("no se sincronizo", payload["result"]["sync_note"])

    def test_archivo_inexistente_es_error_de_uso(self) -> None:
        self.file.unlink()
        code, out = self.run_main(*self.base("--tarea", str(TASK), "--seco"))
        self.assertEqual(code, 2)
        self.assertIn("No existe el archivo", out)
        self.assertEqual(self.client.reads, [])
        self.assertEqual(self.client.calls, [])

    def test_param0_con_carpeta_falla_antes_de_la_red(self) -> None:
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--param0", "Alumno", "--seco")
        )
        self.assertEqual(code, 2)
        self.assertIn("--param0", out)
        self.assertEqual(self.client.reads, [])

    def test_seco_y_confirmar_juntos_es_error_de_uso(self) -> None:
        code, out = self.run_main(
            *self.base("--tarea", str(TASK), "--seco", "--confirmar")
        )
        self.assertEqual(code, 2)
        self.assertIn("--seco", out)
        self.assertEqual(self.client.uploads, [])
        self.assertEqual(self.client.reads, [])

    def test_seco_carpeta_en_sesion_activa_hace_dos_lecturas(self) -> None:
        code, out = self.run_main(*self.base("--carpeta", str(FOLDER), "--seco"))
        self.assertEqual(code, 0)
        self.assertEqual(self.client.reads, ["cursos", "sesion activa"])
        self.assertIn("semana 10", out)

    def test_seco_carpeta_fuera_de_la_sesion_activa_recorre_sesiones(self) -> None:
        client = UploadClient(folder_active=False)
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--seco"), client=client
        )
        self.assertEqual(code, 0)
        self.assertEqual(client.reads, ["cursos", "sesion activa", "sesiones"])
        self.assertIn("semana 10", out)

    def test_sesion_salta_la_busqueda(self) -> None:
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--sesion", "12", "--seco", "--json")
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.client.reads, ["cursos"])
        self.assertEqual(json.loads(out)["target"]["session"], 12)

    def test_sesion_solo_vale_con_carpeta(self) -> None:
        code, out = self.run_main(
            *self.base("--tarea", str(TASK), "--sesion", "12", "--seco")
        )
        self.assertEqual(code, 2)
        self.assertIn("--sesion", out)
        self.assertEqual(self.client.reads, [])

    def test_carpeta_sincroniza_con_el_payload_del_campus(self) -> None:
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--confirmar", "--json")
        )
        self.assertEqual(code, 0)
        payload = self.client.calls[1][1]
        self.assertEqual(payload["nDocLinNum"], FOLDER)
        self.assertEqual(payload["carpetaInformation"]["cPerCodigo"], "2024000001")
        self.assertEqual(payload["carpetaInformation"]["Archivo"], "209901_ENTREGA.zip")
        self.assertEqual(payload["silaboId"], "")
        self.assertEqual(payload["sesionId"], "")
        self.assertTrue(json.loads(out)["result"]["synced"])

    def test_carpeta_sin_student_code_avisa_y_no_falla(self) -> None:
        client = UploadClient(student_error="no hay codigo de alumno")
        code, out = self.run_main(
            *self.base("--carpeta", str(FOLDER), "--confirmar", "--json"), client=client
        )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["result"]["resource_id"], 209903)
        self.assertFalse(payload["result"]["synced"])
        self.assertIn("no hay codigo de alumno", payload["result"]["sync_note"])
        self.assertEqual([name for name, _ in client.calls], ["Doc_InsertarRecurso"])

    def test_carpeta_con_extension_no_permitida(self) -> None:
        word = Path(self.tmp.name) / "informe.docx"
        word.write_bytes(b"PK\x03\x04")
        argv = self.base("--carpeta", str(FOLDER), "--seco")
        argv[2] = str(word)
        code, out = self.run_main(*argv)
        self.assertEqual(code, 2)
        self.assertIn(".zip", out)

    def test_curso_ambiguo_lista_candidatos(self) -> None:
        argv = self.base("--tarea", str(TASK), "--seco")
        argv[1] = "ejemplo"
        code, out = self.run_main(*argv)
        self.assertEqual(code, 2)
        self.assertIn("CURSO DE EJEMPLO UNO", out)
        self.assertIn("CURSO DE EJEMPLO DOS", out)

    def test_curso_inexistente(self) -> None:
        argv = self.base("--tarea", str(TASK), "--seco")
        argv[1] = "no-existe-999"
        code, out = self.run_main(*argv)
        self.assertEqual(code, 2)
        self.assertIn("No hay ningun curso", out)

    def test_el_parser_exige_un_destino(self) -> None:
        parser = build_parser()
        required = ["entregar", "90000001", "entrega.zip", "--titulo", "T", "--descripcion", "D"]
        both = [*required, "--carpeta", str(FOLDER), "--tarea", str(TASK)]
        for argv in (required, both):
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        parser.parse_args(argv)


if __name__ == "__main__":
    unittest.main()

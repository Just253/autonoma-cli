from __future__ import annotations

import unittest

from autonoma_cli.models import (
    Course,
    Resource,
    SessionTopic,
    extension_from,
    kind_name,
    resolve_upload_url,
    safe_filename,
    slugify,
)

BASE = "https://virtual.autonoma.edu.pe"


class SlugTests(unittest.TestCase):
    def test_slugify_removes_accents_and_illegal_chars(self) -> None:
        self.assertEqual(slugify("PRESENTACIÓN: DISEÑO DIGITAL / TEMA?"), "PRESENTACION_DISENO_DIGITAL_TEMA")

    def test_slugify_never_returns_empty(self) -> None:
        self.assertEqual(slugify("###"), "sin_titulo")

    def test_safe_filename_keeps_extension_when_truncating(self) -> None:
        name = safe_filename("a" * 200 + ".pdf", limit=40)
        self.assertTrue(name.endswith(".pdf"))
        self.assertLessEqual(len(name), 40)

    def test_safe_filename_fallback(self) -> None:
        self.assertEqual(safe_filename("   "), "archivo")


class UrlTests(unittest.TestCase):
    def test_relative_goes_to_uploads(self) -> None:
        self.assertEqual(
            resolve_upload_url(BASE, "01-03-2027_000000000_000DOCUMENTO.pdf"),
            f"{BASE}/uploads/01-03-2027_000000000_000DOCUMENTO.pdf",
        )

    def test_absolute_path_is_joined(self) -> None:
        self.assertEqual(
            resolve_upload_url(BASE, "/UploadsEnvioEmailPDF/silabo.pdf"),
            f"{BASE}/UploadsEnvioEmailPDF/silabo.pdf",
        )

    def test_full_url_is_respected(self) -> None:
        url = "https://cdn.example.com/a.pdf"
        self.assertEqual(resolve_upload_url(BASE, url), url)

    def test_pipe_suffix_is_discarded(self) -> None:
        self.assertEqual(
            resolve_upload_url(BASE, "archivo.pdf||otra-cosa"),
            f"{BASE}/uploads/archivo.pdf",
        )

    def test_empty(self) -> None:
        self.assertEqual(resolve_upload_url(BASE, None), "")

    def test_extension_from_icon(self) -> None:
        self.assertEqual(extension_from("", "far fa-file-pdf"), ".pdf")
        self.assertEqual(extension_from(f"{BASE}/uploads/a.PDF", ""), ".pdf")


class CourseTests(unittest.TestCase):
    def test_from_api_maps_main_fields(self) -> None:
        course = Course.from_api(
            {
                "nGruCodigo": 90000001,
                "asignatura": "CURSO DE EJEMPLO",
                "codigo": "PISOP00001",
                "periodo": "209901",
                "ciclo": 1,
                "seccion": "1",
                "grupo": "1A1-A",
                "creditos": 4,
                "modalidad": "VIRTUAL",
                "docenteNombre": "DOCENTE",
                "docenteApellido": "DE EJEMPLO",
                "correoDocente": "docente@ejemplo.edu.pe",
                "fechaInicioCurso": "01/03/2027",
                "fechaFinCurso": "30/06/2027",
                "cantidadRecursos": 12,
                "EstadoCurso": 1,
                "cSilabo": "/UploadsEnvioEmailPDF/silabo.pdf",
            },
            BASE,
        )
        self.assertEqual(course.group_id, 90000001)
        self.assertEqual(course.teacher, "DOCENTE DE EJEMPLO")
        self.assertEqual(course.resources_count, 12)
        self.assertEqual(course.state, "activo")
        self.assertEqual(course.syllabus_url, f"{BASE}/UploadsEnvioEmailPDF/silabo.pdf")
        self.assertTrue(course.matches("ejemplo"))
        self.assertTrue(course.matches("90000001"))
        self.assertFalse(course.matches("matematica"))

    def test_unknown_teacher_does_not_crash(self) -> None:
        course = Course.from_api({"nGruCodigo": 1, "asignatura": "X"}, BASE)
        self.assertEqual(course.teacher, "")
        self.assertEqual(course.credits, "")


class ResourceTests(unittest.TestCase):
    def test_from_api_normalizes_archive(self) -> None:
        resource = Resource.from_api(
            {
                "cTitulo": "PRESENTACIÓN: TEMA DE EJEMPLO",
                "nDocLinTipo": 2,
                "nDocLinNum": 3,
                "nSesion": 1,
                "cSesion": "01",
                "url": "01-03-2027_000000000_000DOCUMENTO.pdf",
                "clase": "far fa-file-pdf",
                "dDocTraFec": "01/03/2027",
                "nItinerario": 2,
            },
            BASE,
        )
        self.assertEqual(resource.kind_name, "Archivo")
        self.assertEqual(resource.extension, ".pdf")
        self.assertEqual(resource.itinerary, "INTERIORIZA")
        self.assertTrue(resource.downloadable)
        self.assertEqual(resource.session, 1)

    def test_kind_names(self) -> None:
        self.assertEqual(kind_name(4), "Tarea")
        self.assertEqual(kind_name(7), "Foro")
        self.assertEqual(kind_name(99), "Otro (99)")
        self.assertEqual(kind_name(None), "Otro")

    def test_folder_is_not_downloadable(self) -> None:
        resource = Resource.from_api({"cTitulo": "Carpeta", "nDocLinTipo": 1}, BASE)
        self.assertFalse(resource.downloadable)


class SessionTopicTests(unittest.TestCase):
    def test_from_api(self) -> None:
        topic = SessionTopic.from_api(
            {
                "nSesion": 4,
                "cSesion": "04",
                "semana_fecha_inicio": "08/03/2027",
                "semana_fecha_fin": "14/03/2027",
                "tema": "Evaluacion de Conocimientos (EC): Tema de ejemplo\nValor: Integridad",
                "logro": "Resuelve problemas",
                "sesion_activa": 1,
            }
        )
        self.assertEqual(topic.number, 4)
        self.assertTrue(topic.active)
        self.assertEqual(topic.title, "Evaluacion de Conocimientos (EC): Tema de ejemplo")


if __name__ == "__main__":
    unittest.main()

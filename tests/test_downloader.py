from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from autonoma_cli.downloader import (
    Manifest,
    build_filename,
    course_folder,
    human_size,
    plan_course,
)
from autonoma_cli.models import Course, Resource

BASE = "https://virtual.autonoma.edu.pe"


def make_course(group: int = 1, name: str = "CURSO DE EJEMPLO UNO") -> Course:
    return Course.from_api({"nGruCodigo": group, "asignatura": name}, BASE)


def make_resource(title: str, kind: int = 2, session: int = 1, url: str = "a.pdf") -> Resource:
    return Resource.from_api(
        {
            "cTitulo": title,
            "nDocLinTipo": kind,
            "nDocLinNum": 1,
            "nSesion": session,
            "url": url,
        },
        BASE,
        session=session,
    )


class FilenameTests(unittest.TestCase):
    def test_course_folder_is_slug(self) -> None:
        self.assertEqual(course_folder(make_course()), "CURSO_DE_EJEMPLO_UNO")

    def test_build_filename_contains_kind_and_extension(self) -> None:
        name = build_filename(make_resource("PRESENTACIÓN: TEMA"))
        self.assertTrue(name.startswith("ARCHIVO_"))
        self.assertTrue(name.endswith(".pdf"))
        self.assertNotIn(":", name)

    def test_human_size(self) -> None:
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(2048), "2.0 KB")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0 MB")


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.course = make_course()
        self.sessions = [
            (1, [make_resource("PRESENTACION: A", url="a.pdf"), make_resource("TAREA: B", kind=4, url="b.pdf")]),
            (2, [make_resource("LECTURA: C", session=2, url="c.pdf"), make_resource("CARPETA", kind=1, session=2)]),
        ]

    def test_plan_structure(self) -> None:
        items = plan_course(self.course, self.sessions, self.root)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].path, self.root / "CURSO_DE_EJEMPLO_UNO" / "Sesion_01" / "ARCHIVO_PRESENTACION_A.pdf")
        self.assertEqual(items[1].resource.kind_name, "Tarea")
        self.assertEqual(items[2].path.parent.name, "Sesion_02")

    def test_kind_filter(self) -> None:
        items = plan_course(self.course, self.sessions, self.root, kinds={4})
        self.assertEqual([item.resource.title for item in items], ["TAREA: B"])

    def test_regex_filter(self) -> None:
        items = plan_course(self.course, self.sessions, self.root, only=re.compile("lectura", re.I))
        self.assertEqual([item.resource.title for item in items], ["LECTURA: C"])

    def test_folder_resources_are_skipped(self) -> None:
        items = plan_course(self.course, self.sessions, self.root)
        self.assertNotIn("CARPETA", [item.resource.title for item in items])

    def test_duplicate_titles_get_suffix(self) -> None:
        sessions = [(1, [make_resource("MISMO", url="a.pdf"), make_resource("MISMO", url="b.pdf")])]
        items = plan_course(self.course, sessions, self.root)
        self.assertEqual(len({item.path for item in items}), 2)
        self.assertTrue(any("(2)" in item.path.name for item in items))


class ManifestTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = Manifest(root)
            manifest.put("https://x/a.pdf", {"bytes": 10, "sha256": "abc"})
            manifest.save()

            document = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("https://x/a.pdf", document["entries"])

            again = Manifest(root)
            self.assertEqual(again.get("https://x/a.pdf")["bytes"], 10)
            self.assertIsNone(again.get("https://x/nada.pdf"))


if __name__ == "__main__":
    unittest.main()

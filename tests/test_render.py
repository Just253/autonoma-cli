from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date

from autonoma_cli import ui
from autonoma_cli.cli import print_schedule, print_stats
from autonoma_cli.downloader import DownloadStats
from autonoma_cli.models import ClassSession

TUESDAY = date(2026, 10, 20)
THURSDAY = date(2026, 10, 22)


def session(
    day: str,
    start: str,
    end: str,
    *,
    course: str = "CURSO DE EJEMPLO",
    room: str = "A-101",
    kind: str = "Sincrona",
    number: int = 1,
    topic: str = "Tema de la sesion",
) -> ClassSession:
    return ClassSession.from_api(
        {
            "fecha": f"{day} {start} a {end}",
            "asignatura": course,
            "ambiente": room,
            "tipo": kind,
            "nSesion": number,
            "cSesion": f"{number:02d}",
            "tema": topic,
        },
        group_id=1,
        course=course,
    )


def undated_session(course: str = "SIN FECHA") -> ClassSession:
    return ClassSession.from_api(
        {"fecha": "", "asignatura": course, "nSesion": 3, "tema": "Sin fecha"},
        group_id=1,
        course=course,
    )


class RenderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        ui.configure_color(False)

    def render_schedule(
        self,
        entries: list[ClassSession],
        start: date | None,
        end: date | None,
    ) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_schedule(entries, start, end)
        return buffer.getvalue()

    def render_stats(self, stats: DownloadStats, dry_run: bool = False) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            print_stats(stats, dry_run=dry_run)
        return out.getvalue(), err.getvalue()


class PrintScheduleEmptyTests(RenderTestCase):
    def test_no_sessions_full_period(self) -> None:
        output = self.render_schedule([], None, None)
        self.assertIn("Horario completo · 0 sesiones", output)
        self.assertIn("Sin clases en el periodo.", output)

    def test_no_sessions_single_day(self) -> None:
        output = self.render_schedule([], TUESDAY, TUESDAY)
        self.assertIn("Martes, 20/10/2026", output)
        self.assertNotIn("sesion", output)
        self.assertIn("Sin clases para esa fecha.", output)

    def test_no_sessions_range(self) -> None:
        output = self.render_schedule([], TUESDAY, THURSDAY)
        self.assertIn("Del 20/10/2026 al 22/10/2026 · 0 sesiones", output)
        self.assertIn("Sin clases en ese rango.", output)


class PrintScheduleDayTests(RenderTestCase):
    def test_single_session_single_day(self) -> None:
        entries = [session("20/10/2026", "08:00", "10:00")]
        output = self.render_schedule(entries, TUESDAY, TUESDAY)
        self.assertIn("Martes, 20/10/2026 · 1 sesion", output)
        self.assertIn("Martes 20/10/2026", output)
        self.assertIn("Hora", output)
        self.assertIn("08:00-10:00", output)
        self.assertIn("CURSO DE EJEMPLO", output)
        self.assertIn("A-101", output)
        # Pie con la etiqueta y el tema, solo cuando el rango es un unico dia.
        self.assertIn("01 · Tema de la sesion", output)

    def test_today_label(self) -> None:
        today = date.today()
        entry = session(today.strftime("%d/%m/%Y"), "08:00", "10:00")
        output = self.render_schedule([entry], today, today)
        self.assertIn(f"Hoy, {today:%d/%m/%Y} · 1 sesion", output)

    def test_grouped_days_in_order(self) -> None:
        entries = [
            session("20/10/2026", "08:00", "10:00", course="CURSO A"),
            session("22/10/2026", "14:00", "16:00", course="CURSO B", number=2),
        ]
        output = self.render_schedule(entries, TUESDAY, THURSDAY)
        self.assertIn("Del 20/10/2026 al 22/10/2026 · 2 sesiones", output)
        self.assertIn("Martes 20/10/2026", output)
        self.assertIn("Jueves 22/10/2026", output)
        self.assertLess(output.index("CURSO A"), output.index("Jueves 22/10/2026"))
        self.assertLess(output.index("Jueves 22/10/2026"), output.index("CURSO B"))
        # Sin pie de temas: solo se imprime cuando start == end.
        self.assertNotIn("02 · Tema de la sesion", output)

    def test_full_period_heading(self) -> None:
        entries = [
            session("20/10/2026", "08:00", "10:00"),
            session("22/10/2026", "14:00", "16:00", number=2),
        ]
        output = self.render_schedule(entries, None, None)
        self.assertIn("Horario completo · 2 sesiones", output)
        self.assertNotIn("Sin clases", output)


class PrintScheduleQuirkTests(RenderTestCase):
    def test_unsorted_days_are_not_merged(self) -> None:
        # print_schedule agrupa solo fechas consecutivas: ordena quien llama.
        entries = [
            session("22/10/2026", "14:00", "16:00", course="CURSO B", number=2),
            session("20/10/2026", "08:00", "10:00", course="CURSO A"),
        ]
        output = self.render_schedule(entries, TUESDAY, THURSDAY)
        self.assertLess(output.index("Jueves 22/10/2026"), output.index("Martes 20/10/2026"))
        self.assertLess(output.index("CURSO B"), output.index("Martes 20/10/2026"))

    def test_entries_without_date_are_skipped_silently(self) -> None:
        entries = [session("20/10/2026", "08:00", "10:00"), undated_session()]
        output = self.render_schedule(entries, None, None)
        self.assertIn("Horario completo · 2 sesiones", output)
        self.assertNotIn("SIN FECHA", output)
        self.assertEqual(output.count("\nHora"), 1)
        self.assertEqual(output.count("08:00-10:00"), 1)
        self.assertNotIn("Sin clases", output)


class PrintStatsTests(RenderTestCase):
    def test_zero(self) -> None:
        out, err = self.render_stats(DownloadStats())
        self.assertEqual(
            out, "\nDescargados: 0 · Ya estaban: 0 · Errores: 0 · Total: 0 B\n"
        )
        self.assertEqual(err, "")

    def test_one(self) -> None:
        out, err = self.render_stats(
            DownloadStats(downloaded=1, skipped=0, failed=0, bytes=2048)
        )
        self.assertIn("Descargados: 1 · Ya estaban: 0 · Errores: 0 · Total: 2.0 KB", out)
        self.assertEqual(err, "")

    def test_many_with_failures(self) -> None:
        stats = DownloadStats(
            downloaded=3,
            skipped=2,
            failed=2,
            bytes=1500000,
            failures=[("carpeta/a.pdf", "timeout"), ("carpeta/b.pdf", "404")],
        )
        out, err = self.render_stats(stats)
        self.assertIn("Descargados: 3 · Ya estaban: 2 · Errores: 2 · Total: 1.4 MB", out)
        # Los fallos van a stderr, no a stdout.
        self.assertNotIn("a.pdf", out)
        self.assertIn("x carpeta/a.pdf: timeout", err)
        self.assertIn("x carpeta/b.pdf: 404", err)

    def test_dry_run_prints_nothing(self) -> None:
        stats = DownloadStats(downloaded=1, bytes=100, failures=[("a", "b")])
        out, err = self.render_stats(stats, dry_run=True)
        self.assertEqual(out, "")
        self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()

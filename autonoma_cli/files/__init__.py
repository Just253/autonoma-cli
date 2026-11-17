"""Plan, manifiesto, descarga y corrida de los archivos del campus.

Cada pieza vive en su archivo: ``plan`` arma las rutas destino, ``manifest``
guarda lo ya bajado, ``fetch`` baja un archivo y ``run`` ejecuta el plan. Este
``__init__`` reexporta la API publica para que los comandos y ``render`` no
dependan de la ubicacion interna.
"""

from __future__ import annotations

from .fetch import download_file
from .manifest import MANIFEST_NAME, Manifest
from .plan import DownloadItem, build_filename, course_folder, plan_course
from .run import DownloadStats, run_plan

__all__ = [
    "MANIFEST_NAME",
    "DownloadItem",
    "DownloadStats",
    "Manifest",
    "build_filename",
    "course_folder",
    "download_file",
    "plan_course",
    "run_plan",
]

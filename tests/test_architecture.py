"""Guardia de arquitectura: impide que vuelva la duplicacion del refactor.

No prueba comportamiento: fija donde vive cada cosa. Si algo falla, el
mensaje dice que hacer, no solo que un numero no cuadra.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "autonoma_cli"
# Clave = ruta posix relativa al paquete. Antes se usaba path.name, que cegaba
# la guardia a las subcarpetas y hacia colisionar dos settings.py.
MODULES = {
    path.relative_to(PACKAGE).as_posix(): path
    for path in sorted(PACKAGE.rglob("*.py"))
    if "__pycache__" not in path.parts
}
# Duenos legitimos de JSON, uno por formato; el resto usa cache.ensure o render.
LOADS = {"cache.py", "client.py", "downloader.py"}
DUMPS = LOADS | {"render/text.py"}
GRAPH = {"cli.py", "__main__.py"}  # unicos que pueden importar cli

# (patron sobre la ruta posix, maximo de lineas, que hacer si se pasa).
SIZE_RULES = (
    (
        r"cli\.py",
        260,
        "cli.py es solo el parser y el despacho: los run_* van en commands/ y la "
        "salida en render/.",
    ),
    (
        r"commands/.+\.py",
        120,
        "un comando por archivo: si crece, saca el plan a selectors/downloader y "
        "la tabla a render/.",
    ),
    (
        r"config/.+\.py",
        200,
        "un tema por archivo (paths, credenciales, settings, io) en vez de "
        "engordar uno solo.",
    ),
    (
        r"models/.+\.py",
        250,
        "un dominio por archivo (common, courses, resources, sessions, grades): "
        "common es la base y los demas no se importan entre si.",
    ),
    (
        r"render/.+\.py",
        200,
        "un tema por archivo (text, courses, schedule, resources, downloads, "
        "grades): el __init__ solo reexporta.",
    ),
)


def is_config(name: str) -> bool:
    """True para cualquier archivo de ``config/``."""

    return name.startswith("config/")


def is_commands(name: str) -> bool:
    """True para cualquier archivo de ``commands/``."""

    return name.startswith("commands/")


def tree(name: str) -> ast.Module:
    return ast.parse(MODULES[name].read_text(encoding="utf-8"))


def calls(name: str, function: str) -> bool:
    """True si el modulo llama a ``function(...)`` o ``algo.function(...)``."""

    return any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == function
        for node in ast.walk(tree(name))
    )


def defines(name: str, function: str) -> bool:
    """True si el modulo define ``def function(...)`` de nivel superior."""

    return any(
        isinstance(node, ast.FunctionDef) and node.name == function
        for node in ast.walk(tree(name))
    )


def references(name: str, function: str) -> bool:
    """True si el modulo menciona ``function`` como nombre o atributo."""

    return any(
        (isinstance(node, ast.Name) and node.id == function)
        or (isinstance(node, ast.Attribute) and node.attr == function)
        for node in ast.walk(tree(name))
    )


def top_level_functions(name: str) -> list[ast.FunctionDef]:
    return [node for node in tree(name).body if isinstance(node, ast.FunctionDef)]


def exports(name: str) -> set[str]:
    """Nombres que quedan ligados en el modulo (imports y asignaciones)."""

    found: set[str] = set()
    for node in tree(name).body:
        if isinstance(node, ast.ImportFrom):
            found |= {alias.asname or alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {(alias.asname or alias.name).split(".")[0] for alias in node.names}
        elif isinstance(node, ast.Assign):
            found |= {target.id for target in node.targets if isinstance(target, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return found


def imports(name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree(name)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    found.add(node.module.split(".")[0])
                else:
                    found |= {alias.name.split(".")[0] for alias in node.names}
            elif node.module and node.module.split(".")[0] == "autonoma_cli":
                parts = node.module.split(".")
                if len(parts) > 1:
                    found.add(parts[1])
                else:
                    # ``from autonoma_cli import commands`` importa el submodulo.
                    found |= {alias.name.split(".")[0] for alias in node.names}
    return found


class ArchitectureTests(unittest.TestCase):
    def test_modules_stay_small(self) -> None:
        self.assertIn(
            "cli.py", MODULES,
            "cli.py tiene que existir: si cambio de nombre, actualiza esta guardia "
            "antes de seguir (si no, queda ciega).",
        )
        for name, path in MODULES.items():
            for pattern, limit, hint in SIZE_RULES:
                if not re.fullmatch(pattern, name):
                    continue
                lines = len(path.read_text(encoding="utf-8").splitlines())
                with self.subTest(module=name):
                    self.assertLessEqual(
                        lines, limit,
                        f"{name} tiene {lines} lineas (maximo {limit}): {hint}",
                    )

    def test_tests_stay_small(self) -> None:
        """Los tests se leen por tarea: ninguno pasa de 300 lineas.

        Va aparte de SIZE_RULES porque MODULES solo recorre autonoma_cli/, asi
        que un patron ``tests/...`` nunca matchearia. Esta guardia se exime a
        si misma: es el archivo que fija la regla.
        """

        limit = 300
        checked = [
            path
            for path in sorted(Path(__file__).parent.glob("test_*.py"))
            if path.name != Path(__file__).name
        ]
        self.assertTrue(
            checked,
            "no se encontro ningun archivo test_*.py junto a esta guardia: si los "
            "tests se mudaron de carpeta, actualiza la ruta antes de seguir (si no, "
            "queda ciega).",
        )
        for path in checked:
            lines = len(path.read_text(encoding="utf-8").splitlines())
            with self.subTest(test=path.name):
                self.assertLessEqual(
                    lines, limit,
                    f"tests/{path.name} tiene {lines} lineas "
                    f"(maximo {limit}): parte el archivo por dominio y deja las "
                    "fixtures en tests/support/.",
                )

    def test_cli_and_commands_do_not_print(self) -> None:
        for name in (n for n in MODULES if n == "cli.py" or is_commands(n)):
            with self.subTest(module=name):
                self.assertFalse(
                    calls(name, "print"),
                    f"{name} no imprime: usa render.text/emit_json o ui.table.",
                )

    def test_cache_is_written_from_cache_module(self) -> None:
        users = {name for name in MODULES
                 if defines(name, "write_private_text") or references(name, "write_private_text")}
        owners = sorted(name for name in users if is_config(name))
        self.assertEqual(
            len(owners), 1,
            "write_private_text lo define y usa un solo archivo de config "
            f"(config/io.py), pero aparece en {owners}: deja una sola "
            "implementacion y que la cache la importe de ahi.",
        )
        self.assertEqual(
            sorted(users), ["cache.py", *owners],
            "write_private_text es de config/io.py y la cache la guarda solo "
            "cache.py (cache.ensure): commands/ no persiste nada a mano. "
            f"Usuarios encontrados: {sorted(users)}.",
        )

    def test_json_belongs_to_a_format_owner(self) -> None:
        readers = LOADS | {name for name in MODULES if is_config(name)}
        writers = DUMPS | {name for name in MODULES if is_config(name)}
        with self.subTest(kind="loads"):
            for name in MODULES.keys() - readers:
                self.assertFalse(
                    calls(name, "loads"),
                    f"{name} no lee JSON a mano: la cache pasa por cache.ensure "
                    f"(lectores permitidos: {sorted(readers)}); prohibido en cli.py, "
                    "commands*, models.py, selectors.py y ui.py.",
                )
        with self.subTest(kind="dumps"):
            for name in MODULES.keys() - writers:
                self.assertFalse(
                    calls(name, "dumps"),
                    f"{name} no escribe JSON a mano: la cache la guarda cache.py y la "
                    f"salida --json render.emit_json (permitidos: {sorted(writers)}); "
                    "prohibido en cli.py, commands*, models.py, selectors.py y ui.py.",
                )

    def test_import_graph(self) -> None:
        self.assertFalse(
            [name for name in MODULES.keys() - GRAPH if "cli" in imports(name)],
            "solo cli.py y __main__.py importan cli: el grafo es "
            "cli -> commands -> {cache, render, selectors, client, ...}.",
        )
        commands_ok = GRAPH | {name for name in MODULES if is_commands(name)}
        self.assertFalse(
            [name for name in MODULES.keys() - commands_ok if "commands" in imports(name)],
            "commands/ solo lo importa cli.py: si otro modulo lo importa, hay un ciclo.",
        )

    def test_every_run_takes_client_first(self) -> None:
        for name in (n for n in MODULES if is_commands(n)):
            for node in top_level_functions(name):
                if not node.name.startswith("run_"):
                    continue
                params = node.args.args
                with self.subTest(module=name, function=node.name):
                    self.assertTrue(
                        params and params[0].arg == "client",
                        f"{name}:{node.lineno} {node.name} debe ser "
                        f"{node.name}(client, args): el cliente se inyecta desde "
                        "cli.main, no se construye adentro.",
                    )

        init = "commands/__init__.py"
        if init not in MODULES:
            return
        available = exports(init)
        missing = [
            f"{node.name} (en {name})"
            for name in MODULES
            if name.startswith("commands/") and name != init
            for node in top_level_functions(name)
            if node.name.startswith("run_") and node.name not in available
        ]
        self.assertFalse(
            missing,
            f"{init} no reexporta {missing}: cli.py hace "
            "set_defaults(func=commands.run_x) y el AttributeError aparece al "
            "ejecutar el comando, no al importar. Agrega el `from .modulo import run_x`.",
        )

    def test_strip_html_is_defined_once(self) -> None:
        defined = {
            (name, node.name)
            for name in MODULES
            for node in ast.walk(tree(name))
            if isinstance(node, ast.FunctionDef) and node.name in {"strip_html", "_strip_tags"}
        }
        self.assertEqual(
            defined, {("models/common.py", "strip_html")},
            "strip_html se define una sola vez en models/common.py: client.py "
            "importa esa version y no trae su propio _strip_tags "
            f"(encontrado: {sorted(defined)}).",
        )

    def test_only_commands_builds_the_campus_client(self) -> None:
        builders = {name for name in MODULES if calls(name, "CampusClient")}
        self.assertTrue(
            "commands/base.py" in builders,
            "commands.client_for es quien construye CampusClient: cli.py solo lo "
            "importa para anotar el tipo.",
        )
        self.assertLessEqual(
            builders, {"client.py", "commands/base.py"},
            f"CampusClient solo se instancia en commands.client_for (lo instancian "
            f"{sorted(builders)}): el resto lo recibe como argumento.",
        )

    def test_subpackages_have_init(self) -> None:
        offenders = sorted(
            folder.relative_to(PACKAGE).as_posix()
            for folder in PACKAGE.rglob("*")
            if folder.is_dir()
            and folder.name != "__pycache__"
            and any(folder.glob("*.py"))
            and not (folder / "__init__.py").is_file()
        )
        self.assertFalse(
            offenders,
            f"estas subcarpetas tienen .py pero les falta __init__.py: {offenders}. "
            "Sin el paquete no se importa en el wheel instalado aunque en el repo "
            "parezca funcionar.",
        )


if __name__ == "__main__":
    unittest.main()

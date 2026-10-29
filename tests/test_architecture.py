"""Guardia de arquitectura: impide que vuelva la duplicacion del refactor.

No prueba comportamiento: fija donde vive cada cosa. Si algo falla, el
mensaje dice que hacer, no solo que un numero no cuadra.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "autonoma_cli"
MODULES = {path.name: path for path in sorted(PACKAGE.glob("*.py"))}
# Duenos legitimos de JSON, uno por formato; el resto usa cache.ensure o render.
LOADS = {"cache.py", "client.py", "config.py", "downloader.py"}
DUMPS = LOADS | {"render.py"}
GRAPH = {"cli.py", "__main__.py"}  # unicos que pueden importar cli


def tree(name: str) -> ast.Module:
    return ast.parse(MODULES[name].read_text(encoding="utf-8"))


def calls(name: str, function: str) -> bool:
    """True si el modulo llama a ``function(...)`` o ``algo.function(...)``."""
    return any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == function
        for node in ast.walk(tree(name))
    )


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
                found.add(node.module.split(".")[1] if "." in node.module else "")
    return found


class ArchitectureTests(unittest.TestCase):
    def test_modules_stay_small(self) -> None:
        for name, limit in {"cli.py": 260, "commands.py": 500}.items():
            lines = len(MODULES[name].read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(
                lines, limit,
                f"{name} tiene {lines} lineas (maximo {limit}): los run_* van en "
                "commands.py y la salida en render.py.",
            )

    def test_cli_and_commands_do_not_print(self) -> None:
        for name in ("cli.py", "commands.py"):
            self.assertFalse(
                calls(name, "print"),
                f"{name} no imprime: usa render.text/emit_json o ui.table.",
            )

    def test_cache_is_written_from_cache_module(self) -> None:
        users = sorted(name for name, path in MODULES.items()
                       if "write_private_text" in path.read_text(encoding="utf-8"))
        self.assertEqual(
            users, ["cache.py", "config.py"],
            "write_private_text es de config.py y la cache la guarda solo cache.py "
            "(cache.ensure): commands.py no persiste nada a mano.",
        )

    def test_json_readers_belong_to_a_format_owner(self) -> None:
        for name in MODULES.keys() - LOADS:
            self.assertFalse(
                calls(name, "loads"),
                f"{name} no lee JSON a mano: la cache pasa por cache.ensure "
                f"(lectores permitidos: {sorted(LOADS)}).",
            )

    def test_json_writers_belong_to_a_format_owner(self) -> None:
        for name in MODULES.keys() - DUMPS:
            self.assertFalse(
                calls(name, "dumps"),
                f"{name} no escribe JSON a mano: la cache la guarda cache.py y la "
                f"salida --json render.emit_json (permitidos: {sorted(DUMPS)}).",
            )

    def test_import_graph(self) -> None:
        self.assertFalse(
            [name for name in MODULES.keys() - GRAPH if "cli" in imports(name)],
            "solo cli.py y __main__.py importan cli: el grafo es "
            "cli -> commands -> {cache, render, selectors, client, ...}.",
        )
        self.assertFalse(
            [name for name in MODULES.keys() - {"cli.py", "commands.py"}
             if "commands" in imports(name)],
            "commands.py solo lo importa cli.py: si otro modulo lo importa, hay un ciclo.",
        )

    def test_every_run_takes_client_first(self) -> None:
        for node in tree("commands.py").body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("run_"):
                params = node.args.args
                self.assertTrue(
                    params and params[0].arg == "client",
                    f"commands.{node.name} debe ser {node.name}(client, args): el "
                    "cliente se inyecta desde cli.main, no se construye adentro.",
                )

    def test_strip_html_is_defined_once(self) -> None:
        defined = {
            (name, node.name)
            for name in MODULES
            for node in ast.walk(tree(name))
            if isinstance(node, ast.FunctionDef) and node.name in {"strip_html", "_strip_tags"}
        }
        self.assertEqual(
            defined, {("models.py", "strip_html")},
            "strip_html se define una sola vez en models.py: client.py importa esa "
            "version y no trae su propio _strip_tags.",
        )

    def test_only_commands_builds_the_campus_client(self) -> None:
        builders = {name for name in MODULES if calls(name, "CampusClient")}
        self.assertIn(
            "commands.py", builders,
            "commands.client_for es quien construye CampusClient: cli.py solo lo "
            "importa para anotar el tipo.",
        )
        self.assertLessEqual(
            builders, {"client.py", "commands.py"},
            f"CampusClient solo se instancia en commands.client_for (lo instancian "
            f"{builders}): el resto lo recibe como argumento.",
        )


if __name__ == "__main__":
    unittest.main()

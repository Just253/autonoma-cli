"""Guardia de arquitectura: evita que la logica se duplique entre capas.

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
# net.py lee y escribe pinned-ip.json, el pin de la IP que valido certificado.
LOADS = {"cache.py", "client.py", "downloader.py", "net.py"}
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
    (
        r"uploadcheck\.py",
        120,
        "uploadcheck.py valida archivo y textos antes de la red: el plan y la "
        "corrida van en uploader.py.",
    ),
    (
        r"uploader\.py",
        260,
        "uploader.py es el plan y la corrida de una subida: el multipart, el XML "
        "y el parseo van en uploadform.py.",
    ),
    (
        r"uploadform\.py",
        200,
        "uploadform.py es el contrato del campus (multipart, XML y respuestas); "
        "la validacion y la corrida van en uploader.py.",
    ),
)

# Catch-all: ningun modulo del paquete crece sin tope. Los que ya pasaban de
# 250 cuando se creo esta regla quedan congelados en su tamano actual: solo
# pueden bajar. Para partir uno grande, mueve una responsabilidad a otro
# archivo.
MODULE_MAX = 250
SIZE_RATCHET = {
    "cli.py": 251,  # ya pasaba el catch-all; su regla propia lo deja en 260
    "client.py": 673,  # 858 -> 732 -> 673 al extraer net.py y session.py; solo puede bajar
    "downloader.py": 323,  # solo puede bajar
}

# Nombres privados que un modulo le pide a otro. Hoy esta vacio: el nombre
# privado pertenece al dueno y se importa desde su API publica. Si hace falta
# una excepcion, va aca con su motivo y el test falla si queda huerfana.
PRIVATE_IMPORTS_OK: frozenset[tuple[str, str, str]] = frozenset()

# Direccion de dependencias: cada capa solo importa las capas de su lista. Una
# clave terminada en "/" cubre la carpeta entera; el resto, un modulo exacto.
# Un modulo sin regla hace fallar la guardia: una capa nueva no entra callada.
ALLOWED_LAYERS = {
    "__init__.py": frozenset(),
    "__main__.py": frozenset({"cli"}),
    "cli.py": frozenset({"commands", "config", "selectors", "ui", "client", "errors"}),
    "commands/": frozenset({
        "commands", "cache", "config", "models", "selectors", "ui", "render",
        "client", "downloader", "errors", "uploader",
    }),
    "render/": frozenset({"render", "models", "ui"}),
    "uploader.py": frozenset({
        "client", "errors", "models", "uploadcheck", "uploadform",
    }),
    "uploadform.py": frozenset({"client", "errors"}),
    "uploadcheck.py": frozenset({"errors", "ui"}),
    "downloader.py": frozenset({"models", "errors", "net"}),
    "client.py": frozenset({"config", "models", "errors", "session"}),
    "session.py": frozenset({"net", "errors"}),
    "selectors.py": frozenset({"models", "errors"}),
    "cache.py": frozenset({"config"}),
    "models/": frozenset({"models", "errors"}),
    "config/": frozenset({"config"}),
    "ui.py": frozenset(),
    "net.py": frozenset(),
    "errors.py": frozenset(),
}

# Aristas que la tabla prohibe pero que hoy existen. La guardia falla si
# aparece una nueva y tambien si una de estas desaparece sin borrar su
# excepcion.
KNOWN_EDGES = {
    ("render/downloads.py", "downloader"): "human_size deberia vivir en ui.py",
    ("render/upload.py", "downloader"): "human_size deberia vivir en ui.py",
    ("uploadcheck.py", "downloader"): "human_size deberia vivir en ui.py",
    ("uploader.py", "client._call"): "usar client.call() publico",
}


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


def layers() -> set[str]:
    """Nombre de cada capa: primer componente de la ruta, sin ``.py``."""

    return {name.split("/")[0].removesuffix(".py") for name in MODULES}


def relative_target(name: str, node: ast.ImportFrom) -> str:
    """Modulo destino de un ``ImportFrom`` relativo, resuelto desde ``name``."""

    package = Path(name).parent.as_posix()
    parts = [] if package == "." else package.split("/")
    up = node.level - 1
    if up:
        parts = parts[:-up] if up <= len(parts) else []
    if node.module:
        parts += node.module.split(".")
    return ".".join(parts)


def imported_targets(name: str, node: ast.ImportFrom) -> list[str]:
    """Modulos internos a los que apunta un ``ImportFrom``.

    Cubre las dos formas que existen en el paquete: relativa (``from .net``) y
    absoluta (``from autonoma_cli.net``); si la absoluta no se mirara, una capa
    nueva podria saltarse la tabla escribiendo el nombre completo.
    """

    if node.level:
        base = relative_target(name, node)
        if node.module:
            return [base]
        return [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
    if node.module and node.module.split(".")[0] == "autonoma_cli":
        rest = ".".join(node.module.split(".")[1:])
        if rest:
            return [rest]
        return [alias.name.split(".")[0] for alias in node.names]
    return []


def imported_layers(name: str) -> set[str]:
    """Capas internas que ``name`` importa."""

    known = layers()
    found: set[str] = set()
    for node in ast.walk(tree(name)):
        if isinstance(node, ast.ImportFrom):
            found |= {target.split(".")[0] for target in imported_targets(name, node)}
    return found & known


def private_imports(name: str) -> set[tuple[str, str, str]]:
    """``(modulo, dueno, nombre)`` de cada ``from .x import _y``."""

    found: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree(name)):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue  # ``from . import _modulo`` importa el modulo, no un nombre
        targets = imported_targets(name, node)
        if not targets:
            continue
        found |= {
            (name, targets[0], alias.name)
            for alias in node.names
            if alias.name.startswith("_") and not alias.name.startswith("__")
        }
    return found


def allowed_layers(name: str) -> frozenset[str] | None:
    """Capas que ``name`` puede importar, o ``None`` si no tiene regla."""

    if name in ALLOWED_LAYERS:
        return ALLOWED_LAYERS[name]
    for prefix, allowed in ALLOWED_LAYERS.items():
        if prefix.endswith("/") and name.startswith(prefix):
            return allowed
    return None


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

    def test_every_module_has_a_size_cap(self) -> None:
        """Catch-all: hasta los modulos sin regla propia tienen tope.

        Un modulo nuevo nace por debajo de 250. Los que ya pasaban el maximo
        cuando se agrego la regla quedan en SIZE_RATCHET con su tamano
        congelado: solo pueden bajar.
        """

        self.assertTrue(
            MODULES,
            "no se encontro ningun modulo en autonoma_cli/: si el paquete cambio "
            "de lugar, actualiza PACKAGE (si no, la guardia queda ciega).",
        )
        stale = sorted(name for name in SIZE_RATCHET if name not in MODULES)
        self.assertFalse(
            stale,
            f"SIZE_RATCHET nombra modulos que ya no existen: {stale}. Si los "
            "partiste o renombraste, actualiza o borra su tope.",
        )
        for name, path in MODULES.items():
            limit = SIZE_RATCHET.get(name, MODULE_MAX)
            lines = len(path.read_text(encoding="utf-8").splitlines())
            with self.subTest(module=name):
                self.assertLessEqual(
                    lines, limit,
                    f"{name} tiene {lines} lineas (maximo {limit}): un modulo nuevo "
                    f"no pasa de {MODULE_MAX}, asi que saca una responsabilidad a "
                    "otro archivo. Si el modulo ya tenia un tope congelado, ese "
                    "tope solo puede bajar; no lo subas para que entre un cambio: "
                    "mueve codigo a otro archivo.",
                )

    def test_no_new_private_imports(self) -> None:
        """``from .x import _y`` no se agrega: el nombre privado es del dueno.

        Hoy PRIVATE_IMPORTS_OK esta vacio: el paquete no importa nombres
        privados de otro modulo. La lista existe solo para excepciones
        justificadas y el test falla si una queda huerfana.
        """

        found: set[tuple[str, str, str]] = set()
        for name in MODULES:
            found |= private_imports(name)
        new = sorted(found - PRIVATE_IMPORTS_OK)
        self.assertFalse(
            new,
            "imports privados nuevos: "
            + ", ".join(f"{mod} importa {key} de {owner}" for mod, owner, key in new)
            + ". Usa la API publica del dueno (net.cert_mismatch, client.call, "
            "ui.human_size...) o mueve la funcion al modulo que la define; si es "
            "una excepcion justificada, registra el par en PRIVATE_IMPORTS_OK con "
            "su motivo.",
        )
        stale = sorted(PRIVATE_IMPORTS_OK - found)
        self.assertFalse(
            stale,
            "PRIVATE_IMPORTS_OK tiene excepciones que ya no existen: "
            + ", ".join(f"{mod} -> {owner}.{key}" for mod, owner, key in stale)
            + ". Borralas: la lista de excepciones solo puede encoger.",
        )

    def test_dependency_direction(self) -> None:
        """Cada capa mira solo hacia abajo; las excepciones estan en KNOWN_EDGES."""

        uncovered = sorted(name for name in MODULES if allowed_layers(name) is None)
        self.assertFalse(
            uncovered,
            f"modulos sin regla de direccion: {uncovered}. Agrega la capa a "
            "ALLOWED_LAYERS en el mismo commit que la crea; si no, la guardia "
            "queda ciega justo donde aparece el codigo nuevo.",
        )
        edges: set[tuple[str, str]] = set()
        for name in MODULES:
            allowed = allowed_layers(name) or frozenset()
            edges |= {(name, layer) for layer in imported_layers(name) - allowed}
        for name in MODULES:
            if name == "client.py":
                continue
            if any(
                isinstance(node, ast.Attribute) and node.attr == "_call"
                for node in ast.walk(tree(name))
            ):
                edges.add((name, "client._call"))
        new = sorted(edges - set(KNOWN_EDGES))
        self.assertFalse(
            new,
            "aristas nuevas contra la direccion: "
            + ", ".join(f"{src} -> {dst}" for src, dst in new)
            + ". Mira ALLOWED_LAYERS: si la capa destino es correcta, agrega la "
            "capa a la lista; si no, mueve el codigo a su capa. client._call solo "
            "se usa dentro de client.py; uploader deberia llamar a client.call().",
        )
        stale = sorted(set(KNOWN_EDGES) - edges)
        self.assertFalse(
            stale,
            "KNOWN_EDGES tiene aristas que ya no existen: "
            + ", ".join(f"{src} -> {dst}" for src, dst in stale)
            + ". Borralas en el mismo commit que elimina la arista.",
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

    def test_upload_contract_lives_in_uploadform(self) -> None:
        """El multipart y el XML de la subida se arman en un solo modulo.

        Si otro modulo arma su propio formulario u otro XML, hay dos caminos
        escribiendo en el campus con contratos distintos.
        """

        builders = {"multipart_body", "resource_xml", "task_xml"}
        found = sorted(
            name
            for name in MODULES
            for node in ast.walk(tree(name))
            if isinstance(node, ast.FunctionDef) and node.name in builders
        )
        self.assertEqual(
            set(found), {"uploadform.py"},
            "multipart_body, resource_xml y task_xml se definen solo en "
            f"uploadform.py, y uploader.py los llama desde ahi (encontrado: {found}).",
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

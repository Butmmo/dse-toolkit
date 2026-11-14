"""Start a new project in any of these languages, with a real test and a git repository:

  node (JavaScript API, no dependencies)   typescript (Node + tsc)   python-cli   python-api (FastAPI)
  java (Maven + JUnit)   kotlin (Gradle)   csharp (.NET + xUnit)   c (CMake)   cpp (CMake)
  dart (CLI)   flutter (app)   go   rust   powershell (module + Pester test)

The files are written by this program, so it works offline. With official=True it first runs the language's own generator when it is installed
(flutter create, dart create, dotnet new, cargo new, go mod init, npm init) and adds ours on top. A language whose tools are not installed still gets
its project; `dev run` then tells you exactly what to install. For the web, phone, desktop and TV apps use the App Builder (builder/build.py).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import config, gitops
from .sandbox import Refused, run, workspace

LANGS = {
    "node": "JavaScript API (Node, no dependencies, node:test)", "typescript": "TypeScript (Node, tsc)", "python-cli": "Python command line tool (unittest)",
    "python-api": "Python web API (FastAPI, pytest)", "java": "Java (Maven, JUnit 5)", "kotlin": "Kotlin (Gradle, kotlin.test)", "csharp": ".NET C# (console + xUnit)",
    "c": "C (CMake, ctest)", "cpp": "C++17 (CMake, ctest)", "dart": "Dart command line (package:test)", "flutter": "Flutter app (widget test)", "go": "Go (go test)",
    "rust": "Rust (cargo test)", "powershell": "PowerShell module (Pester)",
}
GITIGNORE = {
    "node": "node_modules/\n.env\n.env.*\ncoverage/\n", "typescript": "node_modules/\ndist/\n.env\n.env.*\n", "python-cli": ".venv/\n__pycache__/\n*.egg-info/\n.env\ndist/\nbuild/\n",
    "python-api": ".venv/\n__pycache__/\n.env\n.pytest_cache/\n", "java": "target/\n.idea/\n*.class\n", "kotlin": "build/\n.gradle/\n.idea/\n*.class\n", "csharp": "bin/\nobj/\n.vs/\n*.user\n",
    "c": "build/\n", "cpp": "build/\n", "dart": ".dart_tool/\nbuild/\n.packages\n", "flutter": ".dart_tool/\nbuild/\n.flutter-plugins*\n.idea/\nandroid/local.properties\n", "go": "bin/\n*.exe\n",
    "rust": "target/\n", "powershell": "*.log\n",
}


def names(project: str) -> dict:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", project) if w] or ["app"]
    snake = "_".join(w.lower() for w in words)
    if snake[0].isdigit():
        snake = "app_" + snake
    pascal = "".join(w.capitalize() for w in words)
    if pascal[0].isdigit():
        pascal = "App" + pascal
    return {"kebab": "-".join(w.lower() for w in words), "snake": snake, "pascal": pascal, "flat": "".join(w.lower() for w in words) if not words[0][0].isdigit() else "app" + "".join(w.lower() for w in words)}


def files_for(lang: str, project: str) -> dict[str, str]:
    n = names(project)
    k, s, P, flat = n["kebab"], n["snake"], n["pascal"], n["flat"]
    if lang == "node":
        return {
            "package.json": f'{{\n  "name": "{k}",\n  "version": "0.1.0",\n  "private": true,\n  "type": "module",\n  "scripts": {{ "start": "node src/server.js", "test": "node --test" }}\n}}\n',
            "src/server.js": ('import { createServer } from "node:http";\n\nconst items = [];\n\nexport function makeServer() {\n  return createServer(async (req, res) => {\n'
                              '    const json = (code, body) => { res.writeHead(code, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };\n'
                              '    if (req.url === "/health") return json(200, { ok: true });\n'
                              '    if (req.url === "/api/items" && req.method === "GET") return json(200, items);\n'
                              '    if (req.url === "/api/items" && req.method === "POST") {\n      let raw = "";\n      for await (const c of req) raw += c;\n'
                              '      try { const { name } = JSON.parse(raw); if (!name) return json(400, { error: "name is required" }); const item = { id: items.length + 1, name }; items.push(item); return json(201, item); }\n'
                              '      catch { return json(400, { error: "send JSON" }); }\n    }\n    json(404, { error: "not found" });\n  });\n}\n\n'
                              'if (import.meta.url === `file://${process.argv[1].replace(/\\\\/g, "/")}` || process.argv[1]?.endsWith("server.js")) {\n  const port = Number(process.env.PORT ?? 3000);\n  makeServer().listen(port, () => console.log(`listening on http://localhost:${port}`));\n}\n'),
            "test/server.test.js": ('import test from "node:test";\nimport assert from "node:assert/strict";\nimport { makeServer } from "../src/server.js";\n\n'
                                   'test("health, create and list", async () => {\n  const server = makeServer();\n  await new Promise((r) => server.listen(0, r));\n  const base = `http://127.0.0.1:${server.address().port}`;\n'
                                   '  assert.deepEqual(await (await fetch(`${base}/health`)).json(), { ok: true });\n'
                                   '  const made = await fetch(`${base}/api/items`, { method: "POST", body: JSON.stringify({ name: "first" }) });\n  assert.equal(made.status, 201);\n'
                                   '  assert.equal((await (await fetch(`${base}/api/items`)).json()).length, 1);\n'
                                   '  assert.equal((await fetch(`${base}/api/items`, { method: "POST", body: "{}" })).status, 400);\n  server.close();\n});\n'),
            "README.md": f"# {project}\n\nA small JavaScript API with no dependencies.\n\n```bash\nnpm test\nnpm start\n```\n",
        }
    if lang == "typescript":
        return {
            "package.json": f'{{\n  "name": "{k}",\n  "version": "0.1.0",\n  "private": true,\n  "type": "module",\n  "scripts": {{ "build": "tsc", "test": "node --test test/*.test.ts" }},\n  "devDependencies": {{ "typescript": "^5.6.0", "@types/node": "^22.0.0" }}\n}}\n',
            "tsconfig.json": '{\n  "compilerOptions": { "target": "ES2022", "module": "NodeNext", "moduleResolution": "NodeNext", "strict": true, "outDir": "dist", "rootDir": "src", "skipLibCheck": true },\n  "include": ["src"]\n}\n',
            "src/greeter.ts": 'export function greet(name: string): string {\n  const clean = name.trim();\n  if (!clean) throw new Error("name is required");\n  return `Hello, ${clean}!`;\n}\n',
            "src/index.ts": 'import { greet } from "./greeter.js";\n\nconsole.log(greet(process.argv[2] ?? "world"));\n',
            "test/greeter.test.ts": 'import test from "node:test";\nimport assert from "node:assert/strict";\nimport { greet } from "../src/greeter.ts";\n\ntest("greets", () => assert.equal(greet(" Ada "), "Hello, Ada!"));\ntest("needs a name", () => assert.throws(() => greet("  ")));\n',
            "README.md": f"# {project}\n\nTypeScript on Node. Tests run directly on Node 22.18 or newer (it understands TypeScript); `npm run build` compiles with tsc.\n\n```bash\nnpm install\nnpm test\nnpm run build\n```\n",
        }
    if lang == "python-cli":
        return {
            "pyproject.toml": f'[build-system]\nrequires = ["setuptools>=68"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "{k}"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n\n[project.scripts]\n{k} = "{s}.cli:main"\n\n[tool.setuptools.packages.find]\nwhere = ["src"]\n',
            f"src/{s}/__init__.py": '__version__ = "0.1.0"\n',
            f"src/{s}/cli.py": 'import argparse\n\n\ndef greet(name: str) -> str:\n    name = name.strip()\n    if not name:\n        raise ValueError("name is required")\n    return f"Hello, {name}!"\n\n\n'
                               'def main(argv=None) -> int:\n    p = argparse.ArgumentParser(description="A small command line tool.")\n    p.add_argument("name", nargs="?", default="world")\n    a = p.parse_args(argv)\n    print(greet(a.name))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
            "tests/test_cli.py": f'import sys\nimport unittest\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))\nfrom {s}.cli import greet, main  # noqa: E402\n\n\nclass CliTest(unittest.TestCase):\n    def test_greet(self):\n        self.assertEqual(greet(" Ada "), "Hello, Ada!")\n\n    def test_needs_a_name(self):\n        with self.assertRaises(ValueError):\n            greet("  ")\n\n    def test_main(self):\n        self.assertEqual(main(["Bolu"]), 0)\n\n\nif __name__ == "__main__":\n    unittest.main()\n',
            "README.md": f"# {project}\n\nA small Python command line tool.\n\n```bash\npython -m unittest discover -s tests -v\npython -m {s}.cli Ada   (after: pip install -e .)\n```\n",
        }
    if lang == "python-api":
        return {
            "requirements.txt": "fastapi>=0.110\nuvicorn>=0.29\npytest>=8\nhttpx>=0.27\n",
            "app/__init__.py": "",
            "app/main.py": 'from fastapi import FastAPI, HTTPException\nfrom pydantic import BaseModel\n\napp = FastAPI(title="' + project + '")\nitems: list[dict] = []\n\n\nclass ItemIn(BaseModel):\n    name: str\n\n\n'
                           '@app.get("/health")\ndef health():\n    return {"ok": True}\n\n\n@app.get("/api/items")\ndef list_items():\n    return items\n\n\n@app.post("/api/items", status_code=201)\ndef add_item(body: ItemIn):\n    if not body.name.strip():\n        raise HTTPException(400, "name is required")\n    item = {"id": len(items) + 1, "name": body.name.strip()}\n    items.append(item)\n    return item\n',
            "tests/test_main.py": 'from fastapi.testclient import TestClient\n\nfrom app.main import app\n\nc = TestClient(app)\n\n\ndef test_health():\n    assert c.get("/health").json() == {"ok": True}\n\n\ndef test_create_and_list():\n    assert c.post("/api/items", json={"name": "first"}).status_code == 201\n    assert len(c.get("/api/items").json()) >= 1\n\n\ndef test_name_required():\n    assert c.post("/api/items", json={"name": "  "}).status_code == 400\n',
            "pytest.ini": "[pytest]\npythonpath = .\n",
            "README.md": f"# {project}\n\nA FastAPI service.\n\n```bash\npip install -r requirements.txt\npytest\nuvicorn app.main:app --reload\n```\n",
        }
    if lang == "java":
        pkg = f"com.example.{flat}"
        pdir = pkg.replace(".", "/")
        return {
            "pom.xml": f'<?xml version="1.0" encoding="UTF-8"?>\n<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">\n'
                       f'  <modelVersion>4.0.0</modelVersion>\n  <groupId>com.example</groupId>\n  <artifactId>{k}</artifactId>\n  <version>0.1.0</version>\n  <packaging>jar</packaging>\n'
                       '  <properties>\n    <maven.compiler.release>21</maven.compiler.release>\n    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>\n  </properties>\n'
                       '  <dependencies>\n    <dependency>\n      <groupId>org.junit.jupiter</groupId>\n      <artifactId>junit-jupiter</artifactId>\n      <version>5.10.2</version>\n      <scope>test</scope>\n    </dependency>\n  </dependencies>\n'
                       '  <build>\n    <plugins>\n      <plugin>\n        <groupId>org.apache.maven.plugins</groupId>\n        <artifactId>maven-surefire-plugin</artifactId>\n        <version>3.2.5</version>\n      </plugin>\n    </plugins>\n  </build>\n</project>\n',
            f"src/main/java/{pdir}/Greeter.java": f"package {pkg};\n\npublic final class Greeter {{\n    private Greeter() {{}}\n\n    public static String greet(String name) {{\n        if (name == null || name.isBlank()) {{\n            throw new IllegalArgumentException(\"name is required\");\n        }}\n        return \"Hello, \" + name.trim() + \"!\";\n    }}\n}}\n",
            f"src/main/java/{pdir}/App.java": f"package {pkg};\n\npublic class App {{\n    public static void main(String[] args) {{\n        System.out.println(Greeter.greet(args.length > 0 ? args[0] : \"world\"));\n    }}\n}}\n",
            f"src/test/java/{pdir}/GreeterTest.java": f"package {pkg};\n\nimport static org.junit.jupiter.api.Assertions.assertEquals;\nimport static org.junit.jupiter.api.Assertions.assertThrows;\n\nimport org.junit.jupiter.api.Test;\n\nclass GreeterTest {{\n    @Test\n    void greets() {{\n        assertEquals(\"Hello, Ada!\", Greeter.greet(\" Ada \"));\n    }}\n\n    @Test\n    void needsAName() {{\n        assertThrows(IllegalArgumentException.class, () -> Greeter.greet(\" \"));\n    }}\n}}\n",
            "README.md": f"# {project}\n\nJava with Maven and JUnit 5 (needs JDK 21).\n\n```bash\nmvn test\nmvn package\njava -cp target/classes {pkg}.App Ada\n```\n",
        }
    if lang == "kotlin":
        return {
            "settings.gradle.kts": f'rootProject.name = "{k}"\n',
            "build.gradle.kts": 'plugins {\n    kotlin("jvm") version "2.0.21"\n    application\n}\n\nrepositories { mavenCentral() }\n\ndependencies { testImplementation(kotlin("test")) }\n\n'
                                'kotlin { jvmToolchain(21) }\n\napplication { mainClass.set("MainKt") }\n\ntasks.test { useJUnitPlatform() }\n',
            "src/main/kotlin/Greeter.kt": 'fun greet(name: String): String {\n    require(name.isNotBlank()) { "name is required" }\n    return "Hello, ${name.trim()}!"\n}\n',
            "src/main/kotlin/Main.kt": 'fun main(args: Array<String>) {\n    println(greet(args.firstOrNull() ?: "world"))\n}\n',
            "src/test/kotlin/GreeterTest.kt": 'import kotlin.test.Test\nimport kotlin.test.assertEquals\nimport kotlin.test.assertFailsWith\n\nclass GreeterTest {\n    @Test\n    fun greets() = assertEquals("Hello, Ada!", greet(" Ada "))\n\n    @Test\n    fun needsAName() {\n        assertFailsWith<IllegalArgumentException> { greet("  ") }\n    }\n}\n',
            "README.md": f"# {project}\n\nKotlin on the JVM with Gradle (install Gradle and JDK 21, then run `gradle wrapper` once to add ./gradlew).\n\n```bash\ngradle test\ngradle run --args=Ada\n```\n",
        }
    if lang == "csharp":
        return {
            f"{P}.sln": ('\nMicrosoft Visual Studio Solution File, Format Version 12.00\n# Visual Studio Version 17\n'
                         f'Project("{{9A19103F-16F7-4668-BE54-9A1E7A4F7556}}") = "App", "App\\App.csproj", "{{11111111-1111-1111-1111-111111111111}}"\nEndProject\n'
                         f'Project("{{9A19103F-16F7-4668-BE54-9A1E7A4F7556}}") = "Tests", "Tests\\Tests.csproj", "{{22222222-2222-2222-2222-222222222222}}"\nEndProject\n'
                         'Global\n\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n\t\tDebug|Any CPU = Debug|Any CPU\n\t\tRelease|Any CPU = Release|Any CPU\n\tEndGlobalSection\n'
                         '\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n'
                         '\t\t{11111111-1111-1111-1111-111111111111}.Debug|Any CPU.ActiveCfg = Debug|Any CPU\n\t\t{11111111-1111-1111-1111-111111111111}.Debug|Any CPU.Build.0 = Debug|Any CPU\n'
                         '\t\t{11111111-1111-1111-1111-111111111111}.Release|Any CPU.ActiveCfg = Release|Any CPU\n\t\t{11111111-1111-1111-1111-111111111111}.Release|Any CPU.Build.0 = Release|Any CPU\n'
                         '\t\t{22222222-2222-2222-2222-222222222222}.Debug|Any CPU.ActiveCfg = Debug|Any CPU\n\t\t{22222222-2222-2222-2222-222222222222}.Debug|Any CPU.Build.0 = Debug|Any CPU\n'
                         '\t\t{22222222-2222-2222-2222-222222222222}.Release|Any CPU.ActiveCfg = Release|Any CPU\n\t\t{22222222-2222-2222-2222-222222222222}.Release|Any CPU.Build.0 = Release|Any CPU\n'
                         '\tEndGlobalSection\nEndGlobal\n'),
            "App/App.csproj": '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <OutputType>Exe</OutputType>\n    <TargetFramework>net8.0</TargetFramework>\n    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n  </PropertyGroup>\n</Project>\n',
            "App/Greeter.cs": 'namespace App;\n\npublic static class Greeter\n{\n    public static string Greet(string? name)\n    {\n        if (string.IsNullOrWhiteSpace(name)) throw new ArgumentException("name is required");\n        return $"Hello, {name.Trim()}!";\n    }\n}\n',
            "App/Program.cs": 'using App;\n\nConsole.WriteLine(Greeter.Greet(args.Length > 0 ? args[0] : "world"));\n',
            "Tests/Tests.csproj": '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup>\n    <TargetFramework>net8.0</TargetFramework>\n    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n    <IsPackable>false</IsPackable>\n  </PropertyGroup>\n  <ItemGroup>\n    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.9.0" />\n    <PackageReference Include="xunit" Version="2.7.0" />\n    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.7" />\n  </ItemGroup>\n  <ItemGroup>\n    <ProjectReference Include="..\\App\\App.csproj" />\n  </ItemGroup>\n</Project>\n',
            "Tests/GreeterTests.cs": 'using App;\nusing Xunit;\n\npublic class GreeterTests\n{\n    [Fact]\n    public void Greets() => Assert.Equal("Hello, Ada!", Greeter.Greet(" Ada "));\n\n    [Fact]\n    public void NeedsAName() => Assert.Throws<ArgumentException>(() => Greeter.Greet("  "));\n}\n',
            "README.md": f"# {project}\n\n.NET 8 console app with an xUnit test project (install the .NET 8 SDK).\n\n```bash\ndotnet test\ndotnet run --project App -- Ada\n```\n",
        }
    if lang in ("c", "cpp"):
        cx = lang == "cpp"
        ext = "cpp" if cx else "c"
        hdr = "hpp" if cx else "h"
        return {
            "CMakeLists.txt": f'cmake_minimum_required(VERSION 3.16)\nproject({k} {"CXX" if cx else "C"})\n{"set(CMAKE_CXX_STANDARD 17)" if cx else "set(CMAKE_C_STANDARD 11)"}\nenable_testing()\n\n'
                              f'add_library(mathutil src/mathutil.{ext})\ntarget_include_directories(mathutil PUBLIC src)\n\nadd_executable({k} src/main.{ext})\ntarget_link_libraries({k} mathutil)\n\n'
                              f'add_executable(test_mathutil tests/test_mathutil.{ext})\ntarget_link_libraries(test_mathutil mathutil)\nadd_test(NAME mathutil COMMAND test_mathutil)\n',
            f"src/mathutil.{hdr}": ("#pragma once\nint clamp_int(int value, int low, int high);\n" if cx else "#ifndef MATHUTIL_H\n#define MATHUTIL_H\nint clamp_int(int value, int low, int high);\n#endif\n"),
            f"src/mathutil.{ext}": f'#include "mathutil.{hdr}"\n\nint clamp_int(int value, int low, int high) {{\n    if (value < low) return low;\n    if (value > high) return high;\n    return value;\n}}\n',
            f"src/main.{ext}": (f'#include <iostream>\n#include "mathutil.hpp"\n\nint main() {{\n    std::cout << "clamp(15, 0, 10) = " << clamp_int(15, 0, 10) << std::endl;\n    return 0;\n}}\n' if cx
                                else '#include <stdio.h>\n#include "mathutil.h"\n\nint main(void) {\n    printf("clamp(15, 0, 10) = %d\\n", clamp_int(15, 0, 10));\n    return 0;\n}\n'),
            f"tests/test_mathutil.{ext}": (f'#include <cassert>\n#include "mathutil.{hdr}"\n\nint main() {{\n    assert(clamp_int(15, 0, 10) == 10);\n    assert(clamp_int(-3, 0, 10) == 0);\n    assert(clamp_int(5, 0, 10) == 5);\n    return 0;\n}}\n' if cx
                                           else f'#include <assert.h>\n#include "mathutil.{hdr}"\n\nint main(void) {{\n    assert(clamp_int(15, 0, 10) == 10);\n    assert(clamp_int(-3, 0, 10) == 0);\n    assert(clamp_int(5, 0, 10) == 5);\n    return 0;\n}}\n'),
            "README.md": f"# {project}\n\n{'C++17' if cx else 'C'} with CMake (install CMake and a compiler: Visual Studio Build Tools, or MSYS2 gcc).\n\n```bash\ncmake -S . -B build\ncmake --build build\nctest --test-dir build --output-on-failure\n```\n",
        }
    if lang == "dart":
        return {
            "pubspec.yaml": f"name: {s}\ndescription: A small Dart command line app.\nversion: 0.1.0\n\nenvironment:\n  sdk: ^3.3.0\n\ndev_dependencies:\n  lints: ^4.0.0\n  test: ^1.25.0\n",
            "analysis_options.yaml": "include: package:lints/recommended.yaml\n",
            "lib/greeter.dart": "String greet(String name) {\n  final clean = name.trim();\n  if (clean.isEmpty) throw ArgumentError('name is required');\n  return 'Hello, $clean!';\n}\n",
            "bin/main.dart": f"import 'package:{s}/greeter.dart';\n\nvoid main(List<String> args) {{\n  print(greet(args.isNotEmpty ? args.first : 'world'));\n}}\n",
            "test/greeter_test.dart": f"import 'package:{s}/greeter.dart';\nimport 'package:test/test.dart';\n\nvoid main() {{\n  test('greets', () => expect(greet(' Ada '), 'Hello, Ada!'));\n  test('needs a name', () => expect(() => greet('  '), throwsArgumentError));\n}}\n",
            "README.md": f"# {project}\n\nDart command line app (install the Dart SDK).\n\n```bash\ndart pub get\ndart test\ndart run\n```\n",
        }
    if lang == "flutter":
        return {
            "pubspec.yaml": f"name: {s}\ndescription: A Flutter app.\npublish_to: none\nversion: 0.1.0+1\n\nenvironment:\n  sdk: ^3.3.0\n\ndependencies:\n  flutter:\n    sdk: flutter\n\ndev_dependencies:\n  flutter_test:\n    sdk: flutter\n  flutter_lints: ^4.0.0\n\nflutter:\n  uses-material-design: true\n",
            "analysis_options.yaml": "include: package:flutter_lints/flutter.yaml\n",
            "lib/main.dart": ("import 'package:flutter/material.dart';\n\nvoid main() => runApp(const MyApp());\n\nclass MyApp extends StatelessWidget {\n  const MyApp({super.key});\n\n  @override\n  Widget build(BuildContext context) {\n    return MaterialApp(\n      title: '" + project + "',\n      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),\n      home: const CounterPage(),\n    );\n  }\n}\n\n"
                             "class CounterPage extends StatefulWidget {\n  const CounterPage({super.key});\n\n  @override\n  State<CounterPage> createState() => _CounterPageState();\n}\n\nclass _CounterPageState extends State<CounterPage> {\n  int _count = 0;\n\n  @override\n  Widget build(BuildContext context) {\n    return Scaffold(\n      appBar: AppBar(title: const Text('" + project + "')),\n"
                             "      body: Center(child: Text('Taps: $_count', style: Theme.of(context).textTheme.headlineMedium)),\n      floatingActionButton: FloatingActionButton(\n        onPressed: () => setState(() => _count++),\n        tooltip: 'Add one',\n        child: const Icon(Icons.add),\n      ),\n    );\n  }\n}\n"),
            "test/widget_test.dart": f"import 'package:flutter/material.dart';\nimport 'package:flutter_test/flutter_test.dart';\nimport 'package:{s}/main.dart';\n\nvoid main() {{\n  testWidgets('counter increments', (tester) async {{\n    await tester.pumpWidget(const MyApp());\n    expect(find.text('Taps: 0'), findsOneWidget);\n    await tester.tap(find.byIcon(Icons.add));\n    await tester.pump();\n    expect(find.text('Taps: 1'), findsOneWidget);\n  }});\n}}\n",
            "README.md": f"# {project}\n\nFlutter app. After installing Flutter run `flutter create --project-name {s} .` once to add the android, ios and web folders, then:\n\n```bash\nflutter pub get\nflutter test\nflutter run\nflutter build apk --debug\n```\n",
        }
    if lang == "go":
        return {
            "go.mod": f"module example.com/{k}\n\ngo 1.22\n",
            "greeter.go": 'package main\n\nimport (\n\t"errors"\n\t"strings"\n)\n\nfunc Greet(name string) (string, error) {\n\tname = strings.TrimSpace(name)\n\tif name == "" {\n\t\treturn "", errors.New("name is required")\n\t}\n\treturn "Hello, " + name + "!", nil\n}\n',
            "main.go": 'package main\n\nimport (\n\t"fmt"\n\t"os"\n)\n\nfunc main() {\n\tname := "world"\n\tif len(os.Args) > 1 {\n\t\tname = os.Args[1]\n\t}\n\tmsg, err := Greet(name)\n\tif err != nil {\n\t\tfmt.Fprintln(os.Stderr, err)\n\t\tos.Exit(1)\n\t}\n\tfmt.Println(msg)\n}\n',
            "greeter_test.go": 'package main\n\nimport "testing"\n\nfunc TestGreet(t *testing.T) {\n\tgot, err := Greet(" Ada ")\n\tif err != nil || got != "Hello, Ada!" {\n\t\tt.Fatalf("got %q, %v", got, err)\n\t}\n\tif _, err := Greet("  "); err == nil {\n\t\tt.Fatal("expected an error for an empty name")\n\t}\n}\n',
            "README.md": f"# {project}\n\nGo (install Go).\n\n```bash\ngo test ./...\ngo run . Ada\n```\n",
        }
    if lang == "rust":
        return {
            "Cargo.toml": f'[package]\nname = "{k}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n',
            "src/lib.rs": 'pub fn greet(name: &str) -> Result<String, String> {\n    let name = name.trim();\n    if name.is_empty() {\n        return Err("name is required".to_string());\n    }\n    Ok(format!("Hello, {name}!"))\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn greets() {\n        assert_eq!(greet(" Ada ").unwrap(), "Hello, Ada!");\n    }\n\n    #[test]\n    fn needs_a_name() {\n        assert!(greet("  ").is_err());\n    }\n}\n',
            "src/main.rs": f'fn main() {{\n    let name = std::env::args().nth(1).unwrap_or_else(|| "world".to_string());\n    match {s}::greet(&name) {{\n        Ok(msg) => println!("{{msg}}"),\n        Err(e) => {{\n            eprintln!("{{e}}");\n            std::process::exit(1);\n        }}\n    }}\n}}\n',
            "README.md": f"# {project}\n\nRust (install rustup).\n\n```bash\ncargo test\ncargo run -- Ada\n```\n",
        }
    if lang == "powershell":
        return {
            f"{P}.psm1": 'function Get-Greeting {\n    [CmdletBinding()]\n    param([Parameter(Mandatory)][string]$Name)\n    $clean = $Name.Trim()\n    if (-not $clean) { throw "name is required" }\n    "Hello, $clean!"\n}\n\nExport-ModuleMember -Function Get-Greeting\n',
            f"{P}.Tests.ps1": f"BeforeAll {{ Import-Module \"$PSScriptRoot/{P}.psm1\" -Force }}\n\nDescribe 'Get-Greeting' {{\n    It 'greets' {{ Get-Greeting -Name ' Ada ' | Should -Be 'Hello, Ada!' }}\n    It 'needs a name' {{ {{ Get-Greeting -Name '  ' }} | Should -Throw }}\n}}\n",
            "README.md": f"# {project}\n\nA PowerShell module with a Pester test.\n\n```powershell\nInstall-Module Pester -Scope CurrentUser   # once\nInvoke-Pester\nImport-Module ./{P}.psm1; Get-Greeting -Name Ada\n```\n",
        }
    raise Refused(f"Unknown language '{lang}'. Choose one of: {', '.join(LANGS)}.")


def new(project: str, lang: str, official: bool = False) -> str:
    if lang not in LANGS:
        raise Refused(f"Unknown language '{lang}'. Choose one of: {', '.join(LANGS)}.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{1,59}", project or ""):
        raise Refused("Give the project a name of 2-60 letters, digits, spaces, dots, dashes or underscores.")
    config.WORKSPACES.mkdir(exist_ok=True)
    ws = workspace(names(project)["kebab"], must_exist=False)
    if ws.exists():
        raise Refused(f"A workspace called '{ws.name}' already exists. Pick another name.")
    ws.mkdir()
    notes = []
    try:
        if official:
            notes.append(official_generate(ws, lang, project))
        for rel, content in files_for(lang, project).items():
            p = ws / rel
            if official and p.exists():
                continue                                   # the official generator's own file wins
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8", newline="\n")
        gi = ws / ".gitignore"
        if not gi.exists():
            gi.write_text(GITIGNORE.get(lang, "") + ".env\n.env.*\n", encoding="utf-8", newline="\n")
        if shutil.which("git"):
            gitops.init(ws, f"Start {project} ({lang})")
            notes.append("A git repository was started with a first commit.")
    except Exception:
        shutil.rmtree(ws, ignore_errors=True)
        raise
    count = sum(1 for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts)
    test_cmd = {"node": "npm test", "typescript": "npm install, then npm test", "python-cli": "python -m unittest discover -s tests -v", "python-api": "pip install -r requirements.txt, then pytest",
                "java": "mvn test", "kotlin": "gradle test", "csharp": "dotnet test", "c": "cmake, build, ctest", "cpp": "cmake, build, ctest", "dart": "dart test", "flutter": "flutter test",
                "go": "go test ./...", "rust": "cargo test", "powershell": "Invoke-Pester"}[lang]
    return "\n".join([f"Created workspace '{ws.name}' ({LANGS[lang]}): {count} files in {ws}", *[n for n in notes if n],
                      f"Next: run its tests ({test_cmd}) with: dev run {ws.name} test   (or install first: dev run {ws.name} install)"])


def official_generate(ws: Path, lang: str, project: str) -> str:
    n = names(project)
    cmd = {"flutter": ["flutter", "create", "--project-name", n["snake"], "."], "dart": ["dart", "create", "-t", "console", "--force", "."],
           "csharp": ["dotnet", "new", "console", "-n", "App", "-o", "App", "--no-restore"], "rust": ["cargo", "init", "--name", n["kebab"], "."],
           "go": ["go", "mod", "init", f"example.com/{n['kebab']}"], "node": ["npm", "init", "-y"]}.get(lang)
    if not cmd:
        return f"No official generator is used for {lang}; the built-in template was used."
    code, out = run(cmd, ws)
    if code == 127:
        return f"{cmd[0]} is not installed, so the built-in template was used instead. ({out.strip()})"
    if code != 0:
        raise Refused(f"The official generator failed:\n{out.strip()[-400:]}")
    return f"Ran the official generator: {' '.join(cmd)}."

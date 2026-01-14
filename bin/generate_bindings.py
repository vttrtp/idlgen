#!/usr/bin/env python3
"""
Generic IDL Code Generator

Parses C++-like IDL definitions and generates:
  1. C API exports (header + implementation) - per IDL file
  2. C++ client wrapper for dynamic loading - per IDL file
  3. Emscripten WASM bindings - combined
  4. JNI bindings for Java interop (optional) - combined

Usage:
    python generate_bindings.py input.idl --output-dir generated/
    python generate_bindings.py common_types.idl main.idl --output-dir generated/
    python generate_bindings.py input.idl --output-dir generated/ --java --java-package com.example
"""

import argparse
import sys
import time
from pathlib import Path

# Add parent directory to path so idlgen package can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from idlgen import (
    IDLParser,
    CAPIGenerator,
    ClientGenerator,
    WASMGenerator,
    JNIGenerator,
    PythonGenerator,
    CommonGenerator,
    ParsedIDL,
    IDLModule,
)


def main():
    start_time = time.perf_counter()

    parser = argparse.ArgumentParser(description="Generate bindings from IDL")
    parser.add_argument("idl_files", nargs="*", help="Path to IDL file(s)")
    parser.add_argument("--output-dir", "-o", default="generated", help="Output directory")
    parser.add_argument("--namespace", "-n", default="", help="C++ namespace (used for combined files)")
    parser.add_argument("--header", default="", help="Implementation header to include (alternative)")
    parser.add_argument("--impl-header", default="", help="Implementation header to include")
    parser.add_argument("--api-macro", default="", help="API export macro name")
    parser.add_argument("--java", action="store_true", help="Generate Java/JNI bindings")
    parser.add_argument("--java-package", default="", help="Java package name")
    parser.add_argument("--java-output-dir", default="", help="Java source output directory")
    parser.add_argument("--java-output", default="", help="Java source output directory (alternative)")
    parser.add_argument("--python", action="store_true", help="Generate Python bindings")
    parser.add_argument("--python-output", default="", help="Python bindings output directory")
    args = parser.parse_args()

    if not args.idl_files:
        parser.error("At least one IDL file is required")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse all IDL files and build module
    module = IDLModule()
    parsed_files: list[tuple[Path, ParsedIDL]] = []

    for idl_file in args.idl_files:
        idl_path = Path(idl_file)
        parsed = IDLParser(idl_path.read_text()).parse()
        parsed.source_file = idl_path.stem  # Store filename without extension
        module.add_file(parsed)
        parsed_files.append((idl_path, parsed))

    # Determine namespace from first IDL file (for combined files)
    first_idl_path = parsed_files[0][0]
    namespace = args.namespace or first_idl_path.stem.replace("-", "_")
    impl_header = args.impl_header or args.header or f"{namespace}.hpp"
    impl_header = Path(impl_header).name
    api_macro = args.api_macro or f"{namespace.upper()}_API"

    files = {}

    # Generate common header files
    common = CommonGenerator(namespace, api_macro)
    export_header = f"{namespace}_export.h"
    common_client_header = "idl_client.hpp"
    files[export_header] = common.generate_export_header()
    files[common_client_header] = common.generate_client_header()

    # Generate per-file C API and client headers/implementations
    for idl_path, parsed in parsed_files:
        file_ns = parsed.source_file.replace("-", "_")

        # Find dependency headers for this file
        deps = module.get_dependencies(parsed)
        dep_c_headers = [f"{d.source_file.replace('-', '_')}_c_api.h" for d in deps]
        dep_client_headers = [f"{d.source_file.replace('-', '_')}_client.hpp" for d in deps]

        # C API generator - per file
        c_api = CAPIGenerator(
            idl=parsed,
            namespace=file_ns,
            api_macro=api_macro,
            module=module,
            dep_headers=dep_c_headers
        )

        # Only generate if there's content
        if parsed.enums or parsed.structs or parsed.callbacks or parsed.classes:
            files[f"{file_ns}_c_api.h"] = c_api.generate_header()
            files[f"{file_ns}_c_api.cpp"] = c_api.generate_impl(impl_header)

        # Collect types from dependencies that this file uses
        dep_types = []
        for dep in deps:
            for struct in dep.structs:
                if struct.name in parsed.get_used_types():
                    dep_types.append(struct.name)
            for enum in dep.enums:
                if enum.name in parsed.get_used_types():
                    dep_types.append(enum.name)

        # Client generator - per file
        client = ClientGenerator(
            idl=parsed,
            namespace=file_ns,
            module=module,
            dep_headers=dep_client_headers,
            dep_types=dep_types,
            client_header=common_client_header
        )

        if parsed.enums or parsed.structs or parsed.callbacks or parsed.classes:
            files[f"{file_ns}_client.hpp"] = client.generate_header()
            files[f"{file_ns}_client.cpp"] = client.generate_impl()

    # WASM bindings - combined (needs all types and classes)
    merged_idl = module.get_merged_idl()
    wasm = WASMGenerator(merged_idl, namespace, module=module)
    files[f"{namespace}_wasm_bindings.cpp"] = wasm.generate(impl_header)

    # Generate JNI bindings if requested - combined
    java_output_dir = args.java_output_dir or args.java_output
    generate_java = args.java or args.java_package or java_output_dir

    if generate_java:
        java_package = args.java_package or namespace.replace("_", ".")
        jni = JNIGenerator(merged_idl, namespace, java_package)

        files[f"{namespace}_jni.h"] = jni.generate_jni_header()
        files[f"{namespace}_jni.cpp"] = jni.generate_jni_impl(impl_header)

        # Generate Java classes
        java_output = Path(java_output_dir) if java_output_dir else output_dir / "java"
        java_pkg_dir = java_output / java_package.replace(".", "/")
        java_pkg_dir.mkdir(parents=True, exist_ok=True)

        # Generate shared types file (structs and callbacks)
        if merged_idl.structs or merged_idl.callbacks:
            types_path = java_pkg_dir / "Types.java"
            types_path.write_text(jni.generate_java_types())
            print(f"Generated: {types_path}")

        for cls in merged_idl.classes:
            java_path = java_pkg_dir / f"{cls.name}.java"
            java_path.write_text(jni.generate_java_class(cls))
            print(f"Generated: {java_path}")

    # Generate Python bindings if requested - combined
    generate_python = args.python or args.python_output
    if generate_python:
        python_gen = PythonGenerator(merged_idl, namespace)
        python_output = Path(args.python_output) if args.python_output else output_dir
        python_output.mkdir(parents=True, exist_ok=True)

        python_path = python_output / f"{namespace}.py"
        python_path.write_text(python_gen.generate())
        print(f"Generated: {python_path}")

    for filename, content in files.items():
        path = output_dir / filename
        path.write_text(content)
        print(f"Generated: {path}")

    elapsed = time.perf_counter() - start_time
    print(f"Generation completed in {elapsed*1000:.2f} ms")


if __name__ == "__main__":
    main()

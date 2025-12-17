# IDL Code Generator

A Python-based code generator that creates C API, WASM (Emscripten), and JNI bindings from IDL definitions.

## Requirements

- CMake 3.16+
- C++17 compatible compiler
- Python 3.8+
- Ninja build system
- vcpkg package manager (for C++ tests)
- Emscripten SDK (for WASM build)
- Java JDK (for JNI tests, optional)
- Node.js (for WASM tests)

## Installing Prerequisites

### vcpkg

```bash
# Clone vcpkg (should be at ../../vcpkg relative to this project)
cd ../..
git clone https://github.com/microsoft/vcpkg.git
cd vcpkg
./bootstrap-vcpkg.sh   # Linux/macOS
# or bootstrap-vcpkg.bat on Windows
```

### Emscripten SDK (for WASM build)

```bash
# Clone and install emsdk (should be at ../../emsdk relative to this project)
cd ../..
git clone https://github.com/emscripten-core/emsdk.git
cd emsdk
./emsdk install latest
./emsdk activate latest
source ./emsdk_env.sh   # Linux/macOS
```

## Installation

```bash
pip install -e .
```

## Usage

```bash
python bin/generate_bindings.py <idl_file> \
    --output-dir <output_dir> \
    --namespace <namespace> \
    --impl-header <header.hpp> \
    [--java] \
    [--java-package <package>] \
    [--java-output-dir <dir>]
```

## Supported Generators

- **C API** - C-compatible API with opaque handles
- **Client** - C++ client that loads library dynamically
- **WASM** - Emscripten bindings for WebAssembly
- **JNI** - Java Native Interface bindings

## IDL Syntax

```idl
namespace MyLib;

struct Point {
    int x;
    int y;
}

callback OnResult(Point result);

interface Calculator {
    int add(int a, int b);
    void processAsync(OnResult callback);
}
```

## Building and Testing

### Using CMake Presets

The project uses CMake presets for easy building.

**Available presets:**
| Preset | Description | Build Directory |
|--------|-------------|-----------------|
| `default` | Release build with vcpkg | `build/` |
| `debug` | Debug build with vcpkg | `build-debug/` |
| `wasm` | WASM build with Emscripten | `build-wasm/` |

**Native build:**
```bash
cmake --preset default
cmake --build --preset default
ctest --preset default
```

**WASM build:**
```bash
source ../../emsdk/emsdk_env.sh
cmake --preset wasm
cmake --build --preset wasm
node build-wasm/samples/samples_test.js
```

**Java tests:**
```bash
# After native build completes
cd samples/tests/java
mkdir -p out
javac -d out generated/idl/samples/*.java SamplesTest.java
java -Djava.library.path=../../../build/samples -cp out idl.samples.SamplesTest
```

## Directory Structure

```
idlgen/
├── CMakeLists.txt          # Root CMake configuration
├── CMakePresets.json       # CMake presets (default, debug, wasm)
├── vcpkg.json              # vcpkg dependencies
├── vcpkg-configuration.json # vcpkg baseline
├── pyproject.toml          # Python package configuration
├── README.md               # This file
├── bin/
│   └── generate_bindings.py  # CLI entry point
├── idlgen/                 # Python package
│   ├── __init__.py
│   ├── parser.py           # IDL parser
│   ├── type_mapper.py      # Type mapping utilities
│   ├── types.py            # Type definitions
│   ├── c_api_generator.py  # C API generator
│   ├── client_generator.py # C++ client generator
│   ├── wasm_generator.py   # WASM bindings generator
│   └── jni_generator.py    # JNI bindings generator
├── samples/
│   ├── CMakeLists.txt      # Samples build configuration
│   ├── samples.idl         # Sample IDL definitions
│   ├── samples.hpp         # Sample C++ implementation
│   ├── samples.cpp         # Sample C++ implementation
│   └── tests/
│       ├── cpp/
│       │   ├── samples_test.cpp
│       │   └── generated/  # (gitignored) Generated C++ sources
│       ├── java/
│       │   ├── SamplesTest.java
│       │   └── generated/  # (gitignored) Generated Java sources
│       └── wasm/
│           ├── samples_test.js
│           └── generated/  # (gitignored) Generated WASM sources
└── triplets/
    └── wasm32-emscripten.cmake  # WASM vcpkg triplet
```

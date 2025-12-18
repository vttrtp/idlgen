"""
IDL Code Generator Package

Parses C++-like IDL definitions and generates:
  1. C API exports (header + implementation)
  2. C++ client wrapper for dynamic loading
  3. Emscripten WASM bindings
  4. JNI bindings for Java interop
  5. Python bindings using ctypes
"""

from .types import Param, Member, Method, Class, Struct, Enum, EnumValue, ParsedIDL
from .parser import IDLParser
from .type_mapper import TypeMapper
from .c_api_generator import CAPIGenerator
from .client_generator import ClientGenerator
from .wasm_generator import WASMGenerator
from .jni_generator import JNIGenerator
from .python_generator import PythonGenerator

__all__ = [
    'Param', 'Member', 'Method', 'Class', 'Struct', 'ParsedIDL',
    'IDLParser', 'TypeMapper',
    'CAPIGenerator', 'ClientGenerator', 'WASMGenerator', 'JNIGenerator',
    'PythonGenerator',
]

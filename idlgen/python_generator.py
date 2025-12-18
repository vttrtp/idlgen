"""Python Generator - generates Python bindings using ctypes for shared library access"""

from typing import Optional
from pathlib import Path
from .types import ParsedIDL, Class, Method, Member, Param, Struct, Callback
from .type_mapper import TypeMapper


class PythonGenerator:
    """Generates Python bindings using ctypes"""

    def __init__(self, idl: ParsedIDL, namespace: str):
        self.idl = idl
        self.namespace = namespace

    def generate(self) -> str:
        """Generate complete Python module"""
        lines = [
            '"""',
            f"AUTO-GENERATED Python bindings for {self.namespace}",
            "DO NOT EDIT - Generated from IDL",
            '"""',
            "",
            "import ctypes",
            "import os",
            "import sys",
            "from ctypes import (",
            "    POINTER, Structure, CFUNCTYPE,",
            "    c_void_p, c_int, c_double, c_float, c_char_p,",
            "    c_int8, c_uint8, c_int16, c_uint16,",
            "    c_int32, c_uint32, c_int64, c_uint64,",
            ")",
            "from typing import Callable, List, Optional",
            "",
            "",
            "# ══════════════════════════════════════════════════════════════",
            "# Library Loading",
            "# ══════════════════════════════════════════════════════════════",
            "",
            "def _load_library():",
            '    """Load the native library"""',
            "    if sys.platform == 'win32':",
            f'        lib_name = "{self.namespace}.dll"',
            "    elif sys.platform == 'darwin':",
            f'        lib_name = "lib{self.namespace}.dylib"',
            "    else:",
            f'        lib_name = "libidl_{self.namespace}.so"',
            "",
            "    # Get the directory containing this file",
            "    this_dir = os.path.dirname(os.path.abspath(__file__))",
            "",
            "    # Search paths (relative to generated file location)",
            "    search_paths = [",
            "        this_dir,",
            "        os.path.join(this_dir, '..', '..', '..', '..', 'build', 'samples'),  # From tests/python/generated",
            "        os.path.join(this_dir, '..', 'build', 'samples'),",
            "        os.path.join(this_dir, '..', 'lib'),",
            "        os.getcwd(),",
            "        os.path.join(os.getcwd(), 'build', 'samples'),",
            "    ]",
            "",
            "    for path in search_paths:",
            "        lib_path = os.path.join(path, lib_name)",
            "        if os.path.exists(lib_path):",
            "            return ctypes.CDLL(lib_path)",
            "",
            "    # Try system library path",
            "    return ctypes.CDLL(lib_name)",
            "",
            "",
            "_lib = _load_library()",
            "",
        ]

        # Generate enum definitions
        lines.extend(self._generate_enums())

        # Generate struct definitions
        lines.extend(self._generate_structs())

        # Generate callback types
        lines.extend(self._generate_callbacks())

        # Generate result struct definitions for vector returns
        lines.extend(self._generate_result_structs())

        # Generate function declarations
        lines.extend(self._generate_function_decls())

        # Generate wrapper classes
        for cls in self.idl.classes:
            lines.extend(self._generate_class(cls))

        return "\n".join(lines)

    def _generate_enums(self) -> list[str]:
        """Generate Python enum classes for IDL enums"""
        if not self.idl.enums:
            return []
        
        lines = [
            "# ══════════════════════════════════════════════════════════════",
            "# Enum Definitions",
            "# ══════════════════════════════════════════════════════════════",
            "",
            "from enum import IntEnum",
            "",
        ]
        
        for enum in self.idl.enums:
            lines.append(f"class {enum.name}(IntEnum):")
            lines.append(f'    """Enum {enum.name}"""')
            for val in enum.values:
                lines.append(f"    {val.name} = {val.value}")
            lines.append("")
        
        lines.append("")
        return lines

    def _generate_structs(self) -> list[str]:
        """Generate ctypes Structure classes for IDL structs"""
        lines = [
            "# ══════════════════════════════════════════════════════════════",
            "# Struct Definitions",
            "# ══════════════════════════════════════════════════════════════",
            "",
        ]

        for struct in self.idl.structs:
            lines.append(f"class {struct.name}(Structure):")
            lines.append(f'    """IDL struct: {struct.name}"""')
            lines.append("    _fields_ = [")
            for m in struct.members:
                ctype = self._to_ctypes(m.type)
                lines.append(f'        ("{m.name}", {ctype}),')
            lines.append("    ]")
            lines.append("")
            # Add __repr__ for debugging
            lines.append("    def __repr__(self):")
            field_strs = ", ".join(f"{m.name}={{self.{m.name}}}" for m in struct.members)
            lines.append(f'        return f"{struct.name}({field_strs})"')
            lines.append("")

        return lines

    def _generate_callbacks(self) -> list[str]:
        """Generate CFUNCTYPE definitions for callbacks"""
        if not self.idl.callbacks:
            return []

        lines = [
            "# ══════════════════════════════════════════════════════════════",
            "# Callback Types",
            "# ══════════════════════════════════════════════════════════════",
            "",
        ]

        for cb in self.idl.callbacks:
            ret_type = self._to_ctypes(cb.return_type)
            param_types = ", ".join(self._to_ctypes(p.type) for p in cb.params)
            if param_types:
                lines.append(f"{cb.name} = CFUNCTYPE({ret_type}, {param_types})")
            else:
                lines.append(f"{cb.name} = CFUNCTYPE({ret_type})")
            lines.append("")

        return lines

    def _generate_result_structs(self) -> list[str]:
        """Generate result struct classes for vector returns"""
        lines = []
        result_types = set()

        for cls in self.idl.classes:
            for method in cls.methods:
                if TypeMapper.is_vector(method.return_type):
                    inner = TypeMapper.vector_inner(method.return_type)
                    result_types.add((cls.name, inner))

        if result_types:
            lines.extend([
                "# ══════════════════════════════════════════════════════════════",
                "# Result Structs for Vector Returns",
                "# ══════════════════════════════════════════════════════════════",
                "",
            ])

            for iface_name, inner in sorted(result_types):
                result_name = f"{iface_name}_{inner}_CResult"
                lines.append(f"class {result_name}(Structure):")
                lines.append(f'    """Result container for vector<{inner}>"""')
                lines.append("    pass  # Opaque structure")
                lines.append("")

        return lines

    def _generate_function_decls(self) -> list[str]:
        """Generate ctypes function declarations"""
        lines = [
            "# ══════════════════════════════════════════════════════════════",
            "# C API Function Declarations",
            "# ══════════════════════════════════════════════════════════════",
            "",
        ]

        for cls in self.idl.classes:
            prefix = cls.name
            handle = f"{cls.name}Handle"

            # Create/destroy
            has_ctor = any(m.is_constructor for m in cls.methods)
            if has_ctor:
                ctor = next(m for m in cls.methods if m.is_constructor)
                ctor_params = [self._to_ctypes(p.type) for p in ctor.params]
                
                lines.append(f"_lib.{prefix}_create.restype = c_void_p")
                if ctor_params:
                    lines.append(f"_lib.{prefix}_create.argtypes = [{', '.join(ctor_params)}]")
                else:
                    lines.append(f"_lib.{prefix}_create.argtypes = []")
                lines.append("")

                lines.append(f"_lib.{prefix}_destroy.restype = None")
                lines.append(f"_lib.{prefix}_destroy.argtypes = [c_void_p]")
                lines.append("")

            # Methods
            for method in cls.methods:
                if method.is_constructor:
                    continue

                func_name = f"{prefix}_{method.name}"
                ret_type = self._c_return_type(cls.name, method.return_type)
                
                param_types = ["c_void_p"]  # handle
                for p in method.params:
                    if self._is_callback_type(p.type):
                        param_types.append(p.type)  # Callback type name
                    elif self._is_struct_type(p.type):
                        # Structs are passed by value in C API
                        param_types.append(p.type)
                    else:
                        param_types.append(self._to_ctypes(p.type))

                lines.append(f"_lib.{func_name}.restype = {ret_type}")
                lines.append(f"_lib.{func_name}.argtypes = [{', '.join(param_types)}]")
                lines.append("")

            # Result accessors for vector returns
            for method in cls.methods:
                if TypeMapper.is_vector(method.return_type):
                    inner = TypeMapper.vector_inner(method.return_type)
                    result_name = f"{cls.name}_{inner}_CResult"
                    inner_ctype = self._to_ctypes(inner)
                    
                    lines.append(f"_lib.{result_name}_getCount.restype = c_int")
                    lines.append(f"_lib.{result_name}_getCount.argtypes = [c_void_p]")
                    lines.append("")
                    lines.append(f"_lib.{result_name}_getData.restype = POINTER({inner_ctype})")
                    lines.append(f"_lib.{result_name}_getData.argtypes = [c_void_p]")
                    lines.append("")
                    lines.append(f"_lib.{result_name}_free.restype = None")
                    lines.append(f"_lib.{result_name}_free.argtypes = [c_void_p]")
                    lines.append("")

            # Attribute getters
            for member in cls.members:
                func_name = f"{prefix}_get{member.name[0].upper()}{member.name[1:]}"
                ret_type = self._to_ctypes(member.type)
                lines.append(f"_lib.{func_name}.restype = {ret_type}")
                lines.append(f"_lib.{func_name}.argtypes = [c_void_p]")
                lines.append("")

        return lines

    def _generate_class(self, cls: Class) -> list[str]:
        """Generate Python wrapper class for a class"""
        lines = [
            "# ══════════════════════════════════════════════════════════════",
            f"# {cls.name} Class",
            "# ══════════════════════════════════════════════════════════════",
            "",
            f"class {cls.name}:",
            f'    """Python wrapper for {cls.name} class"""',
            "",
        ]

        # Constructor
        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            params = ", ".join(f"{p.name}: {self._to_python_type(p.type)}" for p in ctor.params)
            if params:
                lines.append(f"    def __init__(self, {params}):")
            else:
                lines.append("    def __init__(self):")
            
            args = ", ".join(self._python_to_c_arg(p) for p in ctor.params)
            if args:
                lines.append(f"        self._handle = _lib.{cls.name}_create({args})")
            else:
                lines.append(f"        self._handle = _lib.{cls.name}_create()")
            lines.append("        if not self._handle:")
            lines.append(f'            raise RuntimeError("Failed to create {cls.name}")')
            lines.append("        # Store callback references to prevent GC")
            lines.append("        self._callbacks = []")
            lines.append("")

        # Destructor
        lines.extend([
            "    def __del__(self):",
            "        if hasattr(self, '_handle') and self._handle:",
            f"            _lib.{cls.name}_destroy(self._handle)",
            "            self._handle = None",
            "",
            "    def __enter__(self):",
            "        return self",
            "",
            "    def __exit__(self, exc_type, exc_val, exc_tb):",
            "        self.__del__()",
            "        return False",
            "",
        ])

        # Methods
        for method in cls.methods:
            if method.is_constructor:
                continue
            lines.extend(self._generate_method(cls, method))

        # Attribute getters
        for member in cls.members:
            lines.extend(self._generate_attribute(cls, member))

        return lines

    def _generate_method(self, cls: Class, method: Method) -> list[str]:
        """Generate method wrapper"""
        # Build parameter list with type hints
        params = []
        for p in method.params:
            if self._is_callback_type(p.type):
                cb = self._get_callback_def(p.type)
                if cb:
                    cb_params = ", ".join(self._to_python_type(cp.type) for cp in cb.params)
                    cb_ret = self._to_python_type(cb.return_type)
                    params.append(f"{p.name}: Callable[[{cb_params}], {cb_ret}]")
                else:
                    params.append(f"{p.name}: Callable")
            else:
                params.append(f"{p.name}: {self._to_python_type(p.type)}")

        params_str = ", ".join(params)
        ret_type = self._to_python_return_type(method.return_type)

        lines = [f"    def {method.name}(self, {params_str}) -> {ret_type}:"]
        lines.append(f'        """Call {cls.name}.{method.name}"""')

        # Build argument list
        args = ["self._handle"]
        for p in method.params:
            if self._is_callback_type(p.type):
                # Wrap callback in CFUNCTYPE
                lines.append(f"        _{p.name}_c = {p.type}({p.name})")
                lines.append(f"        self._callbacks.append(_{p.name}_c)  # Prevent GC")
                args.append(f"_{p.name}_c")
            elif self._is_struct_type(p.type):
                # Structs are passed by value in C API
                args.append(p.name)
            else:
                args.append(self._python_to_c_arg(p))

        args_str = ", ".join(args)

        if TypeMapper.is_vector(method.return_type):
            inner = TypeMapper.vector_inner(method.return_type)
            result_name = f"{cls.name}_{inner}_CResult"
            
            lines.append(f"        result_ptr = _lib.{cls.name}_{method.name}({args_str})")
            lines.append("        if not result_ptr:")
            lines.append("            return []")
            lines.append(f"        count = _lib.{result_name}_getCount(result_ptr)")
            lines.append(f"        data = _lib.{result_name}_getData(result_ptr)")
            lines.append("        items = [data[i] for i in range(count)]")
            lines.append(f"        _lib.{result_name}_free(result_ptr)")
            lines.append("        return items")
        elif self._is_struct_type(method.return_type):
            lines.append(f"        return _lib.{cls.name}_{method.name}({args_str})")
        else:
            lines.append(f"        return _lib.{cls.name}_{method.name}({args_str})")

        lines.append("")
        return lines

    def _generate_attribute(self, cls: Class, member: Member) -> list[str]:
        """Generate property for attribute"""
        getter_name = f"get{member.name[0].upper()}{member.name[1:]}"
        ret_type = self._to_python_type(member.type)

        return [
            "    @property",
            f"    def {member.name}(self) -> {ret_type}:",
            f'        """Get {member.name} attribute"""',
            f"        return _lib.{cls.name}_{getter_name}(self._handle)",
            "",
        ]

    def _to_ctypes(self, idl_type: str) -> str:
        """Convert IDL type to ctypes type"""
        mapping = {
            'void': 'None',
            'bool': 'c_int',
            'int': 'c_int',
            'int8_t': 'c_int8',
            'uint8_t': 'c_uint8',
            'int16_t': 'c_int16',
            'uint16_t': 'c_uint16',
            'int32_t': 'c_int32',
            'uint32_t': 'c_uint32',
            'int64_t': 'c_int64',
            'uint64_t': 'c_uint64',
            'float': 'c_float',
            'double': 'c_double',
            'char': 'c_char',
            'string': 'c_char_p',
        }
        
        # Check if it's a struct
        if any(s.name == idl_type for s in self.idl.structs):
            return idl_type
        
        return mapping.get(idl_type, 'c_void_p')

    def _to_python_type(self, idl_type: str) -> str:
        """Convert IDL type to Python type hint"""
        mapping = {
            'void': 'None',
            'bool': 'bool',
            'int': 'int',
            'int8_t': 'int',
            'uint8_t': 'int',
            'int16_t': 'int',
            'uint16_t': 'int',
            'int32_t': 'int',
            'uint32_t': 'int',
            'int64_t': 'int',
            'uint64_t': 'int',
            'float': 'float',
            'double': 'float',
            'char': 'str',
            'string': 'str',
        }
        
        # Check if it's a struct
        if any(s.name == idl_type for s in self.idl.structs):
            return idl_type
        
        return mapping.get(idl_type, 'object')

    def _to_python_return_type(self, idl_type: str) -> str:
        """Convert IDL return type to Python type hint"""
        if TypeMapper.is_vector(idl_type):
            inner = TypeMapper.vector_inner(idl_type)
            inner_py = self._to_python_type(inner)
            return f"List[{inner_py}]"
        return self._to_python_type(idl_type)

    def _c_return_type(self, iface_name: str, idl_type: str) -> str:
        """Get ctypes return type for C function"""
        if TypeMapper.is_vector(idl_type):
            return "c_void_p"  # Returns pointer to result struct
        return self._to_ctypes(idl_type)

    def _python_to_c_arg(self, param: Param) -> str:
        """Convert Python parameter to C argument"""
        if param.type == 'string':
            return f"{param.name}.encode('utf-8')"
        return param.name

    def _is_callback_type(self, type_name: str) -> bool:
        """Check if type is a callback"""
        return any(cb.name == type_name for cb in self.idl.callbacks)

    def _is_struct_type(self, type_name: str) -> bool:
        """Check if type is a struct"""
        return any(s.name == type_name for s in self.idl.structs)

    def _get_callback_def(self, type_name: str) -> Optional[Callback]:
        """Get callback definition by name"""
        return next((cb for cb in self.idl.callbacks if cb.name == type_name), None)

"""Client Generator - generates C++ wrapper for dynamic library loading"""

from .types import ParsedIDL, IDLModule, Class, Method, Member, Param, Callback
from .type_mapper import TypeMapper


class ClientGenerator:
    """Generates C++ client wrapper for dynamic loading"""

    def __init__(self, idl: ParsedIDL, namespace: str,
                 module: IDLModule | None = None, dep_headers: list[str] | None = None,
                 dep_types: list[str] | None = None, client_header: str = ""):
        self.idl = idl
        self.namespace = namespace
        self.module = module
        self.dep_headers = dep_headers or []
        # Types from dependencies that need using declarations
        self.dep_types = dep_types or []
        # Common client header (e.g., "face_detector_client.hpp")
        self.client_header = client_header

    def _lookup(self):
        """Get the object to use for type lookups (module or idl)"""
        return self.module if self.module else self.idl

    def generate_header(self) -> str:
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            "#pragma once",
            "",
            "#include <string>",
            "#include <vector>",
            "#include <memory>",
            "#include <functional>",
            f'#include "{self.namespace}_c_api.h"',
        ]

        # Include common client header if provided
        if self.client_header:
            lines.append(f'#include "{self.client_header}"')

        # Include dependency headers
        for dep_header in self.dep_headers:
            lines.append(f'#include "{dep_header}"')

        lines.extend([
            "",
            f"namespace {self.namespace}_client {{",
            "",
        ])

        # Only declare initialize/isInitialized if no common client header
        # (they're defined inline in the common header)
        if not self.client_header:
            lines.extend([
                "bool initialize(const std::string& libraryPath);",
                "bool isInitialized();",
                "",
            ])

        # Generate using declarations for types from dependencies
        for type_name in self.dep_types:
            lines.append(f"using {type_name} = ::{type_name};")
        if self.dep_types:
            lines.append("")

        # Generate using declarations for local enums
        for e in self.idl.enums:
            lines.append(f"using {e.name} = ::{e.name};")
        if self.idl.enums:
            lines.append("")

        # Generate using declarations for local structs
        for d in self.idl.structs:
            lines.append(f"using {d.name} = ::{d.name};")
        if self.idl.structs:
            lines.append("")

        # Generate std::function typedefs for callbacks
        lines.extend(self._generate_callback_typedefs())

        for cls in self.idl.classes:
            lines.extend(self._class_header(cls))

        lines.append(f"}} // namespace {self.namespace}_client")
        return "\n".join(lines)

    def _generate_callback_typedefs(self) -> list[str]:
        """Generate std::function typedefs for callback types"""
        lines = []
        for cb in self.idl.callbacks:
            params = ", ".join(TypeMapper.to_cpp(p.type) for p in cb.params)
            ret = TypeMapper.to_cpp(cb.return_type)
            lines.append(f"using {cb.name} = std::function<{ret}({params})>;")
        if self.idl.callbacks:
            lines.append("")
        return lines

    def generate_impl(self) -> str:
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            f'#include "{self.namespace}_client.hpp"',
            "",
            "#include <stdexcept>",
            "",
            f"namespace {self.namespace}_client {{",
            "",
            "namespace {",
            "",
        ]

        for cls in self.idl.classes:
            lines.extend(self._fn_pointer_types(cls))

        lines.append("")

        for cls in self.idl.classes:
            lines.extend(self._fn_pointer_vars(cls))

        lines.extend([
            "",
            "} // namespace",
            "",
        ])

        lines.extend(self._initialize_fn())

        for cls in self.idl.classes:
            lines.extend(self._class_impl(cls))

        lines.append(f"}} // namespace {self.namespace}_client")
        return "\n".join(lines)

    def _class_header(self, cls: Class) -> list[str]:
        h = f"{cls.name}Handle"
        lines = []

        # Result class - one per unique vector element type
        vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
        result_types = set()
        for m in vec_methods:
            inner = TypeMapper.vector_inner(m.return_type)
            result_types.add(inner)
        
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            c_result_name = f"::{result_name}"
            client_result = self._client_result_name(cls.name, inner)
            lines.extend([
                f"class {client_result} {{",
                "public:",
                f"    {client_result}();",
                f"    explicit {client_result}({c_result_name}* result);",
                f"    ~{client_result}() = default;",
                f"    {client_result}({client_result}&&) noexcept = default;",
                f"    {client_result}& operator=({client_result}&&) noexcept = default;",
                "",
                "    [[nodiscard]] int count() const;",
                f"    [[nodiscard]] const {inner}* data() const;",
                f"    [[nodiscard]] std::vector<{inner}> toVector() const;",
                "",
                "private:",
                f"    std::unique_ptr<{c_result_name}, std::function<void({c_result_name}*)>> result_;",
                "};",
                "",
            ])

        # Main class
        lines.append(f"class {cls.name} {{")
        lines.append("public:")

        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            cpp_params = ", ".join(self._param_to_cpp_decl(p) for p in ctor.params)
            lines.append(f"    explicit {cls.name}({cpp_params});")

        lines.extend([
            f"    ~{cls.name}() = default;",
            "",
            f"    {cls.name}(const {cls.name}&) = delete;",
            f"    {cls.name}& operator=(const {cls.name}&) = delete;",
            f"    {cls.name}({cls.name}&&) noexcept = default;",
            f"    {cls.name}& operator=({cls.name}&&) noexcept = default;",
            "",
        ])

        for member in cls.members:
            ret = TypeMapper.to_cpp(member.type)
            getter = self._getter_name(member)
            lines.append(f"    [[nodiscard]] {ret} {getter}() const noexcept;")

        for method in cls.methods:
            if method.is_constructor:
                continue
            ret = self._cpp_return_type(cls.name, method.return_type)
            params = ", ".join(self._param_to_cpp_decl(p) for p in method.params)
            const_q = " const" if method.is_const else ""
            lines.append(f"    [[nodiscard]] {ret} {method.name}({params}){const_q};")

        lines.extend([
            "",
            "private:",
            f"    std::unique_ptr<::{h}, std::function<void(::{h}*)>> handle_;",
            "};",
            "",
        ])

        return lines

    def _fn_pointer_types(self, cls: Class) -> list[str]:
        h = f"{cls.name}Handle"
        prefix = cls.name
        lines = []

        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            c_params = ", ".join(self._param_to_c_type(p) for p in ctor.params) or "void"
            lines.append(f"using {prefix}CreateFn = {h}*(*)({c_params});")
            lines.append(f"using {prefix}DestroyFn = void(*)({h}*);")

        for method in cls.methods:
            if method.is_constructor:
                continue
            ret = self._c_return_type_for_method(cls.name, method.return_type)
            params = [f"{h}*"] + [self._param_to_c_type(p) for p in method.params]
            fn_name = method.name[0].upper() + method.name[1:]
            lines.append(f"using {prefix}{fn_name}Fn = {ret}(*)({', '.join(params)});")

        # Function pointers for result accessors per unique element type
        vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
        result_types = set()
        for m in vec_methods:
            inner = TypeMapper.vector_inner(m.return_type)
            result_types.add(inner)
        
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            lines.append(f"using {result_name}GetCountFn = int(*)(const {result_name}*);")
            lines.append(f"using {result_name}GetDataFn = const {inner}*(*)(const {result_name}*);")
            lines.append(f"using {result_name}FreeFn = void(*)({result_name}*);")

        for member in cls.members:
            ret = "int" if member.type == "bool" else TypeMapper.to_c(member.type)
            getter = self._getter_name(member)
            fn_name = getter[0].upper() + getter[1:]
            lines.append(f"using {prefix}{fn_name}Fn = {ret}(*)({h}*);")

        return lines

    def _fn_pointer_vars(self, cls: Class) -> list[str]:
        prefix = cls.name
        lines = []

        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            lines.append(f"{prefix}CreateFn g_{prefix}_create = nullptr;")
            lines.append(f"{prefix}DestroyFn g_{prefix}_destroy = nullptr;")

        for method in cls.methods:
            if method.is_constructor:
                continue
            fn_name = method.name[0].upper() + method.name[1:]
            lines.append(f"{prefix}{fn_name}Fn g_{prefix}_{method.name} = nullptr;")

        # Variables for result accessors per unique element type
        vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
        result_types = set()
        for m in vec_methods:
            inner = TypeMapper.vector_inner(m.return_type)
            result_types.add(inner)
        
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            lines.append(f"{result_name}GetCountFn g_{result_name}_getCount = nullptr;")
            lines.append(f"{result_name}GetDataFn g_{result_name}_getData = nullptr;")
            lines.append(f"{result_name}FreeFn g_{result_name}_free = nullptr;")

        for member in cls.members:
            getter = self._getter_name(member)
            fn_name = getter[0].upper() + getter[1:]
            lines.append(f"{prefix}{fn_name}Fn g_{prefix}_{getter} = nullptr;")

        return lines

    def _initialize_fn(self) -> list[str]:
        # Use common client utilities when client_header is provided
        if self.client_header:
            lines = [
                "void loadSymbols() {",
            ]
        else:
            lines = [
                "void* g_library = nullptr;",
                "",
                "void* loadSymbol(const char* name) {",
                "#ifdef _WIN32",
                "    return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(g_library), name));",
                "#else",
                "    return dlsym(g_library, name);",
                "#endif",
                "}",
                "",
                "bool initialize(const std::string& libraryPath) {",
                "    if (g_library) return true;",
                "",
                "#ifdef _WIN32",
                "    g_library = LoadLibraryA(libraryPath.c_str());",
                "#else",
                "    g_library = dlopen(libraryPath.c_str(), RTLD_NOW);",
                "#endif",
                "    if (!g_library) return false;",
                "",
            ]

        for cls in self.idl.classes:
            prefix = cls.name
            load_sym = "idl_client::detail::loadSymbol" if self.client_header else "loadSymbol"

            ctor = next((m for m in cls.methods if m.is_constructor), None)
            if ctor:
                lines.append(f'    g_{prefix}_create = reinterpret_cast<{prefix}CreateFn>({load_sym}("{prefix}_create"));')
                lines.append(f'    g_{prefix}_destroy = reinterpret_cast<{prefix}DestroyFn>({load_sym}("{prefix}_destroy"));')

            for method in cls.methods:
                if method.is_constructor:
                    continue
                fn_name = method.name[0].upper() + method.name[1:]
                lines.append(f'    g_{prefix}_{method.name} = reinterpret_cast<{prefix}{fn_name}Fn>({load_sym}("{prefix}_{method.name}"));')

            # Load result accessors per unique element type
            vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
            result_types = set()
            for m in vec_methods:
                inner = TypeMapper.vector_inner(m.return_type)
                result_types.add(inner)

            for inner in sorted(result_types):
                result_name = self._result_struct_name(cls.name, inner)
                lines.append(f'    g_{result_name}_getCount = reinterpret_cast<{result_name}GetCountFn>({load_sym}("{result_name}_getCount"));')
                lines.append(f'    g_{result_name}_getData = reinterpret_cast<{result_name}GetDataFn>({load_sym}("{result_name}_getData"));')
                lines.append(f'    g_{result_name}_free = reinterpret_cast<{result_name}FreeFn>({load_sym}("{result_name}_free"));')

            for member in cls.members:
                getter = self._getter_name(member)
                fn_name = getter[0].upper() + getter[1:]
                lines.append(f'    g_{prefix}_{getter} = reinterpret_cast<{prefix}{fn_name}Fn>({load_sym}("{prefix}_{getter}"));')

        if self.client_header:
            lines.extend([
                "}",
                "",
                "bool g_symbolsLoaded = false;",
                "",
                "void ensureSymbolsLoaded() {",
                "    if (!g_symbolsLoaded && idl_client::isInitialized()) {",
                "        loadSymbols();",
                "        g_symbolsLoaded = true;",
                "    }",
                "}",
                "",
            ])
        else:
            lines.extend([
                "",
                "    return true;",
                "}",
                "",
                "bool isInitialized() { return g_library != nullptr; }",
                "",
            ])

        return lines

    def _class_impl(self, cls: Class) -> list[str]:
        prefix = cls.name
        h = f"{cls.name}Handle"
        lines = []

        # Result class impl - one per unique vector element type
        vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
        result_types = set()
        for m in vec_methods:
            inner = TypeMapper.vector_inner(m.return_type)
            result_types.add(inner)
        
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            c_result_name = f"::{result_name}"
            client_result = self._client_result_name(cls.name, inner)
            lines.extend([
                f"{client_result}::{client_result}() : result_(nullptr, nullptr) {{}}",
                "",
                f"{client_result}::{client_result}({c_result_name}* result)",
                f"    : result_(result, []({c_result_name}* r) {{ if (r && g_{result_name}_free) g_{result_name}_free(r); }}) {{}}",
                "",
                f"int {client_result}::count() const {{",
                f"    return result_ ? g_{result_name}_getCount(result_.get()) : 0;",
                "}",
                "",
                f"const {inner}* {client_result}::data() const {{",
                f"    return result_ ? g_{result_name}_getData(result_.get()) : nullptr;",
                "}",
                "",
                f"std::vector<{inner}> {client_result}::toVector() const {{",
                f"    std::vector<{inner}> vec;",
                "    int n = count();",
                "    auto* d = data();",
                "    if (n > 0 && d) vec.assign(d, d + n);",
                "    return vec;",
                "}",
                "",
            ])

        # Main class impl
        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            cpp_params = ", ".join(self._param_to_cpp_decl(p) for p in ctor.params)
            c_args = ", ".join(self._to_c_arg(p) for p in ctor.params)
            is_init = "idl_client::isInitialized" if self.client_header else "isInitialized"

            init_lines = [
                f"{cls.name}::{cls.name}({cpp_params})",
                "    : handle_(nullptr, nullptr) {",
                f'    if (!{is_init}()) throw std::runtime_error("Library not initialized");',
            ]
            if self.client_header:
                init_lines.append("    ensureSymbolsLoaded();")
            init_lines.extend([
                f"    auto* h = g_{prefix}_create({c_args});",
                f"    handle_ = std::unique_ptr<::{h}, std::function<void(::{h}*)>>(h,",
                f"        [](::{h}* p) {{ if (p && g_{prefix}_destroy) g_{prefix}_destroy(p); }});",
                "}",
                "",
            ])
            lines.extend(init_lines)

        for member in cls.members:
            ret = TypeMapper.to_cpp(member.type)
            getter = self._getter_name(member)
            default = "false" if member.type == "bool" else "0"
            lines.extend([
                f"{ret} {cls.name}::{getter}() const noexcept {{",
                f"    return handle_ && g_{prefix}_{getter} ? g_{prefix}_{getter}(handle_.get()) : {default};",
                "}",
                "",
            ])

        for method in cls.methods:
            if method.is_constructor:
                continue
            lines.extend(self._method_impl(cls, method, prefix))

        return lines

    def _method_impl(self, cls: Class, method: Method, prefix: str) -> list[str]:
        """Generate method implementation, handling callbacks specially"""
        ret = self._cpp_return_type(cls.name, method.return_type)
        params = ", ".join(self._param_to_cpp_decl(p) for p in method.params)
        const_q = " const" if method.is_const else ""
        
        lines = [f"{ret} {cls.name}::{method.name}({params}){const_q} {{"]
        lines.append(f"    if (!handle_) return {ret}();")
        
        # Check if we have callback parameters
        callback_params = [p for p in method.params if self._lookup().is_callback(p.type)]

        if callback_params:
            # Generate wrappers for each callback
            for p in callback_params:
                cb = self._lookup().find_callback(p.type)
                cb_params = ", ".join(f"{TypeMapper.to_c(cp.type)} {cp.name}" for cp in cb.params)
                cb_args = ", ".join(cp.name for cp in cb.params)
                ret_type = TypeMapper.to_c(cb.return_type)
                
                # Store callback in thread_local static, create wrapper
                lines.append(f"    static thread_local {p.type} s_{p.name};")
                lines.append(f"    s_{p.name} = {p.name};")
                lines.append(f"    auto callback_wrapper_{p.name} = []({cb_params}) -> {ret_type} {{")
                if cb.return_type == 'void':
                    lines.append(f"        s_{p.name}({cb_args});")
                else:
                    lines.append(f"        return s_{p.name}({cb_args});")
                lines.append("    };")
        
        c_args = ", ".join(self._to_c_arg(p) for p in method.params)
        if c_args:
            lines.append(f"    return {ret}(g_{prefix}_{method.name}(handle_.get(), {c_args}));")
        else:
            lines.append(f"    return {ret}(g_{prefix}_{method.name}(handle_.get()));")
        lines.append("}")
        lines.append("")
        return lines

    def _param_to_cpp_decl(self, param: Param) -> str:
        """Convert param to C++ declaration for method signature"""
        # Callbacks use std::function (already defined in namespace)
        if self._lookup().is_callback(param.type):
            return f'const {param.type}& {param.name}'

        base_type = TypeMapper.to_cpp(param.type)

        if param.is_const:
            base_type = f'const {base_type}'

        if param.is_pointer:
            return f'{base_type}* {param.name}'
        elif param.is_reference:
            return f'{base_type}& {param.name}'
        else:
            # For strings and complex types, use const ref
            if param.type == 'string':
                return f'const std::string& {param.name}'
            return f'{base_type} {param.name}'

    def _param_to_c_type(self, param: Param) -> str:
        """Convert param type to C type (without name)"""
        if param.type == 'string':
            return 'const char*'

        # Callbacks are function pointers
        if self._lookup().is_callback(param.type):
            return f'::{param.type}'

        base = TypeMapper.to_c(param.type)
        if param.is_const:
            base = f'const {base}'
        if param.is_pointer:
            return f'{base}*'
        return base

    def _to_c_arg(self, param: Param, method_name: str = "") -> str:
        if TypeMapper.is_string(param.type):
            return f"{param.name}.c_str()"
        # Callbacks need a wrapper - the wrapper is generated as a static lambda
        if self._lookup().is_callback(param.type):
            return f"callback_wrapper_{param.name}"
        return param.name

    def _getter_name(self, member: Member) -> str:
        prefix = "is" if member.type == "bool" else "get"
        return f"{prefix}{member.name[0].upper()}{member.name[1:]}"

    def _result_struct_name(self, iface_name: str, inner_type: str) -> str:
        """Generate the C API result struct name for interface + element type.
        Must match the C API generator's naming convention."""
        return f"{iface_name}_{inner_type}_CResult"

    def _client_result_name(self, iface_name: str, inner_type: str) -> str:
        """Generate the client wrapper result class name for interface + element type"""
        return f"{iface_name}{inner_type}Result"

    def _cpp_return_type(self, iface_name: str, idl_type: str) -> str:
        if TypeMapper.is_vector(idl_type):
            inner = TypeMapper.vector_inner(idl_type)
            return self._client_result_name(iface_name, inner)
        return TypeMapper.to_cpp(idl_type)

    def _c_return_type_for_method(self, iface_name: str, idl_type: str) -> str:
        """Get C return type using per-method result types for vectors"""
        if TypeMapper.is_vector(idl_type):
            inner = TypeMapper.vector_inner(idl_type)
            result_name = self._result_struct_name(iface_name, inner)
            return f"{result_name}*"
        return TypeMapper.to_c(idl_type)

    def _c_return_type(self, idl_type: str, result_type: str) -> str:
        if TypeMapper.is_vector(idl_type):
            return f"{result_type}*"
        return TypeMapper.to_c(idl_type)

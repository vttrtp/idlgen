"""C API Generator - generates C header and implementation for shared library export"""

from pathlib import Path
from .types import ParsedIDL, IDLModule, Class, Method, Member, Param
from .type_mapper import TypeMapper


class CAPIGenerator:
    """Generates C API header and implementation"""

    def __init__(self, idl: ParsedIDL, namespace: str, api_macro: str = "",
                 module: IDLModule | None = None, dep_headers: list[str] | None = None,
                 export_macro: str = ""):
        self.idl = idl
        self.namespace = namespace
        self.api_macro = api_macro or f"{namespace.upper()}_API"
        # Export macro should match api_macro for consistency across all files in a library
        self.export_macro = export_macro or self.api_macro.replace("_API", "_EXPORTS")
        # Module is used for type lookups across all files
        self.module = module
        # List of dependency header files to include
        self.dep_headers = dep_headers or []

    def _lookup(self):
        """Get the object to use for type lookups (module or idl)"""
        return self.module if self.module else self.idl

    def generate_header(self) -> str:
        lines = self._header_preamble()
        lines.extend(self._generate_enums())
        lines.extend(self._generate_structs())
        lines.extend(self._generate_callbacks())
        lines.extend(self._generate_class_decls())
        lines.extend(self._header_postamble())
        return "\n".join(lines)

    def generate_impl(self, impl_header: str) -> str:
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            f'#include "{Path(impl_header).name}"',
            f'#include "{self.namespace}_c_api.h"',
            "",
            "#include <memory>",
            "",
        ]
        for cls in self.idl.classes:
            lines.extend(self._generate_class_impl(cls))
        return "\n".join(lines)

    def _header_preamble(self) -> list[str]:
        guard = f"{self.namespace.upper()}_C_API_H"
        # Derive export header name from api_macro (e.g., FACE_DETECTOR_API -> face_detector_export.h)
        export_header = self.api_macro.lower().replace("_api", "_export.h")
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#include <stdint.h>",
            f'#include "{export_header}"',
        ]

        # Include dependency headers
        for dep_header in self.dep_headers:
            lines.append(f'#include "{dep_header}"')

        lines.extend([
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            "",
        ])
        return lines

    def _header_postamble(self) -> list[str]:
        return [
            "#ifdef __cplusplus",
            "}",
            "#endif",
            "",
            f"#endif // {self.namespace.upper()}_C_API_H",
        ]

    def _generate_enums(self) -> list[str]:
        """Generate enum type definitions"""
        lines = []
        for enum in self.idl.enums:
            lines.append(f"typedef enum {enum.name} {{")
            for i, val in enumerate(enum.values):
                comma = "," if i < len(enum.values) - 1 else ""
                if val.value is not None:
                    lines.append(f"    {enum.name}_{val.name} = {val.value}{comma}")
                else:
                    lines.append(f"    {enum.name}_{val.name}{comma}")
            lines.append(f"}} {enum.name};")
            lines.append("")
        return lines

    def _generate_structs(self) -> list[str]:
        lines = []
        for d in self.idl.structs:
            lines.append(f"typedef struct {d.name} {{")
            for m in d.members:
                lines.append(f"    {TypeMapper.to_c(m.type)} {m.name};")
            lines.append(f"}} {d.name};")
            lines.append("")
        return lines

    def _callback_param_to_c(self, param: Param) -> str:
        """Convert callback parameter to C type"""
        base = TypeMapper.to_c(param.type)
        # Struct references become const pointers in C callbacks
        if param.is_reference and self._lookup().is_struct(param.type):
            if param.is_const:
                return f"const {base}*"
            return f"{base}*"
        if param.is_const:
            base = f"const {base}"
        if param.is_pointer:
            return f"{base}*"
        return base

    def _generate_callbacks(self) -> list[str]:
        """Generate callback function pointer typedefs"""
        lines = []
        for cb in self.idl.callbacks:
            params = ", ".join(self._callback_param_to_c(p) for p in cb.params) or "void"
            ret = TypeMapper.to_c(cb.return_type)
            lines.append(f"typedef {ret} (*{cb.name})({params});")
        if self.idl.callbacks:
            lines.append("")
        return lines

    def _generate_class_decls(self) -> list[str]:
        lines = []
        for cls in self.idl.classes:
            handle = f"{cls.name}Handle"

            lines.append(f"typedef struct {handle} {handle};")
            
            # Create result struct typedef per unique vector return type
            vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
            result_types = set()
            for m in vec_methods:
                inner = TypeMapper.vector_inner(m.return_type)
                result_types.add(inner)
            
            for inner in sorted(result_types):
                result_name = self._result_struct_name(cls.name, inner)
                lines.append(f"typedef struct {result_name} {result_name};")
            
            lines.append("")

            for method in cls.methods:
                lines.extend(self._method_decl(cls, method))

            # Result accessors per unique vector element type
            for inner in sorted(result_types):
                result_name = self._result_struct_name(cls.name, inner)
                lines.append(f"{self.api_macro} int {result_name}_getCount(const {result_name}* result);")
                lines.append(f"{self.api_macro} const {inner}* {result_name}_getData(const {result_name}* result);")
                lines.append(f"{self.api_macro} void {result_name}_free({result_name}* result);")

            for member in cls.members:
                lines.append(self._attr_getter_decl(cls, member))

            lines.append("")
        return lines

    def _result_struct_name(self, class_name: str, inner_type: str) -> str:
        """Generate a unique result struct name for class + element type.
        Uses underscores and _C suffix to avoid collisions with client wrapper classes."""
        return f"{class_name}_{inner_type}_CResult"

    def _method_decl(self, cls: Class, method: Method) -> list[str]:
        h = f"{cls.name}Handle"
        prefix = cls.name
        lines = []

        if method.is_constructor:
            c_params = self._c_params_str(method.params)
            lines.append(f"{self.api_macro} {h}* {prefix}_create({c_params});")
            lines.append(f"{self.api_macro} void {prefix}_destroy({h}* handle);")
        else:
            ret = self._c_return_type_for_method(cls.name, method.return_type)
            params = [f"{h}* handle"] + [self._param_to_c(p) for p in method.params]
            lines.append(f"{self.api_macro} {ret} {prefix}_{method.name}({', '.join(params)});")

        return lines

    def _attr_getter_decl(self, cls: Class, member: Member) -> str:
        h = f"{cls.name}Handle"
        ret = "int" if member.type == "bool" else TypeMapper.to_c(member.type)
        getter = self._getter_name(member)
        return f"{self.api_macro} {ret} {cls.name}_{getter}({h}* handle);"

    def _generate_class_impl(self, cls: Class) -> list[str]:
        h = f"{cls.name}Handle"
        cpp_class = f"{self.namespace}::{cls.name}"
        lines = []

        # Check if any method returns string
        has_string_return = any(m.return_type == "string" for m in cls.methods if not m.is_constructor)

        # Handle struct
        lines.append(f"struct {h} {{")
        lines.append(f"    std::unique_ptr<{cpp_class}> impl;")
        if has_string_return:
            lines.append("    std::string last_string;")
        lines.append("};")
        lines.append("")

        # Result struct per unique vector element type
        vec_methods = [m for m in cls.methods if TypeMapper.is_vector(m.return_type)]
        result_types = set()
        for m in vec_methods:
            inner = TypeMapper.vector_inner(m.return_type)
            result_types.add(inner)
        
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            cpp_inner = TypeMapper.to_cpp(inner)
            lines.append(f"struct {result_name} {{")
            lines.append(f"    std::vector<{cpp_inner}> data;")
            lines.append("};")
            lines.append("")

        lines.append('extern "C" {')
        lines.append("")

        for method in cls.methods:
            lines.extend(self._method_impl(cls, method, cpp_class))

        # Result accessors per unique vector element type
        for inner in sorted(result_types):
            result_name = self._result_struct_name(cls.name, inner)
            lines.extend([
                f"int {result_name}_getCount(const {result_name}* result) {{",
                "    return result ? static_cast<int>(result->data.size()) : -1;",
                "}",
                "",
                f"const {inner}* {result_name}_getData(const {result_name}* result) {{",
                "    return (result && !result->data.empty()) ? result->data.data() : nullptr;",
                "}",
                "",
                f"void {result_name}_free({result_name}* result) {{",
                "    delete result;",
                "}",
                "",
            ])

        for member in cls.members:
            lines.extend(self._attr_getter_impl(cls, member))

        lines.append("} // extern \"C\"")
        lines.append("")
        return lines

    def _method_impl(self, cls: Class, method: Method, cpp_class: str) -> list[str]:
        h = f"{cls.name}Handle"
        prefix = cls.name
        lines = []

        if method.is_constructor:
            c_params = self._c_params_str(method.params)
            lines.append(f"{h}* {prefix}_create({c_params}) {{")

            for p in method.params:
                if TypeMapper.is_string(p.type):
                    lines.append(f"    if (!{p.name}) return nullptr;")

            lines.append("    try {")
            lines.append(f"        auto handle = new {h}();")
            cpp_args = ", ".join(p.name for p in method.params)
            lines.append(f"        handle->impl = std::make_unique<{cpp_class}>({cpp_args});")
            lines.append("        return handle;")
            lines.append("    } catch (...) { return nullptr; }")
            lines.append("}")
            lines.append("")

            lines.append(f"void {prefix}_destroy({h}* handle) {{")
            lines.append("    delete handle;")
            lines.append("}")
            lines.append("")
        else:
            ret = self._c_return_type_for_method(cls.name, method.return_type)
            params = [f"{h}* handle"] + [self._param_to_c(p) for p in method.params]

            lines.append(f"{ret} {prefix}_{method.name}({', '.join(params)}) {{")

            null_checks = ["!handle", "!handle->impl"]
            for p in method.params:
                if TypeMapper.is_string(p.type):
                    null_checks.append(f"!{p.name}")

            # Determine appropriate null/error return value
            if ret.endswith("*"):
                null_ret = "nullptr"
            elif ret == "int":
                null_ret = "-1"
            elif ret in ("bool", "double", "float"):
                null_ret = "0"
            elif TypeMapper.is_primitive(method.return_type):
                null_ret = "0"
            else:
                # Struct type - return empty struct
                null_ret = "{}"
            lines.append(f"    if ({' || '.join(null_checks)}) return {null_ret};")

            # Convert parameters for C++ call
            cpp_args = self._build_cpp_args(method.params)
            
            if TypeMapper.is_vector(method.return_type):
                inner = TypeMapper.vector_inner(method.return_type)
                result_name = self._result_struct_name(cls.name, inner)
                lines.append(f"    auto result = new {result_name}();")
                lines.append(f"    result->data = handle->impl->{method.name}({cpp_args});")
                lines.append("    return result;")
            elif method.return_type == "string":
                # Store string in handle to keep it alive
                lines.append(f"    handle->last_string = handle->impl->{method.name}({cpp_args});")
                lines.append("    return handle->last_string.c_str();")
            elif method.return_type.endswith('*'):
                # Pointer return - check if it's a class type
                base_type = method.return_type.rstrip('*').strip()
                if self._lookup().is_class(base_type):
                    # Wrap returned class pointer in a handle
                    handle_type = f"{base_type}Handle"
                    lines.append(f"    auto* obj = handle->impl->{method.name}({cpp_args});")
                    lines.append(f"    if (!obj) return nullptr;")
                    lines.append(f"    auto* result = new {handle_type}();")
                    lines.append(f"    result->impl = std::unique_ptr<{self.namespace}::{base_type}>(obj);")
                    lines.append("    return result;")
                else:
                    lines.append(f"    return handle->impl->{method.name}({cpp_args});")
            else:
                lines.append(f"    return handle->impl->{method.name}({cpp_args});")

            lines.append("}")
            lines.append("")

        return lines

    def _needs_callback_wrapper(self, cb) -> bool:
        """Check if callback needs a wrapper (has struct reference params)"""
        for p in cb.params:
            if self._lookup().is_struct(p.type) and p.is_reference:
                return True
        return False

    def _build_cpp_args(self, params: list[Param]) -> str:
        """Build C++ argument list, converting handles to impl pointers"""
        args = []
        for p in params:
            if self._lookup().is_callback(p.type):
                # Check if callback needs wrapper
                cb = self._lookup().find_callback(p.type)
                if cb and self._needs_callback_wrapper(cb):
                    # Generate inline lambda wrapper
                    wrapper = self._generate_callback_wrapper_inline(p.name, cb)
                    args.append(wrapper)
                else:
                    args.append(p.name)
            elif self._lookup().is_class(p.type):
                # Handle pointer -> impl pointer or reference
                if p.is_reference:
                    # Reference parameter - dereference impl pointer
                    args.append(f"*{p.name}->impl")
                elif p.is_pointer:
                    # Pointer parameter - get raw impl pointer
                    args.append(f"({p.name} && {p.name}->impl) ? {p.name}->impl.get() : nullptr")
                else:
                    # By value (unlikely for classes) - dereference
                    args.append(f"*{p.name}->impl")
            elif self._lookup().is_struct(p.type) and p.is_reference:
                # Struct reference - dereference pointer if needed
                args.append(f"*{p.name}" if p.is_pointer else p.name)
            else:
                args.append(p.name)
        return ", ".join(args)

    def _generate_callback_wrapper_inline(self, name: str, cb) -> str:
        """Generate an inline lambda wrapper for callbacks with struct references"""
        # Build parameter list for the C++ lambda
        cpp_params = []
        c_call_args = []
        for p in cb.params:
            if self._lookup().is_struct(p.type) and p.is_reference:
                if p.is_const:
                    cpp_params.append(f"const ::{p.type}& {p.name}")
                else:
                    cpp_params.append(f"::{p.type}& {p.name}")
                c_call_args.append(f"&{p.name}")
            else:
                cpp_params.append(f"{TypeMapper.to_cpp(p.type)} {p.name}")
                c_call_args.append(p.name)

        cpp_params_str = ", ".join(cpp_params)
        c_call_args_str = ", ".join(c_call_args)

        # Return type handling
        if cb.return_type == "bool":
            return f"[{name}]({cpp_params_str}) {{ return {name}({c_call_args_str}) != 0; }}"
        elif cb.return_type == "void":
            return f"[{name}]({cpp_params_str}) {{ {name}({c_call_args_str}); }}"
        else:
            return f"[{name}]({cpp_params_str}) {{ return {name}({c_call_args_str}); }}"

    def _attr_getter_impl(self, cls: Class, member: Member) -> list[str]:
        h = f"{cls.name}Handle"
        ret = "int" if member.type == "bool" else TypeMapper.to_c(member.type)
        getter = self._getter_name(member)
        cpp_getter = f"is{member.name[0].upper()}{member.name[1:]}" if member.type == "bool" else f"get{member.name[0].upper()}{member.name[1:]}"

        return [
            f"{ret} {cls.name}_{getter}({h}* handle) {{",
            f"    return (handle && handle->impl) ? handle->impl->{cpp_getter}() : 0;",
            "}",
            "",
        ]

    def _param_to_c(self, param: Param) -> str:
        """Convert param to C declaration"""
        if param.type == 'string':
            return f'const char* {param.name}'

        # Callback types are already function pointers
        if self._lookup().is_callback(param.type):
            return f'{param.type} {param.name}'

        # Class types use Handle pointers
        if self._lookup().is_class(param.type):
            handle = f"{param.type}Handle"
            if param.is_const:
                return f'const {handle}* {param.name}'
            return f'{handle}* {param.name}'

        base = TypeMapper.to_c(param.type)
        if param.is_const:
            base = f'const {base}'
        if param.is_pointer:
            return f'{base}* {param.name}'
        return f'{base} {param.name}'

    def _c_params_str(self, params: list[Param]) -> str:
        return ", ".join(self._param_to_c(p) for p in params) or "void"

    def _c_return_type_for_method(self, iface_name: str, idl_type: str) -> str:
        """Get C return type, using per-method result types for vectors"""
        if TypeMapper.is_vector(idl_type):
            inner = TypeMapper.vector_inner(idl_type)
            result_name = self._result_struct_name(iface_name, inner)
            return f"{result_name}*"
        if idl_type == "void":
            return "void"
        if idl_type == "bool":
            return "int"
        # Class pointer returns use Handle
        if idl_type.endswith('*'):
            base_type = idl_type.rstrip('*').strip()
            if self._lookup().is_class(base_type):
                return f"{base_type}Handle*"
        return TypeMapper.to_c(idl_type)

    def _c_return_type(self, idl_type: str, result_type: str) -> str:
        if TypeMapper.is_vector(idl_type):
            return f"{result_type}*"
        if idl_type == "void":
            return "void"
        if idl_type == "bool":
            return "int"
        return TypeMapper.to_c(idl_type)

    def _getter_name(self, member: Member) -> str:
        prefix = "is" if member.type == "bool" else "get"
        return f"{prefix}{member.name[0].upper()}{member.name[1:]}"

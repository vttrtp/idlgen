"""WASM Generator - generates Emscripten bindings for WebAssembly"""

from .types import ParsedIDL, Class, Method, Member, Param
from .type_mapper import TypeMapper


class WASMGenerator:
    """Generates Emscripten bindings"""

    def __init__(self, idl: ParsedIDL, namespace: str):
        self.idl = idl
        self.namespace = namespace

    def generate(self, impl_header: str) -> str:
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            "#include <emscripten/bind.h>",
            "#include <emscripten/val.h>",
            f'#include "{impl_header}"',
            "#include <vector>",
            "#include <memory>",
            "#include <string>",
            "#include <cstdint>",
            "",
            "using namespace emscripten;",
            "",
        ]

        for cls in self.idl.classes:
            lines.extend(self._class_wrapper(cls))
            lines.extend(self._class_bindings(cls))

        # Generate enum bindings
        if self.idl.enums:
            lines.extend(self._enum_bindings())

        # Generate struct bindings
        if self.idl.structs:
            lines.extend(self._struct_bindings())

        return "\n".join(lines)

    def _enum_bindings(self) -> list[str]:
        """Generate Emscripten bindings for enums"""
        lines = [
            f"EMSCRIPTEN_BINDINGS({self.namespace}_enums) {{",
        ]
        
        for enum in self.idl.enums:
            lines.append(f'    enum_<{enum.name}>("{enum.name}")')
            for val in enum.values:
                lines.append(f'        .value("{val.name}", {enum.name}_{val.name})')
            lines.append("    ;")
            lines.append("")
        
        lines.append("}")
        lines.append("")
        return lines

    def _struct_bindings(self) -> list[str]:
        """Generate Emscripten bindings for structs"""
        lines = [
            f"EMSCRIPTEN_BINDINGS({self.namespace}_structs) {{",
        ]
        
        for struct in self.idl.structs:
            lines.append(f'    value_object<{struct.name}>("{struct.name}")')
            for m in struct.members:
                lines.append(f'        .field("{m.name}", &{struct.name}::{m.name})')
            lines.append("    ;")
            lines.append("")
        
        lines.append("}")
        lines.append("")
        return lines

    def _class_wrapper(self, cls: Class) -> list[str]:
        cpp_class = f"{self.namespace}::{cls.name}"
        wasm_class = f"Wasm{cls.name}"
        lines = [
            f"class {wasm_class} {{",
            "public:",
            f"    {wasm_class}() = default;",
            "",
        ]

        # Constructor
        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            lines.extend(self._wasm_constructor(cls, ctor, cpp_class))

        # Attribute getters
        for member in cls.members:
            lines.extend(self._wasm_attribute(member))

        # Methods
        for method in cls.methods:
            if method.is_constructor:
                continue
            # Skip methods returning class pointers (not supported in Emscripten)
            if self._returns_class_pointer(method):
                continue
            lines.extend(self._wasm_method(cls, method))

        lines.extend([
            "private:",
            f"    std::unique_ptr<{cpp_class}> impl_;",
            "};",
            "",
        ])

        return lines

    def _returns_class_pointer(self, method: Method) -> bool:
        """Check if method returns a pointer to a class type"""
        if method.return_type.endswith('*'):
            base_type = method.return_type.rstrip('*').strip()
            return self._is_class_type(base_type)
        return False
    def _wasm_constructor(self, cls: Class, ctor: Method, cpp_class: str) -> list[str]:
        params = ", ".join(f"{self._wasm_param_type(p)} {p.name}" for p in ctor.params)
        args = ", ".join(p.name for p in ctor.params)
        
        lines = [
            f"    bool create({params}) {{",
            "        try {",
            f"            impl_ = std::make_unique<{cpp_class}>({args});",
            "            return impl_ != nullptr;",
            "        } catch (...) {",
            "            return false;",
            "        }",
            "    }",
            "",
        ]
        return lines

    def _wasm_attribute(self, member: Member) -> list[str]:
        ret = self._wasm_return_type(member.type)
        if member.type == "bool":
            getter = f"is{member.name[0].upper()}{member.name[1:]}"
            default = "false"
        else:
            getter = f"get{member.name[0].upper()}{member.name[1:]}"
            default = self._wasm_default(member.type)
        
        return [
            f"    {ret} {getter}() const {{",
            f"        return impl_ ? impl_->{getter}() : {default};",
            "    }",
            "",
        ]

    def _wasm_method(self, cls: Class, method: Method) -> list[str]:
        ret = self._wasm_return_type(method.return_type)
        params = ", ".join(f"{self._wasm_param_type(p)} {p.name}" for p in method.params)
        
        # Check if we have uint8_t* parameter that needs special handling
        has_uint8_ptr = any(p.type == "uint8_t" and p.is_pointer for p in method.params)
        
        # Check for callback parameters
        callback_params = [(p, self._get_callback_def(p.type)) for p in method.params if self._is_callback_type(p.type)]
        
        # Build argument conversion
        args = []
        for p in method.params:
            if p.type == "uint8_t" and p.is_pointer:
                args.append(f"{p.name}Vec.data()")
            elif self._is_callback_type(p.type):
                args.append(f"{p.name}Wrapper")
            elif self._is_struct_type(p.type) and p.is_pointer:
                # Struct pointer - pass address of local copy
                args.append(f"&{p.name}")
            elif self._is_class_type(p.type) and p.is_pointer:
                # Class pointer - pass address
                args.append(f"&{p.name}")
            else:
                # References and values pass directly
                args.append(p.name)
        args_str = ", ".join(args)

        lines = [f"    {ret} {method.name}({params}) {{"]
        
        # Add vector conversion for uint8_t* parameters (using efficient typed_memory_view)
        if has_uint8_ptr:
            for p in method.params:
                if p.type == "uint8_t" and p.is_pointer:
                    lines.append(f'        unsigned int {p.name}Len = {p.name}["length"].as<unsigned int>();')
                    lines.append(f"        std::vector<uint8_t> {p.name}Vec({p.name}Len);")
                    lines.append(f"        val {p.name}MemView = val(typed_memory_view({p.name}Len, {p.name}Vec.data()));")
                    lines.append(f'        {p.name}MemView.call<void>("set", {p.name});')
        
        # Add callback wrappers
        for param, cb_def in callback_params:
            if cb_def:
                cb_params = ", ".join(self._wasm_cb_param_type(cp) for cp in cb_def.params)
                cb_args = ", ".join(cp.name for cp in cb_def.params)
                cb_return = self._wasm_cb_return_type(cb_def.return_type)
                
                if cb_return == "void":
                    lines.append(f"        auto {param.name}Wrapper = [{param.name}]({cb_params}) {{")
                    lines.append(f'            {param.name}({cb_args});')
                    lines.append("        };")
                elif cb_return == "bool":
                    lines.append(f"        auto {param.name}Wrapper = [{param.name}]({cb_params}) -> bool {{")
                    lines.append(f'            return {param.name}({cb_args}).as<bool>();')
                    lines.append("        };")
                else:
                    lines.append(f"        auto {param.name}Wrapper = [{param.name}]({cb_params}) -> {cb_return} {{")
                    lines.append(f'            return {param.name}({cb_args}).as<{cb_return}>();')
                    lines.append("        };")
        
        if TypeMapper.is_vector(method.return_type):
            inner = TypeMapper.vector_inner(method.return_type)
            struct_def = next((d for d in self.idl.structs if d.name == inner), None)
            
            lines.append("        val result = val::array();")
            lines.append("        if (!impl_) return result;")
            lines.append(f"        auto items = impl_->{method.name}({args_str});")
            lines.append("        for (const auto& item : items) {")
            
            if struct_def:
                lines.append("            val obj = val::object();")
                for m in struct_def.members:
                    lines.append(f'            obj.set("{m.name}", item.{m.name});')
                lines.append('            result.call<void>("push", obj);')
            else:
                lines.append('            result.call<void>("push", item);')
            
            lines.append("        }")
            lines.append("        return result;")
        elif method.return_type.endswith('*'):
            # Pointer return - handle struct/class pointers specially
            base_type = method.return_type.rstrip('*').strip()
            if self._is_struct_type(base_type):
                # Struct pointer - dereference to return by value
                lines.append(f"        if (!impl_) return {base_type}{{}};")
                lines.append(f"        auto* result = impl_->{method.name}({args_str});")
                lines.append(f"        if (!result) return {base_type}{{}};")
                lines.append(f"        {base_type} copy = *result;")
                lines.append("        delete result;")
                lines.append("        return copy;")
            else:
                # Other pointer returns (class pointers, etc.)
                default = self._wasm_default(method.return_type)
                lines.append(f"        if (!impl_) return {default};")
                lines.append(f"        return impl_->{method.name}({args_str});")
        else:
            default = self._wasm_default(method.return_type)
            lines.append(f"        if (!impl_) return {default};")
            lines.append(f"        return impl_->{method.name}({args_str});")
        
        lines.append("    }")
        lines.append("")
        return lines

    def _is_callback_type(self, type_name: str) -> bool:
        """Check if type is a callback"""
        return any(cb.name == type_name for cb in self.idl.callbacks)

    def _is_struct_type(self, type_name: str) -> bool:
        """Check if type is a struct"""
        return any(s.name == type_name for s in self.idl.structs)

    def _is_class_type(self, type_name: str) -> bool:
        """Check if type is a class"""
        return any(c.name == type_name for c in self.idl.classes)

    def _get_callback_def(self, type_name: str):
        """Get callback definition by name"""
        return next((cb for cb in self.idl.callbacks if cb.name == type_name), None)

    def _wasm_cb_param_type(self, param: Param) -> str:
        """Get C++ type for callback parameter"""
        if param.type == "int":
            return f"int {param.name}"
        if param.type == "bool":
            return f"bool {param.name}"
        if param.type == "double":
            return f"double {param.name}"
        # Handle struct reference parameters
        if self._is_struct_type(param.type) and param.is_reference:
            return f"const {param.type}& {param.name}"
        if self._is_struct_type(param.type):
            return f"{param.type} {param.name}"
        return f"int {param.name}"

    def _wasm_cb_return_type(self, ret_type: str) -> str:
        """Get C++ return type for callback"""
        if ret_type == "void":
            return "void"
        if ret_type == "bool":
            return "bool"
        if ret_type == "int":
            return "int"
        return "int"

    def _wasm_param_type(self, param: Param) -> str:
        """Convert param to WASM-compatible type"""
        if param.type == "uint8_t" and param.is_pointer:
            return "val"
        if self._is_callback_type(param.type):
            return "val"
        if param.type == "string":
            return "const std::string&"
        if param.type == "int":
            return "int"
        if param.type == "bool":
            return "bool"
        # Class types need namespace prefix
        if self._is_class_type(param.type):
            return f"{self.namespace}::{param.type}"
        return TypeMapper.to_cpp(param.type)

    def _wasm_return_type(self, idl_type: str) -> str:
        # Handle pointer returns - strip pointer and return by value for WASM
        base_type = idl_type.rstrip('*').strip()
        is_pointer = idl_type.endswith('*')
        
        if TypeMapper.is_vector(idl_type):
            return "val"
        if idl_type == "bool":
            return "bool"
        if idl_type == "int":
            return "int"
        if idl_type == "string":
            return "std::string"
        # For struct/class pointer returns, return by value
        if is_pointer and (self._is_struct_type(base_type) or self._is_class_type(base_type)):
            if self._is_class_type(base_type):
                return f"{self.namespace}::{base_type}*"  # Class pointers kept as-is (wrapped)
            return base_type  # Struct returns by value
        return TypeMapper.to_cpp(idl_type)

    def _wasm_default(self, idl_type: str) -> str:
        # Handle pointer types
        if idl_type.endswith('*'):
            return "nullptr"
        if idl_type == "bool":
            return "false"
        if idl_type in ("int", "float", "double", "uint8_t"):
            return "0"
        if idl_type == "string":
            return '""'
        if TypeMapper.is_vector(idl_type):
            return "val::array()"
        return "{}"

    def _class_bindings(self, cls: Class) -> list[str]:
        wasm_class = f"Wasm{cls.name}"
        lines = [
            f"EMSCRIPTEN_BINDINGS({self.namespace}_{cls.name.lower()}) {{",
            f'    class_<{wasm_class}>("{cls.name}")',
            "        .constructor<>()",
        ]

        ctor = next((m for m in cls.methods if m.is_constructor), None)
        if ctor:
            lines.append(f'        .function("create", &{wasm_class}::create)')

        for member in cls.members:
            if member.type == "bool":
                getter = f"is{member.name[0].upper()}{member.name[1:]}"
            else:
                getter = f"get{member.name[0].upper()}{member.name[1:]}"
            lines.append(f'        .function("{getter}", &{wasm_class}::{getter})')

        for method in cls.methods:
            if method.is_constructor:
                continue
            # Skip methods returning class pointers (not supported in Emscripten)
            if self._returns_class_pointer(method):
                continue
            lines.append(f'        .function("{method.name}", &{wasm_class}::{method.name})')

        lines.append("    ;")
        lines.append("}")
        lines.append("")

        return lines

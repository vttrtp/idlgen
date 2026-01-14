"""Common Generator - generates shared header files for IDL bindings"""


class CommonGenerator:
    """Generates common header files used by all IDL-generated code"""

    def __init__(self, namespace: str, api_macro: str = ""):
        self.namespace = namespace
        self.api_macro = api_macro or f"{namespace.upper()}_API"
        self.export_macro = self.api_macro.replace("_API", "_EXPORTS")

    def generate_export_header(self) -> str:
        """Generate idl_export.h with API export macros"""
        guard = f"{self.namespace.upper()}_EXPORT_H"
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#ifdef _WIN32",
            f"    #ifdef {self.export_macro}",
            f"        #define {self.api_macro} __declspec(dllexport)",
            "    #else",
            f"        #define {self.api_macro} __declspec(dllimport)",
            "    #endif",
            "#else",
            f'    #define {self.api_macro} __attribute__((visibility("default")))',
            "#endif",
            "",
            f"#endif // {guard}",
        ]
        return "\n".join(lines)

    def generate_client_header(self) -> str:
        """Generate idl_client.hpp with common client utilities.

        Uses a global namespace-agnostic design so all per-file clients
        share the same library handle.
        """
        guard = "IDL_CLIENT_HPP"
        lines = [
            "// AUTO-GENERATED - DO NOT EDIT",
            f"#ifndef {guard}",
            f"#define {guard}",
            "",
            "#ifdef _WIN32",
            "#include <windows.h>",
            "#else",
            "#include <dlfcn.h>",
            "#endif",
            "",
            "#include <string>",
            "",
            "// Global client utilities shared by all IDL-generated namespaces",
            "namespace idl_client {",
            "",
            "namespace detail {",
            "",
            "inline void*& libraryHandle() {",
            "    static void* handle = nullptr;",
            "    return handle;",
            "}",
            "",
            "inline void* loadSymbol(const char* name) {",
            "#ifdef _WIN32",
            "    return reinterpret_cast<void*>(GetProcAddress(static_cast<HMODULE>(libraryHandle()), name));",
            "#else",
            "    return dlsym(libraryHandle(), name);",
            "#endif",
            "}",
            "",
            "inline bool loadLibrary(const std::string& path) {",
            "    if (libraryHandle()) return true;",
            "#ifdef _WIN32",
            "    libraryHandle() = LoadLibraryA(path.c_str());",
            "#else",
            "    libraryHandle() = dlopen(path.c_str(), RTLD_NOW);",
            "#endif",
            "    return libraryHandle() != nullptr;",
            "}",
            "",
            "} // namespace detail",
            "",
            "inline bool initialize(const std::string& libraryPath) {",
            "    return detail::loadLibrary(libraryPath);",
            "}",
            "",
            "inline bool isInitialized() {",
            "    return detail::libraryHandle() != nullptr;",
            "}",
            "",
            "} // namespace idl_client",
            "",
            f"#endif // {guard}",
        ]
        return "\n".join(lines)

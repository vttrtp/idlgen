"""Data types for IDL parsing"""

from dataclasses import dataclass, field
import re


@dataclass
class Param:
    """Method parameter"""
    type: str
    name: str
    is_const: bool = False
    is_pointer: bool = False
    is_reference: bool = False


@dataclass
class Member:
    """Interface or struct member"""
    name: str
    type: str
    is_const: bool = False


@dataclass
class Method:
    """Interface method"""
    name: str
    return_type: str
    params: list[Param] = field(default_factory=list)
    is_constructor: bool = False
    is_const: bool = False


@dataclass
class Callback:
    """Callback function type definition"""
    name: str
    return_type: str
    params: list[Param] = field(default_factory=list)


@dataclass
class Class:
    """IDL class definition"""
    name: str
    members: list[Member] = field(default_factory=list)
    methods: list[Method] = field(default_factory=list)


@dataclass
class Struct:
    """IDL struct definition"""
    name: str
    members: list[Member] = field(default_factory=list)


@dataclass
class EnumValue:
    """Enum value with optional explicit value"""
    name: str
    value: int | None = None


@dataclass
class Enum:
    """IDL enum definition"""
    name: str
    values: list[EnumValue] = field(default_factory=list)


@dataclass
class ParsedIDL:
    """Complete parsed IDL result"""
    enums: list[Enum] = field(default_factory=list)
    structs: list[Struct] = field(default_factory=list)
    classes: list[Class] = field(default_factory=list)
    callbacks: list[Callback] = field(default_factory=list)
    source_file: str = ""  # Source IDL filename (without path)

    def find_enum(self, name: str) -> Enum | None:
        """Find enum by name"""
        return next((e for e in self.enums if e.name == name), None)

    def find_struct(self, name: str) -> Struct | None:
        """Find struct by name"""
        return next((s for s in self.structs if s.name == name), None)

    def find_class(self, name: str) -> Class | None:
        """Find class by name"""
        return next((c for c in self.classes if c.name == name), None)

    def find_callback(self, name: str) -> Callback | None:
        """Find callback by name"""
        return next((cb for cb in self.callbacks if cb.name == name), None)

    def is_enum(self, name: str) -> bool:
        """Check if name is an enum type"""
        return self.find_enum(name) is not None

    def is_struct(self, name: str) -> bool:
        """Check if name is a struct type"""
        return self.find_struct(name) is not None

    def is_class(self, name: str) -> bool:
        """Check if name is a class type"""
        return self.find_class(name.rstrip('*').strip()) is not None

    def is_callback(self, name: str) -> bool:
        """Check if name is a callback type"""
        return self.find_callback(name) is not None

    @staticmethod
    def extract_type_name(type_str: str) -> str:
        """Extract the base type name from a type string like 'vector<FaceRect>'"""
        # Handle vector<T>
        match = re.match(r'vector\s*<\s*(\w+)\s*>', type_str)
        if match:
            return match.group(1)
        # Strip pointer/reference qualifiers
        return type_str.rstrip('*&').strip()

    def get_used_types(self) -> set[str]:
        """Get all type names used by this IDL (for dependency detection)"""
        types = set()

        # Types used in struct members
        for struct in self.structs:
            for member in struct.members:
                types.add(self.extract_type_name(member.type))

        # Types used in class methods
        for cls in self.classes:
            for method in cls.methods:
                if method.return_type != 'void':
                    types.add(self.extract_type_name(method.return_type))
                for param in method.params:
                    types.add(self.extract_type_name(param.type))
            for member in cls.members:
                types.add(self.extract_type_name(member.type))

        # Types used in callbacks
        for cb in self.callbacks:
            if cb.return_type != 'void':
                types.add(self.extract_type_name(cb.return_type))
            for param in cb.params:
                types.add(self.extract_type_name(param.type))

        # Remove primitive types
        primitives = {'void', 'bool', 'int', 'float', 'double', 'string',
                      'int8_t', 'int16_t', 'int32_t', 'int64_t',
                      'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t'}
        return types - primitives

    def get_defined_types(self) -> set[str]:
        """Get all type names defined in this IDL"""
        types = set()
        for e in self.enums:
            types.add(e.name)
        for s in self.structs:
            types.add(s.name)
        for c in self.classes:
            types.add(c.name)
        for cb in self.callbacks:
            types.add(cb.name)
        return types


@dataclass
class IDLModule:
    """Collection of parsed IDL files with dependency tracking"""
    files: list[ParsedIDL] = field(default_factory=list)

    def add_file(self, idl: ParsedIDL):
        """Add a parsed IDL file to the module"""
        self.files.append(idl)

    def find_type_source(self, type_name: str) -> ParsedIDL | None:
        """Find which IDL file defines a given type"""
        for idl in self.files:
            if type_name in idl.get_defined_types():
                return idl
        return None

    def get_dependencies(self, idl: ParsedIDL) -> list[ParsedIDL]:
        """Get list of IDL files that this file depends on"""
        deps = []
        used_types = idl.get_used_types()
        defined_types = idl.get_defined_types()

        # Find external types (used but not defined locally)
        external_types = used_types - defined_types

        for ext_type in external_types:
            source = self.find_type_source(ext_type)
            if source and source != idl and source not in deps:
                deps.append(source)

        return deps

    def get_merged_idl(self) -> ParsedIDL:
        """Get a merged view of all IDL files (for compatibility)"""
        merged = ParsedIDL()
        for idl in self.files:
            merged.enums.extend(idl.enums)
            merged.structs.extend(idl.structs)
            merged.callbacks.extend(idl.callbacks)
            merged.classes.extend(idl.classes)
        return merged

    # Delegate lookup methods to merged view
    def find_enum(self, name: str) -> Enum | None:
        for idl in self.files:
            result = idl.find_enum(name)
            if result:
                return result
        return None

    def find_struct(self, name: str) -> Struct | None:
        for idl in self.files:
            result = idl.find_struct(name)
            if result:
                return result
        return None

    def find_class(self, name: str) -> Class | None:
        for idl in self.files:
            result = idl.find_class(name)
            if result:
                return result
        return None

    def find_callback(self, name: str) -> Callback | None:
        for idl in self.files:
            result = idl.find_callback(name)
            if result:
                return result
        return None

    def is_enum(self, name: str) -> bool:
        return self.find_enum(name) is not None

    def is_struct(self, name: str) -> bool:
        return self.find_struct(name) is not None

    def is_class(self, name: str) -> bool:
        return self.find_class(name.rstrip('*').strip()) is not None

    def is_callback(self, name: str) -> bool:
        return self.find_callback(name) is not None

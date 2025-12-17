cmake_minimum_required(VERSION 3.16)
project(idlgen-samples VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Options
option(BUILD_TESTS "Build unit tests" ON)

# Set visibility for shared libraries (not applicable for WASM)
if(NOT EMSCRIPTEN)
    set(CMAKE_CXX_VISIBILITY_PRESET hidden)
    set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
endif()

# Find required packages
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# Tests (needs GTest for native builds)
if(BUILD_TESTS AND NOT EMSCRIPTEN)
    find_package(GTest CONFIG REQUIRED)
    enable_testing()
endif()

# Java JNI bindings (optional)
if(NOT EMSCRIPTEN)
    find_package(JNI QUIET)
    if(JNI_FOUND)
        message(STATUS "JNI found: ${JNI_INCLUDE_DIRS}")
    else()
        message(STATUS "JNI not found - Java bindings disabled")
    endif()
endif()

# Add samples subdirectory
add_subdirectory(samples)

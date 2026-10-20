# SPDX-License-Identifier: LGPL-3.0-or-later
cmake_minimum_required(VERSION 3.22)

if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(ardupilot_dataflash_sdk4 VERSION 2.0.0 LANGUAGES CXX)
  enable_testing()
  set(_apbin_plugin_default OFF)
else()
  set(_apbin_plugin_default ON)
endif()

option(APBIN_BUILD_PLUGIN "Build the separate PlotJuggler 4 SDK shared plugin" ${_apbin_plugin_default})
option(APBIN_BUILD_TESTS "Build DataFlash parser and ABI regressions" ON)
set(APBIN_SDK_SOURCE_DIR "" CACHE PATH "Optional exact v0.34.1 SDK checkout for development builds")
set(APBIN_PLUGIN_OUTPUT_DIRECTORY "" CACHE PATH "Optional plugin staging directory")
include(GNUInstallDirs)
set(APBIN_PLUGIN_INSTALL_DIRECTORY "${CMAKE_INSTALL_LIBDIR}" CACHE STRING
    "Install directory for the shared plugin and its manifest sidecar")

if(MSVC)
  add_compile_options(/utf-8)
endif()

add_library(ardupilot_dataflash STATIC src/DataFlashParser.cpp)
target_include_directories(ardupilot_dataflash PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(ardupilot_dataflash PUBLIC cxx_std_20)
set_target_properties(ardupilot_dataflash PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
  target_compile_options(ardupilot_dataflash PRIVATE /W4 /permissive- /utf-8)
else()
  target_compile_options(ardupilot_dataflash PRIVATE -Wall -Wextra -Wshadow -Wconversion -Wpedantic)
endif()

if(APBIN_BUILD_TESTS)
  add_executable(ardupilot_parser_test tests/parser_test.cpp)
  target_link_libraries(ardupilot_parser_test PRIVATE ardupilot_dataflash)
  add_test(NAME ArduPilotDataFlashParser
           COMMAND ardupilot_parser_test ${CMAKE_CURRENT_SOURCE_DIR}/tests
             ${CMAKE_CURRENT_SOURCE_DIR}/../tests/logs/00000001.BIN)
endif()

if(APBIN_BUILD_PLUGIN)
  if(EMSCRIPTEN OR PJ_STATIC_PLUGINS)
    message(FATAL_ERROR "The LGPL ArduPilot loader is a separate native shared plugin; static embedding is not supported")
  endif()
  if(NOT TARGET plotjuggler_sdk::plugin_sdk)
    if(APBIN_SDK_SOURCE_DIR)
      file(READ "${APBIN_SDK_SOURCE_DIR}/VERSION" _apbin_sdk_version)
      string(STRIP "${_apbin_sdk_version}" _apbin_sdk_version)
      if(NOT _apbin_sdk_version STREQUAL "0.34.1")
        message(FATAL_ERROR "APBIN_SDK_SOURCE_DIR must point to SDK v0.34.1")
      endif()
      set(PJ_BUILD_TESTS OFF CACHE BOOL "Build SDK tests" FORCE)
      set(PJ_BUILD_PORTED_PLUGINS OFF CACHE BOOL "Build SDK ported plugins" FORCE)
      add_subdirectory("${APBIN_SDK_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/sdk")
    else()
      find_package(plotjuggler_sdk 0.34.1 EXACT CONFIG REQUIRED)
    endif()
  endif()
  find_package(nlohmann_json REQUIRED)
  find_package(Python3 MODULE REQUIRED COMPONENTS Interpreter)
  set(_apbin_descriptions ${CMAKE_CURRENT_BINARY_DIR}/generated/LogDescriptions.h)
  set(_apbin_xml ${CMAKE_CURRENT_SOURCE_DIR}/../DataLoadAPBin/LogMessageDescriptions)
  add_custom_command(OUTPUT ${_apbin_descriptions}
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate_descriptions.py
            ${_apbin_xml} ${_apbin_descriptions}
    DEPENDS scripts/generate_descriptions.py ${_apbin_xml}/Copter.xml ${_apbin_xml}/Plane.xml
    VERBATIM)
  add_library(ardupilot_source_plugin SHARED src/ArduPilotSource.cpp ${_apbin_descriptions})
  target_compile_features(ardupilot_source_plugin PRIVATE cxx_std_20)
  target_include_directories(ardupilot_source_plugin PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/generated)
  target_link_libraries(ardupilot_source_plugin PRIVATE
    ardupilot_dataflash plotjuggler_sdk::plugin_sdk nlohmann_json::nlohmann_json)
  if(MSVC)
    target_compile_options(ardupilot_source_plugin PRIVATE /W4 /permissive- /utf-8)
  else()
    target_compile_options(ardupilot_source_plugin PRIVATE -Wall -Wextra -Wshadow -Wconversion -Wpedantic)
  endif()
  if(APBIN_PLUGIN_OUTPUT_DIRECTORY)
    set_target_properties(ardupilot_source_plugin PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY "${APBIN_PLUGIN_OUTPUT_DIRECTORY}"
      RUNTIME_OUTPUT_DIRECTORY "${APBIN_PLUGIN_OUTPUT_DIRECTORY}")
  endif()
  # The SDK helper installs its inspection sidecar to CMAKE_INSTALL_LIBDIR.
  # Scope the override here, leaving the parent install layout alone.
  set(_apbin_saved_install_libdir "${CMAKE_INSTALL_LIBDIR}")
  set(CMAKE_INSTALL_LIBDIR "${APBIN_PLUGIN_INSTALL_DIRECTORY}")
  pj_configure_plugin(ardupilot_source_plugin FAMILIES data_source
    MANIFEST_HEADER generated/ArduPilotManifest.h MANIFEST_VAR kArduPilotManifest)
  set(CMAKE_INSTALL_LIBDIR "${_apbin_saved_install_libdir}")
  install(TARGETS ardupilot_source_plugin LIBRARY DESTINATION "${APBIN_PLUGIN_INSTALL_DIRECTORY}"
          RUNTIME DESTINATION "${APBIN_PLUGIN_INSTALL_DIRECTORY}")
  install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/LICENSE ${CMAKE_CURRENT_SOURCE_DIR}/COPYING.GPL3
                ${CMAKE_CURRENT_SOURCE_DIR}/LICENSE.APACHE2 ${CMAKE_CURRENT_SOURCE_DIR}/UPSTREAM.md
          DESTINATION ${CMAKE_INSTALL_DATADIR}/licenses/ardupilot-dataflash)
  install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/licenses/
          DESTINATION ${CMAKE_INSTALL_DATADIR}/licenses/ardupilot-dataflash/third-party)
  if(APBIN_BUILD_TESTS)
    add_executable(ardupilot_source_test tests/source_test.cpp)
    target_compile_features(ardupilot_source_test PRIVATE cxx_std_20)
    target_link_libraries(ardupilot_source_test PRIVATE plotjuggler_sdk::plugin_host nlohmann_json::nlohmann_json)
    add_dependencies(ardupilot_source_test ardupilot_source_plugin)
    add_test(NAME ArduPilotDataFlashPlugin
      COMMAND ardupilot_source_test $<TARGET_FILE:ardupilot_source_plugin> ${CMAKE_CURRENT_SOURCE_DIR}/tests
        ${CMAKE_CURRENT_SOURCE_DIR}/../tests/logs/00000001.BIN)
  endif()
endif()

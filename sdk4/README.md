# ArduPilot BIN for PlotJuggler 4

This branch adds a native, separately loaded DataFlash plugin using
`plotjuggler_sdk` **0.34.1** and C++20. It does not require Qt and does not link
the PlotJuggler 3 Qt5 loader interface. The original `main` branch tracks the
upstream 3.x plugin; the SDK port is maintained on `plotjuggler-4.x-sdk`.
The adapter manifest identifies this prerelease as `2.0.0-rc.1`. This major
version marks the incompatible PJ3-to-PJ4 plugin ABI transition; no stable SDK
compatibility certification is implied. Download packages and checksums from
[the tagged prerelease](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v2.0.0-rc.1).
Keep the shared library and `.pjmanifest.json` together, and retain the included
license files and `SOURCE.json` attribution.

## Parser-only tests

No SDK, Qt, Conan, GTest or network access is needed:

```sh
cmake -S sdk4 -B build/parser -DCMAKE_BUILD_TYPE=Debug
cmake --build build/parser
ctest --test-dir build/parser --output-on-failure
```

## Shared SDK plugin

With the exact `plotjuggler_sdk/0.34.1` Conan package (or installed CMake
package), nlohmann_json 3.12.0, Python 3 and a C++20 compiler available:

```sh
cmake -S sdk4 -B build/sdk4 -DAPBIN_BUILD_PLUGIN=ON \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/path/to/sdk-prefix
cmake --build build/sdk4
ctest --test-dir build/sdk4 --output-on-failure
```

For source-checkout development, set
`-DAPBIN_SDK_SOURCE_DIR=/path/to/plotjuggler_sdk-v0.34.1`; the SDK additionally
requires fmt 12.1.0 and fast_float 8.1.0. That mode verifies the SDK's `VERSION`
and builds it separately. SDK tests stay disabled; this plugin's parser and
dynamic ABI regressions still run. When GCC 14 diagnoses the upstream SDK
`parser_module_abi.cpp` with `-Wfree-nonheap-object`, the SDK's documented
`-DPJ_WARNINGS_AS_ERRORS=OFF` allows that external source build. It does not
disable compiler warnings or change the SDK source.

The shared library is `ardupilot_source_plugin` (`.so` on Linux, `.dll` on
Windows). Copy it to the plugin directory selected in PlotJuggler 4, or start
the host with `--plugin-dir <directory>`. `.bin` files are advertised in the
embedded manifest. A PJ3 binary is not compatible with the PJ4 SDK.

Headless loader configuration is `{"filepath":"/path/to/log.BIN"}`. UTF-8
paths are converted through `std::filesystem` so Chinese filenames work on
Windows as well as Linux. The shared-library test exercises this boundary.

## Application integration

Fetch and pin an exact commit of this independent repository, then:

```cmake
set(APBIN_BUILD_PLUGIN ON CACHE BOOL "" FORCE)
set(APBIN_BUILD_TESTS ${PJ_BUILD_TESTS} CACHE BOOL "" FORCE)
set(APBIN_PLUGIN_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bundled_plugins" CACHE PATH "" FORCE)
set(APBIN_PLUGIN_INSTALL_DIRECTORY "lib/plotjuggler/plugins/ardupilot-dataflash" CACHE STRING "" FORCE)
add_subdirectory("${apbin_SOURCE_DIR}/sdk4" "${CMAKE_BINARY_DIR}/ardupilot")
```

This creates `ardupilot_dataflash`, `ardupilot_source_plugin`,
`ardupilot_parser_test` and `ardupilot_source_test` (test targets only when
enabled). Do not link `ardupilot_dataflash` or the plugin into the application.
Native shared loading is required; static/WASM embedding is refused.

## Data and known limits

- FMT/FMTU, UNIT/MULT, sensor instances, numeric fields, legacy/current PARM,
  both MSG layouts, parameter/default labels and message timeline are retained.
- TimeUS is stored as exact integer microseconds and checked before conversion
  to SDK nanoseconds. A usable GPS sample aligns the entire log; unresolved
  GPS weeks are ignored. The original 18-second GPS/UTC offset is retained and
  assumes logs from 2017 onward.
- Truncated tails retain earlier complete samples with a visible warning.
  Invalid schemas fail before any host data is created. Stop retains decoded
  or written data; the host applies its Keep/Discard decision.
- Upstream message/field descriptions are compiled from the original XML and
  exposed in dataset metadata. The SDK has no scalar field-tooltip writer;
  direct curve-hover tooltip parity is not implemented. See the feature audit.
- Like the source plugin, the parser reads the file and decoded samples into
  memory. Very large logs need sufficient RAM. Numeric values remain doubles
  as in the 3.x loader, while timestamps are integral.
- Array payloads and free-text fields other than MSG/PARM are not plotted;
  ISBD/ISBH records are skipped, matching the 3.x integration.
- The optional upstream RCOU function-name labels were disabled in the 3.x
  Chinese integration and are not enabled in this port.

See [provenance and licenses](UPSTREAM.md) and [feature audit](docs/PORT_AUDIT.md).

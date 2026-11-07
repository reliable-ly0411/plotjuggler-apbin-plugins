# ArduPilot DataFlash BIN plugins for PlotJuggler

This fork of [ArduPilot/plotjuggler-apbin-plugins](https://github.com/ArduPilot/plotjuggler-apbin-plugins)
provides a stable PlotJuggler 3 loader and an independent PlotJuggler 4 SDK
adapter for [ArduPilot DataFlash logs](https://ardupilot.org/copter/docs/common-logs.html).
Original authorship, Git history and LGPLv3 licensing are preserved. These are
plugins, not standalone log viewers or Chinese-localized user interfaces.

## Choose the correct plugin

- **PlotJuggler 3: stable `v1.2.0`**, maintained on `main`.
  [Download and release notes](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v1.2.0).
  Prebuilt Windows and Ubuntu 22.04 x86-64 libraries were tested against
  **PlotJuggler 3.9.2 / Qt 5**. Compatibility with other PJ3 versions, Qt
  versions or compiler ABIs is not claimed. Choose exactly one variant:
  `no_units`, `with_units`, or `with_units_rcou`.
- **PlotJuggler 4: SDK preview `v1.3.0-pj4.rc.1`**, maintained separately on
  `plotjuggler-4.x-sdk`.
  [SDK4 guide](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/blob/plotjuggler-4.x-sdk/sdk4/README.md)
  and [prerelease](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v1.3.0-pj4.rc.1).
  Requires the pinned **plotjuggler_sdk 0.34.1, boot ABI 5, data-source protocol 4**;
  this is not a promise of compatibility with every PlotJuggler 4 build.
  Windows and Ubuntu 22.04 x86-64 packages include a native shared library and
  its manifest. This preview adds leading `TimeMS` boot-clock support and does
  not replace `v1.2.0-pj4.rc.1` assets or the PJ3 stable release / Latest.

**PJ3 and PJ4 binaries are not interchangeable.** Published packages do not
cover macOS, ARM or ROS packages. The build/install instructions below are
for the **PJ3 Qt plugin only**; PJ4 users should follow the SDK4 guide instead.
For exact tested boundaries, known limits and checksums, read the selected
release's notes. Fork version numbers are not upstream ArduPilot release tags.

The PJ4 marketplace entry is **ArduPilot BIN (Contributed)**, plugin ID
`ardupilot-dataflash`. Check its advertised version before installing: a new
GitHub prerelease does not automatically update the marketplace catalog.

## Quick installation

1. Download the package/library for your host and OS, and verify it against
   that release's `SHA256SUMS`.
2. Close the host and move an older copy out of its plugin search paths to
   avoid duplicate loaders. PJ3 users should keep only one variant.
3. For PJ3, copy the selected DLL/SO into the plugin folder configured under
   **App → Preferences → Plugins**. For PJ4, extract the ZIP, keep the library
   and `.pjmanifest.json` together, retain licenses and `SOURCE.json`, and use
   the host's plugin directory or `--plugin-dir <directory>`.
4. Restart the compatible host and open an ArduPilot `.BIN` log.

See [fork provenance and maintenance](FORK.md), [release policy](RELEASING.md)
and [LICENSE](LICENSE). The SDK4 guide includes additional SDK/source licenses.

## Install PlotJuggler

To build any plugin for PlotJuggler, PlotJuggler must be installed on your system.
For detailed instructions on how to install PlotJuggler please have a look at the [Installation](https://github.com/facontidavide/PlotJuggler#installation) section of the PlotJuggler repository.

If you have ROS installed, you can install PlotJuggler using:

    sudo apt install ros-$ROS_DISTRO-plotjuggler-ros

## (Optional) Build plotjuggler-apbin-plugin

If you wish to build `plotjuggler-apbin-plugin` follow these steps.

### 1. Clone the repository

```
git clone --branch main https://github.com/reliable-ly0411/plotjuggler-apbin-plugins.git
```

### 2a. Compile via Docker

This requires that you have Docker installed in your system.

1. `cd` into the cloned repository.

2. Prepare a new folder with
    ```bash
    mkdir artifacts
    ```

3. Build the plugin with
    ```bash
    docker build -o type=local,dest=artifacts .
    ```
    This command will clone and build PlotJuggler anew, which takes a lot of time.

    You can pass build arguments with the `--build-arg` option.
    Build arguments include:
    - `ADD_UNITS[=OFF]`: Set to `ON` to enable the display of units in the logged fields. Read at the end for more information.
    - `ADD_RCOU_FUNCTION_LABELS[=OFF]`: Set to `ON` to enable the display the channel function next to its name.
    - `BASE_IMAGE[=ubuntu:22.04]`: Specify the OS image to build off of. It is known that using a different OS than your host OS may result in the plugin not working.
    - `PJ_TAG[=3.9.2]`: The PlotJuggler git branch or tag to use when cloning and compiling PlotJuggler.

Once compilation is finished, you will find your `.so` plugin in the `artifacts` folder you created previously.

### 2b. Compile locally

1. Clone and compile PlotJuggler [following the instructions](https://github.com/facontidavide/PlotJuggler/blob/main/COMPILE.md).
    Make a note of the workspace folder you created (where the `src`, `build` and `install` folders live).
1. Install the dependencies:  
    The plugin uses Qt as dependency.
    Since PlotJuggler also depends on Qt, chances are high that you already have it installed.
    On Ubuntu Qt can be installed with:

    ```bash
    sudo apt -y install qtbase5-dev libqt5svg5-dev
    ```

2. The optional features are selected with cmake options, both `OFF` by default:
    - `-DADD_UNITS=ON` displays the units of the logged fields (read at the end).
    - `-DADD_RCOU_FUNCTION_LABELS=ON` displays the channel function next to its name.

3. Compile using cmake:

    ```bash
    export PJ_WS=<absolute_path_to_plotjugger_workspace>
    export LIBRARY_PATH="$LIBRARY_PATH:$PJ_WS/install/lib"
    mkdir build; cd build
    cmake -DCMAKE_PREFIX_PATH="$PJ_WS/install/lib/cmake/plotjuggler" -DCMAKE_LIBRARY_PATH="$PJ_WS/install/lib;$PJ_WS/build/PlotJuggler" ..
    make
    sudo make install
    ```

### Testing a built plugin

`tests/` holds a headless check that loads a plugin the way PlotJuggler does and
parses the small log in `tests/logs/`, without starting the GUI.
It also verifies that the cmake options above actually reached the binary, and on
Linux reports whether the plugin's libstdc++ requirement is satisfied by your
system — which is what catches a plugin built on a newer distro than the one
running it.

```bash
cmake -S tests -B tests/build -DPJ_INCLUDE_DIR="$PJ_WS/install/include"
cmake --build tests/build
./tests/test_plugin.sh build/libDataAPBin.so
```

Point it at a plugin downloaded from CI or a release to check it before use.

### Notes for building on MacOS

Qt dependencies may not be found automatically.
If you run into issues, try this `cmake` command instead:

```bash
cmake -DCMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@5;$PJ_WS/install/lib/cmake/plotjuggler" -DCMAKE_LIBRARY_PATH="$PJ_WS/install/lib;$PJ_WS/build/PlotJuggler" ..
```

If using this plugin with the new official PlotJuggler .dmg releases, you may run into signing and security issues.
This command allows running a custom plugin on a signed version of PlotJuggler:

```bash
sudo codesign --force --deep --sign - /Applications/PlotJuggler.app
```

This likely adds your signature to the app so your plugin and the official .dmg now share a common signature.

## Install plotjuggler-apbin-plugin

PlotJuggler looks for plugins in specific folders.
Check **App->Preferences->Plugins** in PlotJuggler to find out which they are and add more if you wish to.

If you have added a folder, you will need to restart PlotJuggler for the change to take effect.

### For prebuilt binaries

You can find a pre-built plugin for Ubuntu and Windows in the [stable fork release](https://github.com/reliable-ly0411/plotjuggler-apbin-plugins/releases/tag/v1.2.0) page.
Copy that binary to one of the PlotJuggler plugin folders.

### For Docker-built binaries

If you used Docker to compile the plugin, copy the build artifact from the `artifacts` folder to one of the PlotJuggler plugin folders.

### For locally-built binaries

If you compiled the plugin in your host system, the plugin has been installed to `/usr/local/bin/`.  

Ensure that PlotJuggler scans for plugins in this folder or copy the plugin in one of the folders PlotJuggler already scans.

## Displaying units

This plugin allows the units of logged fields to be appended to the logged field names.

**Be careful:**

If you created a PlotJuggler layout without units and then enable the units, the layout will be unusable and vice-versa.
This is because the units are part of the field name; hence, the original field name no longer exists.

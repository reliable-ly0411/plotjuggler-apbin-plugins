// SPDX-License-Identifier: LGPL-3.0-or-later
// ABI fixture pattern follows plotjuggler_sdk's Apache-2.0 file_source_integration_test.cpp.
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <nlohmann/json.hpp>
#include <pj_base/sdk/service_traits.hpp>
#include <pj_plugins/host/data_source_library.hpp>
#include <pj_plugins/host/service_registry_builder.hpp>
#include <string>
#include <vector>

namespace {
int checks = 0;
void require(bool condition, std::string_view message) {
  ++checks;
  if (!condition) {
    throw std::runtime_error(std::string(message));
  }
}
std::string text(PJ_string_view_t value) {
  return std::string(value.data ? value.data : "", static_cast<std::size_t>(value.size));
}
std::string utf8(const std::filesystem::path& value) {
  const auto encoded = value.u8string();
  return std::string(encoded.begin(), encoded.end());
}

struct Host {
  std::map<std::uint32_t, std::string> topics;
  std::map<std::uint32_t, std::string> fields;
  std::map<std::string, std::vector<std::pair<std::int64_t, double>>> samples;
  std::vector<PJ_data_source_state_t> states;
  std::vector<std::string> messages;
  std::string metadata;
  std::uint64_t cancel_at = 0;
  bool stop = false;
  bool fail_append = false;
  bool fail_metadata = false;
  int starts = 0;
  int finishes = 0;
  int rows = 0;
  std::size_t largest_row = 0;
};

bool error(PJ_error_t* out, std::string_view message) noexcept {
  PJ::sdk::fillError(out, 1, "ardupilot-test", message);
  return false;
}
bool ensureTopic(void* ctx, PJ_string_view_t name, PJ_topic_handle_t* out, PJ_error_t*) noexcept {
  auto& host = *static_cast<Host*>(ctx);
  for (const auto& [id, existing] : host.topics) {
    if (existing == text(name)) {
      *out = {id};
      return true;
    }
  }
  const auto id = static_cast<std::uint32_t>(host.topics.size() + 1);
  host.topics[id] = text(name);
  *out = {id};
  return true;
}
bool ensureField(void* ctx, PJ_topic_handle_t topic, PJ_string_view_t name, PJ_primitive_type_t, PJ_field_handle_t* out,
                 PJ_error_t*) noexcept {
  auto& host = *static_cast<Host*>(ctx);
  const auto id = static_cast<std::uint32_t>(host.fields.size() + 1);
  host.fields[id] = host.topics[topic.id] + (host.topics[topic.id] == "/" ? "" : "/") + text(name);
  *out = {topic, id};
  return true;
}
bool appendBound(void* ctx, PJ_topic_handle_t, std::int64_t time, const PJ_bound_field_value_t* values,
                 std::uint64_t count, PJ_error_t* out) noexcept {
  auto& host = *static_cast<Host*>(ctx);
  if (host.fail_append) {
    return error(out, "injected append failure");
  }
  ++host.rows;
  host.largest_row = std::max(host.largest_row, static_cast<std::size_t>(count));
  for (std::uint64_t i = 0; i < count; ++i) {
    if (values[i].is_null || values[i].value.type != PJ_PRIMITIVE_TYPE_FLOAT64) {
      return error(out, "unexpected scalar wire type");
    }
    host.samples[host.fields[values[i].field.id]].emplace_back(time, values[i].value.data.as_float64);
  }
  return true;
}
bool appendNamed(void*, PJ_topic_handle_t, std::int64_t, const PJ_named_field_value_t*, std::uint64_t,
                 PJ_error_t* out) noexcept {
  return error(out, "expected bound writer");
}
bool appendArrow(void*, PJ_topic_handle_t, ArrowArrayStream*, PJ_string_view_t, PJ_error_t* out) noexcept {
  return error(out, "expected bound writer");
}
void report(void* ctx, PJ_data_source_message_level_t, PJ_string_view_t message) noexcept {
  static_cast<Host*>(ctx)->messages.push_back(text(message));
}
bool progressStart(void* ctx, PJ_string_view_t, std::uint64_t, bool, PJ_error_t*) noexcept {
  ++static_cast<Host*>(ctx)->starts;
  return true;
}
bool progressUpdate(void* ctx, std::uint64_t value) noexcept {
  auto& host = *static_cast<Host*>(ctx);
  if (host.cancel_at && value >= host.cancel_at) {
    host.stop = true;
    return false;
  }
  return true;
}
void progressFinish(void* ctx) noexcept { ++static_cast<Host*>(ctx)->finishes; }
bool isStopped(void* ctx) noexcept { return static_cast<Host*>(ctx)->stop; }
void state(void* ctx, PJ_data_source_state_t value) noexcept { static_cast<Host*>(ctx)->states.push_back(value); }
void requestStop(void*, PJ_data_source_state_t, PJ_string_view_t) noexcept {}
bool parserBinding(void*, const PJ_parser_binding_request_t*, PJ_parser_binding_handle_t*, PJ_error_t* out) noexcept {
  return error(out, "unexpected parser binding");
}
int messageBox(void*, PJ_message_box_type_t, PJ_string_view_t, PJ_string_view_t, int) noexcept { return PJ_MSG_BTN_OK; }
bool metadata(void* ctx, PJ_string_view_t document, PJ_error_t* out) noexcept {
  auto& host = *static_cast<Host*>(ctx);
  if (host.fail_metadata) {
    return error(out, "metadata disabled");
  }
  host.metadata = text(document);
  return true;
}

/// Bind actual SDK service records, not a directly linked plugin implementation.
void bind(PJ::DataSourceHandle& handle, Host& host, PJ::ServiceRegistryBuilder& registry) {
  static const PJ_source_write_host_vtable_t write = {.abi_version = PJ_PLUGIN_DATA_API_VERSION,
                                                      .struct_size = sizeof(PJ_source_write_host_vtable_t),
                                                      .ensure_topic = ensureTopic,
                                                      .ensure_field = ensureField,
                                                      .append_record = appendNamed,
                                                      .append_bound_record = appendBound,
                                                      .append_arrow_stream = appendArrow};
  static const PJ_data_source_runtime_host_vtable_t runtime = {
      .protocol_version = 1,
      .struct_size = sizeof(PJ_data_source_runtime_host_vtable_t),
      .report_message = report,
      .progress_start = progressStart,
      .progress_update = progressUpdate,
      .progress_finish = progressFinish,
      .is_stop_requested = isStopped,
      .notify_state = state,
      .request_stop = requestStop,
      .ensure_parser_binding = parserBinding,
      .show_message_box = messageBox,
      .list_available_encodings = nullptr,
      .push_message = nullptr,
      .notify_available_topics = nullptr,
      .attach_source_record = nullptr,
      .complete_ingest = nullptr,
      .set_dataset_metadata = metadata};
  registry.registerService<PJ::sdk::SourceWriteHostService>(PJ_source_write_host_t{&host, &write});
  registry.registerService<PJ::sdk::DataSourceRuntimeHostService>(PJ_data_source_runtime_host_t{&host, &runtime});
  const auto result = handle.bind(registry.view());
  require(static_cast<bool>(result), result ? "bind" : result.error());
}

void load(PJ::DataSourceHandle& handle, const std::filesystem::path& file) {
  const auto configured = handle.loadConfig(nlohmann::json{{"filepath", utf8(file)}}.dump());
  require(static_cast<bool>(configured), configured ? "configure" : configured.error());
}

void successfulImports(PJ::DataSourceLibrary& library, const std::filesystem::path& directory) {
  for (const auto* filename : {"synthetic.BIN", "gps.BIN", "second.BIN"}) {
    Host host;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / filename);
    std::string saved;
    require(static_cast<bool>(handle.saveConfig(saved)), "config can be saved");
    require(nlohmann::json::parse(saved)["filepath"] == utf8(directory / filename), "config round trip");
    const auto started = handle.start();
    require(static_cast<bool>(started), started ? "import" : started.error());
    require(handle.currentState() == PJ::DataSourceState::kStopped, "successful import state");
    require(host.starts == 1 && host.finishes == 1, "balanced FileSourceBase progress");
    require(!host.samples.empty() && !host.metadata.empty(), "data and provenance published");
    if (std::string_view(filename) == "synthetic.BIN") {
      const auto& value = host.samples.at("/TST/#200/Value\t[V]");
      require(value.size() == 1 && value[0].first == 3000000000 && std::abs(value[0].second - 3.45) < 1e-9,
              "C ABI scaled value and ns timestamp");
      require(host.samples.at("/1. Parameters/TEST_PARAM")[0].first == 1500000000, "C ABI parameter timestamp");
    } else if (std::string_view(filename) == "gps.BIN") {
      require(host.samples.at("/GPS/#0/GMS\t[s]")[1].first == 1525910382000000000LL,
              "GPS timestamp remains exact through microsecond-to-nanosecond SDK conversion");
      require(host.largest_row == 3, "shared GPS fields are published together");
      const auto document = nlohmann::json::parse(host.metadata);
      require(document["gps_synchronized"] == true && !document["series_descriptions"].empty(),
              "upstream descriptions retained as dataset metadata");
    } else {
      require(host.samples.size() == 1 && host.samples.at("/TST/Value")[0].second == 2.5,
              "new plugin instance has no cross-file state");
    }
  }
}

void errorAndStop(PJ::DataSourceLibrary& library, const std::filesystem::path& directory) {
  for (const auto* filename : {"invalid.BIN", "invalid_fmt.BIN", "invalid_fmtu.BIN", "missing.BIN"}) {
    Host host;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / filename);
    require(!handle.start(), "malformed or missing input rejected through ABI");
    require(handle.currentState() == PJ::DataSourceState::kFailed, "failed state delivered");
    require(host.samples.empty() && host.topics.empty(), "malformed file creates no partial data");
    require(host.finishes == 1, "error progress finalized");
  }
  {
    Host host;
    host.fail_append = true;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / "second.BIN");
    const auto status = handle.start();
    require(!status && status.error().find("injected append failure") != std::string::npos,
            "host write error propagates without generic exception");
  }
  {
    Host host;
    host.fail_metadata = true;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / "second.BIN");
    require(static_cast<bool>(handle.start()), "metadata refusal does not lose numeric data");
    require(host.messages.size() >= 2, "metadata refusal reported");
  }
  for (const auto cancel_at : {std::uint64_t{400}, std::uint64_t{850}}) {
    Host host;
    host.cancel_at = cancel_at;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / "synthetic.BIN");
    require(static_cast<bool>(handle.start()), "Stop and Keep returns successful partial import");
    require(!host.samples.empty() && host.stop, "Stop retains decoded/committed prefix");
    require(host.finishes == 1, "cancel progress finalized");
  }
  {
    Host host;
    host.stop = true;
    auto handle = library.createHandle();
    PJ::ServiceRegistryBuilder registry;
    bind(handle, host, registry);
    load(handle, directory / "synthetic.BIN");
    require(static_cast<bool>(handle.start()) && host.samples.empty(), "stop before reading is prompt and empty");
  }
  auto handle = library.createHandle();
  for (const auto* config : {"null", "[]", "{", "{}", "{\"filepath\":2}", "{\"filepath\":\"\"}"}) {
    require(!handle.loadConfig(config), "invalid JSON shape/type rejected");
  }
}

void unicodePath(PJ::DataSourceLibrary& library, const std::filesystem::path& directory) {
  const auto temporary = std::filesystem::temp_directory_path() /
                         ("ardupilot-sdk4-test-" +
                          std::to_string(std::filesystem::file_time_type::clock::now().time_since_epoch().count()));
  std::filesystem::create_directory(temporary);
  struct Cleanup {
    std::filesystem::path directory;
    ~Cleanup() {
      std::error_code ignored;
      std::filesystem::remove_all(directory, ignored);
    }
  } cleanup{temporary};
  const auto file = temporary / std::filesystem::path(u8"飞行日志.BIN");
  std::filesystem::copy_file(directory / "second.BIN", file);
  Host host;
  auto handle = library.createHandle();
  PJ::ServiceRegistryBuilder registry;
  bind(handle, host, registry);
  load(handle, file);
  require(static_cast<bool>(handle.start()) && host.samples.size() == 1, "UTF-8 file paths");

  std::fstream stream(file, std::ios::binary | std::ios::in | std::ios::out);
  stream.seekp(92);
  const auto overflow = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max() / 1000) + 1;
  for (int byte = 0; byte < 8; ++byte) {
    stream.put(static_cast<char>((overflow >> (8 * byte)) & 0xff));
  }
  stream.close();
  Host overflow_host;
  auto overflow_handle = library.createHandle();
  PJ::ServiceRegistryBuilder overflow_registry;
  bind(overflow_handle, overflow_host, overflow_registry);
  load(overflow_handle, file);
  require(!overflow_handle.start() && overflow_host.topics.empty(), "ns overflow rejected before host writes");

  std::filesystem::copy_file(directory / "second.BIN", file, std::filesystem::copy_options::overwrite_existing);
  std::filesystem::resize_file(file, 89);
  Host prefix_host;
  prefix_host.cancel_at = 400;
  auto prefix_handle = library.createHandle();
  PJ::ServiceRegistryBuilder prefix_registry;
  bind(prefix_handle, prefix_host, prefix_registry);
  load(prefix_handle, file);
  require(static_cast<bool>(prefix_handle.start()) && prefix_host.samples.empty(),
          "stopping while only FMT metadata has been read is not a parse failure");
}

void realLog(PJ::DataSourceLibrary& library, const std::filesystem::path& file) {
  Host host;
  auto handle = library.createHandle();
  PJ::ServiceRegistryBuilder registry;
  bind(handle, host, registry);
  load(handle, file);
  const auto status = handle.start();
  require(static_cast<bool>(status), status ? "real-log import" : status.error());
  std::size_t count = 0;
  for (const auto& [name, values] : host.samples) {
    count += values.size();
  }
  require(host.samples.size() == 1940 && count == 444443, "full real log crosses actual shared-library boundary");
  require(!host.samples.at("/RCOU/C1\t[us]").empty(), "real-log units at host boundary");
  require(nlohmann::json::parse(host.metadata)["truncated"] == true, "real-log incomplete tail is reported");
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 4) {
      throw std::runtime_error("usage: source_test plugin fixture-directory upstream-log");
    }
    auto loaded = PJ::DataSourceLibrary::load(argv[1]);
    require(static_cast<bool>(loaded), loaded ? "plugin loaded" : loaded.error());
    auto& library = *loaded;
    auto handle = library.createHandle();
    require(handle.valid(), "plugin instance created");
    require((handle.capabilities() & PJ_DATA_SOURCE_CAPABILITY_FINITE_IMPORT) != 0, "finite source capability");
    require((handle.capabilities() & PJ_DATA_SOURCE_CAPABILITY_DIRECT_INGEST) != 0, "direct ingest capability");
    require(nlohmann::json::parse(handle.manifest())["id"] == "ardupilot-dataflash", "embedded manifest identity");
    require(nlohmann::json::parse(handle.manifest())["version"] == "1.0.0-dev.1", "unreleased adapter identity");
    successfulImports(library, argv[2]);
    errorAndStop(library, argv[2]);
    unicodePath(library, argv[2]);
    realLog(library, argv[3]);
    std::cout << "PASS: " << checks << " DataFlash SDK shared-library checks\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL after " << checks << " checks: " << error.what() << '\n';
    return 1;
  }
}

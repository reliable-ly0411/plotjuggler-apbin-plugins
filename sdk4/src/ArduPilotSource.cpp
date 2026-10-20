// Copyright Pierre Kancir, Jonas Withelm (IAV GmbH)
// SPDX-License-Identifier: LGPL-3.0-only
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <nlohmann/json.hpp>
#include <pj_base/sdk/data_source_patterns.hpp>
#include <pj_base/time_math.hpp>
#include <string_view>
#include <tuple>

#include "ArduPilotManifest.h"
#include "LogDescriptions.h"
#include "ardupilot/DataFlashParser.h"

namespace {

/// The upstream XML sequence is sorted by (message, field) by the generator.
std::string_view descriptionFor(std::string_view message, std::string_view field) {
  const auto key = std::pair{message, field};
  const auto it = std::lower_bound(
      kLogDescriptions.begin(), kLogDescriptions.end(), key,
      [](const LogDescription& entry, const auto& wanted) { return std::pair{entry.message, entry.field} < wanted; });
  return it != kLogDescriptions.end() && std::pair{it->message, it->field} == key ? it->text : std::string_view{};
}

/// UTF-8 file paths must survive the wide-character Windows filesystem boundary.
std::filesystem::path pathFromUtf8(const std::string& path) {
  return std::filesystem::path(std::u8string(path.begin(), path.end()));
}

/// The independently loaded LGPL plugin owns parsing; only the SDK C ABI crosses into PJ4.
class ArduPilotSource final : public PJ::FileSourceBase {
 public:
  std::uint64_t extraCapabilities() const override { return PJ::kCapabilityDirectIngest; }

  std::string saveConfig() const override { return nlohmann::json{{"filepath", filepath_}}.dump(); }

  PJ::Status loadConfig(std::string_view text) override {
    try {
      const auto config = nlohmann::json::parse(text, nullptr, false);
      if (!config.is_object() || !config.contains("filepath") || !config["filepath"].is_string()) {
        return PJ::unexpected("ArduPilot BIN requires a string filepath");
      }
      const auto path = config["filepath"].get<std::string>();
      if (path.empty() || path.find('\0') != std::string::npos) {
        return PJ::unexpected("ArduPilot BIN requires a nonempty filepath without NUL bytes");
      }
      filepath_ = path;
      return PJ::okStatus();
    } catch (const std::exception& error) {
      return PJ::unexpected(std::string("ArduPilot BIN configuration: ") + error.what());
    }
  }

  PJ::Status importData() override {
    try {
      return importFile();
    } catch (const std::exception& error) {
      return PJ::unexpected(std::string("ArduPilot BIN: ") + error.what());
    }
  }

 private:
  /// Parse completely before any host writes, so malformed files cannot leak partial curves.
  PJ::Status importFile() {
    if (filepath_.empty()) {
      return PJ::unexpected("ArduPilot BIN: no filepath configured");
    }
    std::ifstream file(pathFromUtf8(filepath_), std::ios::binary | std::ios::ate);
    if (!file) {
      return PJ::unexpected("ArduPilot BIN: cannot open file");
    }
    const auto end = file.tellg();
    if (end < 0 || static_cast<std::uintmax_t>(end) > std::numeric_limits<std::size_t>::max()) {
      return PJ::unexpected("ArduPilot BIN: unsupported file size");
    }
    const auto file_size = static_cast<std::size_t>(end);
    file.seekg(0);
    if (auto started = runtimeHost().progressStart("ArduPilot BIN", 1000, true); !started) {
      return started;
    }
    std::vector<std::uint8_t> bytes;
    bytes.reserve(file_size);
    std::array<char, 65536> chunk{};
    bool cancelled = false;
    while (file && bytes.size() < file_size) {
      if (runtimeHost().isStopRequested()) {
        cancelled = true;
        break;
      }
      file.read(chunk.data(), static_cast<std::streamsize>(chunk.size()));
      const auto count = file.gcount();
      if (count > 0) {
        bytes.insert(bytes.end(), chunk.begin(), chunk.begin() + count);
      }
      if (!runtimeHost().progressUpdate(file_size
                                            ? static_cast<std::uint64_t>(400.0 * static_cast<double>(bytes.size()) /
                                                                         static_cast<double>(file_size))
                                            : 0)) {
        cancelled = true;
        break;
      }
    }
    if (file.bad() || (!cancelled && bytes.size() != file_size)) {
      return PJ::unexpected("ArduPilot BIN: file read failed or file changed during import");
    }
    if (cancelled && bytes.empty()) {
      return PJ::okStatus();
    }
    const auto progress = [&](std::size_t position) {
      // A stop during reading retains that prefix; do not cancel before decoding it.
      if (cancelled) {
        return true;
      }
      return !runtimeHost().isStopRequested() &&
             runtimeHost().progressUpdate(
                 400 +
                 static_cast<std::uint64_t>(
                     bytes.empty() ? 0 : 400.0 * static_cast<double>(position) / static_cast<double>(bytes.size())));
    };
    pj::ardupilot::ParseResult result;
    try {
      result = pj::ardupilot::parse(bytes, progress);
    } catch (const pj::ardupilot::ParseError& error) {
      if (cancelled && error.code() == pj::ardupilot::ParseError::Code::kNoData) {
        return PJ::okStatus();
      }
      throw;
    }
    cancelled = cancelled || result.cancelled;
    if (result.truncated || result.bytes_skipped) {
      runtimeHost().reportMessage(PJ::DataSourceMessageLevel::kWarning,
                                  "ArduPilot BIN: skipped " + std::to_string(result.bytes_skipped) +
                                      " bytes; the log contains unknown, corrupt or truncated records");
    }
    if (result.messages_without_time) {
      runtimeHost().reportMessage(
          PJ::DataSourceMessageLevel::kWarning,
          "ArduPilot BIN: ignored " + std::to_string(result.messages_without_time) + " records without TimeUS");
    }

    // Group fields by their original topic; aligned fields are written in one row,
    // and independently sampled parameters are merged with explicit sparse rows.
    std::map<std::string, std::vector<pj::ardupilot::Series*>> topics;
    std::size_t total_samples = 0;
    nlohmann::json descriptions = nlohmann::json::object();
    for (auto& series : result.series) {
      for (const auto& sample : series.samples) {
        if (!PJ::scaleToNanoseconds(sample.timestamp_us, PJ::TimeUnit::kMicroseconds)) {
          return PJ::unexpected("ArduPilot BIN: timestamp exceeds the SDK nanosecond range");
        }
      }
      const auto slash = series.name.rfind('/');
      topics[slash == 0 ? "/" : series.name.substr(0, slash)].push_back(&series);
      total_samples += series.samples.size();
      auto description = descriptionFor(series.message_name, series.field_name);
      if (description.empty()) {
        description = descriptionFor(series.message_name, "");
      }
      if (!description.empty()) {
        descriptions[series.name] = description;
      }
      std::stable_sort(series.samples.begin(), series.samples.end(),
                       [](const auto& left, const auto& right) { return left.timestamp_us < right.timestamp_us; });
    }
    std::size_t written = 0;
    for (auto& [name, series] : topics) {
      const auto topic = writeHost().ensureTopic(name);
      if (!topic) {
        return PJ::unexpected(topic.error());
      }
      std::vector<PJ::sdk::FieldHandle> handles;
      for (const auto* field : series) {
        const auto handle = writeHost().ensureField(*topic, field->name.substr(field->name.rfind('/') + 1),
                                                    PJ::PrimitiveType::kFloat64);
        if (!handle) {
          return PJ::unexpected(handle.error());
        }
        handles.push_back(*handle);
      }
      std::vector<std::size_t> positions(series.size(), 0);
      std::vector<PJ::sdk::BoundFieldValue> values;
      while (true) {
        auto next = std::numeric_limits<std::int64_t>::max();
        bool remaining = false;
        for (std::size_t i = 0; i < series.size(); ++i) {
          if (positions[i] < series[i]->samples.size()) {
            next = std::min(next, series[i]->samples[positions[i]].timestamp_us);
            remaining = true;
          }
        }
        if (!remaining) {
          break;
        }
        values.clear();
        for (std::size_t i = 0; i < series.size(); ++i) {
          if (positions[i] < series[i]->samples.size() && series[i]->samples[positions[i]].timestamp_us == next) {
            values.push_back({handles[i], series[i]->samples[positions[i]++].value});
            ++written;
          }
        }
        const auto timestamp_ns = PJ::scaleToNanoseconds(next, PJ::TimeUnit::kMicroseconds);
        auto status =
            writeHost().appendBoundRecord(*topic, PJ::Timestamp{*timestamp_ns},
                                          PJ::Span<const PJ::sdk::BoundFieldValue>(values.data(), values.size()));
        if (!status) {
          return status;
        }
        if (!cancelled &&
            (runtimeHost().isStopRequested() ||
             !runtimeHost().progressUpdate(800 + static_cast<std::uint64_t>(200.0 * static_cast<double>(written) /
                                                                            static_cast<double>(total_samples))))) {
          // The host decides Keep versus Discard. Already committed rows stay
          // available for Keep; return promptly if Stop arrived while publishing.
          return PJ::okStatus();
        }
      }
    }
    const nlohmann::json metadata = {{"format", "ArduPilot DataFlash"},
                                     {"gps_synchronized", result.gps_synchronized},
                                     {"series_descriptions", std::move(descriptions)},
                                     {"records_read", result.records_read},
                                     {"bytes_skipped", result.bytes_skipped},
                                     {"truncated", result.truncated},
                                     {"cancelled", cancelled}};
    if (auto status = runtimeHost().setDatasetMetadata(metadata.dump()); !status) {
      runtimeHost().reportMessage(PJ::DataSourceMessageLevel::kWarning,
                                  "ArduPilot BIN: dataset descriptions unavailable: " + status.error());
    }
    runtimeHost().reportMessage(PJ::DataSourceMessageLevel::kInfo,
                                "ArduPilot BIN: imported " + std::to_string(result.series.size()) + " numeric series" +
                                    (cancelled ? " (stopped; decoded prefix retained)" : ""));
    return PJ::okStatus();
  }

  std::string filepath_;
};

}  // namespace

PJ_DATA_SOURCE_PLUGIN(ArduPilotSource, kArduPilotManifest)

// Copyright Pierre Kancir, Jonas Withelm (IAV GmbH)
// SPDX-License-Identifier: LGPL-3.0-or-later
// Derived from ArduPilot/plotjuggler-apbin-plugins. See UPSTREAM.md.
#include "ardupilot/DataFlashParser.h"

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string_view>
#include <type_traits>
#include <utility>

namespace pj::ardupilot {
namespace {

constexpr std::size_t kHeaderSize = 3;
constexpr std::size_t kFormatSize = 89;
constexpr std::uint8_t kFormatId = 128;

/// The DataFlash wire types, including pre-scaled integer representations.
std::size_t fieldSize(char code) {
  switch (code) {
    case 'b':
    case 'B':
    case 'M':
      return 1;
    case 'h':
    case 'H':
    case 'c':
    case 'C':
      return 2;
    case 'i':
    case 'I':
    case 'f':
    case 'e':
    case 'E':
    case 'L':
    case 'n':
      return 4;
    case 'd':
    case 'q':
    case 'Q':
      return 8;
    case 'N':
      return 16;
    case 'a':
    case 'Z':
      return 64;
    default:
      throw ParseError("Unsupported DataFlash format code");
  }
}

bool isNumeric(char code) { return code != 'a' && code != 'n' && code != 'N' && code != 'Z'; }

/// Decode little-endian bytes without alignment or host-endianness assumptions.
template <class T>
T read(std::span<const std::uint8_t> bytes, std::size_t offset) {
  static_assert(std::is_integral_v<T> || std::is_floating_point_v<T>);
  if (offset > bytes.size() || sizeof(T) > bytes.size() - offset) {
    throw ParseError("Truncated DataFlash field");
  }
  std::array<std::uint8_t, sizeof(T)> representation{};
  std::copy_n(bytes.begin() + static_cast<std::ptrdiff_t>(offset), sizeof(T), representation.begin());
  if constexpr (std::endian::native == std::endian::big) {
    std::reverse(representation.begin(), representation.end());
  }
  return std::bit_cast<T>(representation);
}

std::string readString(std::span<const std::uint8_t> bytes, std::size_t offset, std::size_t length) {
  if (offset > bytes.size() || length > bytes.size() - offset) {
    throw ParseError("Truncated DataFlash string field");
  }
  const auto field = bytes.subspan(offset, length);
  const auto end = std::find(field.begin(), field.end(), std::uint8_t{0});
  return std::string(field.begin(), end);
}

/// FMT labels are ASCII identifiers, not arbitrary binary bytes.
bool validIdentifier(std::string_view text) {
  return !text.empty() && std::all_of(text.begin(), text.end(), [](unsigned char c) { return c >= 32 && c < 127; });
}

struct Field {
  std::string name;
  char code = 0;
  std::size_t offset = 0;
};

struct Format {
  std::string name;
  std::size_t length = 0;
  std::vector<Field> fields;
  std::vector<std::vector<double>> rows;
  std::vector<std::int64_t> timestamps;
};

struct FormatUnits {
  std::string units;
  std::string multipliers;
};

const Field* findField(const Format& format, std::string_view name) {
  const auto it =
      std::find_if(format.fields.begin(), format.fields.end(), [&](const Field& field) { return field.name == name; });
  return it == format.fields.end() ? nullptr : &*it;
}

const Field& requireField(const Format& format, std::string_view name, std::string_view codes) {
  const auto* field = findField(format, name);
  if (!field || codes.find(field->code) == std::string_view::npos) {
    throw ParseError("Missing or invalid DataFlash " + format.name + "." + std::string(name) + " field");
  }
  return *field;
}

double numericValue(std::span<const std::uint8_t> bytes, const Field& field) {
  switch (field.code) {
    case 'b':
      return read<std::int8_t>(bytes, field.offset);
    case 'B':
    case 'M':
      return read<std::uint8_t>(bytes, field.offset);
    case 'h':
    case 'c':
      return read<std::int16_t>(bytes, field.offset);
    case 'H':
    case 'C':
      return read<std::uint16_t>(bytes, field.offset);
    case 'i':
    case 'e':
    case 'L':
      return read<std::int32_t>(bytes, field.offset);
    case 'I':
    case 'E':
      return read<std::uint32_t>(bytes, field.offset);
    case 'f':
      return read<float>(bytes, field.offset);
    case 'd':
      return read<double>(bytes, field.offset);
    case 'q':
      return static_cast<double>(read<std::int64_t>(bytes, field.offset));
    case 'Q':
      return static_cast<double>(read<std::uint64_t>(bytes, field.offset));
    default:
      return 0;
  }
}

/// Preserve integer timestamp precision through GPS alignment and SDK conversion.
std::int64_t timestamp(std::span<const std::uint8_t> bytes, const Format& format) {
  const auto& field = requireField(format, "TimeUS", "Q");
  const auto value = read<std::uint64_t>(bytes, field.offset);
  if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
    throw ParseError("DataFlash timestamp exceeds supported range");
  }
  return static_cast<std::int64_t>(value);
}

Format readFormat(std::span<const std::uint8_t> bytes) {
  Format format;
  format.name = readString(bytes, 5, 4);
  format.length = bytes[4];
  const auto codes = readString(bytes, 9, 16);
  const auto labels = readString(bytes, 25, 64);
  if (!validIdentifier(format.name) || codes.empty()) {
    throw ParseError("Invalid DataFlash message name or empty format");
  }
  std::size_t offset = kHeaderSize;
  std::size_t position = 0;
  std::set<std::string> names;
  for (char code : codes) {
    const auto end = labels.find(',', position);
    const auto name = labels.substr(position, end == std::string::npos ? end : end - position);
    if (!validIdentifier(name) || !names.insert(name).second) {
      throw ParseError("Invalid or duplicate DataFlash field name");
    }
    format.fields.push_back({name, code, offset});
    offset += fieldSize(code);
    if (end == std::string::npos) {
      position = labels.size() + 1;
      break;
    }
    position = end + 1;
  }
  if (format.length != offset || format.fields.size() != codes.size() || position != labels.size() + 1) {
    throw ParseError("Invalid DataFlash FMT length or field count");
  }
  return format;
}

bool sameFormat(const Format& first, const Format& second) {
  if (first.name != second.name || first.length != second.length || first.fields.size() != second.fields.size()) {
    return false;
  }
  for (std::size_t i = 0; i < first.fields.size(); ++i) {
    if (first.fields[i].name != second.fields[i].name || first.fields[i].code != second.fields[i].code) {
      return false;
    }
  }
  return true;
}

/// Unit slashes would create extra tree nodes; preserve the loader's superscript spelling.
std::string displayUnit(std::string unit) {
  std::map<char, std::size_t> powers;
  for (auto pos = unit.find('/'); pos != std::string::npos; pos = unit.find('/')) {
    if (pos + 1 == unit.size()) {
      unit.erase(pos);
      break;
    }
    ++powers[unit[pos + 1]];
    unit.erase(pos, 2);
  }
  const std::array<std::string, 10> digits = {"⁰", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "⁹"};
  for (const auto& [base, count] : powers) {
    unit += std::string(" ") + base + "⁻";
    for (char digit : std::to_string(count)) {
      unit += digits[static_cast<std::size_t>(digit - '0')];
    }
  }
  return unit;
}

std::string defaultValue(double value) {
  std::ostringstream out;
  out.imbue(std::locale::classic());
  out << std::fixed << std::setprecision(2) << value;
  auto result = out.str();
  if (std::isfinite(value)) {
    result.erase(result.find_last_not_of('0') + 1);
    if (!result.empty() && result.back() == '.') {
      result.pop_back();
    }
  }
  return result;
}

struct Message {
  std::int64_t timestamp_us = 0;
  std::string text;
};

/// Add an offset only when it remains representable as integral microseconds.
std::int64_t shiftTime(std::int64_t time, std::int64_t offset) {
  if ((offset > 0 && time > std::numeric_limits<std::int64_t>::max() - offset) ||
      (offset < 0 && time < std::numeric_limits<std::int64_t>::min() - offset)) {
    throw ParseError("DataFlash synchronized timestamp exceeds supported range");
  }
  return time + offset;
}

}  // namespace

ParseResult parse(std::span<const std::uint8_t> bytes, const Progress& progress) {
  ParseResult result;
  std::array<std::optional<Format>, 256> formats;
  std::array<std::optional<FormatUnits>, 256> format_units;
  std::map<char, double> multipliers;
  std::map<char, std::string> units;
  std::map<std::string, Series> parameters;
  std::vector<Message> messages;
  std::size_t cursor = 0;
  std::size_t last_progress = 0;
  while (cursor < bytes.size()) {
    if (progress && (cursor == 0 || cursor - last_progress >= 65536)) {
      last_progress = cursor;
      if (!progress(cursor)) {
        result.cancelled = true;
        break;
      }
    }
    if (bytes.size() - cursor < kHeaderSize) {
      result.bytes_skipped += bytes.size() - cursor;
      result.truncated = true;
      break;
    }
    if (bytes[cursor] != 0xa3 || bytes[cursor + 1] != 0x95) {
      ++cursor;
      ++result.bytes_skipped;
      continue;
    }
    const auto id = bytes[cursor + 2];
    const auto length = id == kFormatId ? kFormatSize : formats[id] ? formats[id]->length : 0;
    if (length == 0) {
      ++cursor;
      ++result.bytes_skipped;
      continue;
    }
    if (length > bytes.size() - cursor) {
      result.bytes_skipped += bytes.size() - cursor;
      result.truncated = true;
      break;
    }
    const auto record = bytes.subspan(cursor, length);
    cursor += length;
    if (id == kFormatId) {
      const auto type = record[3];
      auto format = readFormat(record);
      if (formats[type] && !sameFormat(*formats[type], format)) {
        throw ParseError("Conflicting DataFlash FMT redefinition");
      }
      if (!formats[type]) {
        formats[type] = std::move(format);
      }
    } else {
      auto& format = *formats[id];
      if (format.name == "FMTU") {
        const auto& type_field = requireField(format, "FmtType", "B");
        const auto& unit_field = requireField(format, "UnitIds", "N");
        const auto& mult_field = requireField(format, "MultIds", "N");
        format_units[record[type_field.offset]] =
            FormatUnits{readString(record, unit_field.offset, 16), readString(record, mult_field.offset, 16)};
      } else if (format.name == "UNIT") {
        const auto& id_field = requireField(format, "Id", "Bb");
        const auto& label_field = requireField(format, "Label", "nNZ");
        units[static_cast<char>(record[id_field.offset])] =
            displayUnit(readString(record, label_field.offset, fieldSize(label_field.code)));
      } else if (format.name == "MULT") {
        const auto& id_field = requireField(format, "Id", "Bb");
        const auto& mult_field = requireField(format, "Mult", "d");
        const auto multiplier = read<double>(record, mult_field.offset);
        if (!std::isfinite(multiplier)) {
          throw ParseError("Non-finite DataFlash multiplier");
        }
        multipliers[static_cast<char>(record[id_field.offset])] = multiplier;
      } else if (format.name == "ISBD" || format.name == "ISBH") {
        ++result.records_skipped;
        continue;
      } else if (format.name == "PARM") {
        const auto& name = requireField(format, "Name", "N");
        const auto& value = requireField(format, "Value", "f");
        std::string label = readString(record, name.offset, 16);
        if (label.empty()) {
          throw ParseError("Empty DataFlash parameter name");
        }
        if (findField(format, "Default")) {
          const auto& default_field = requireField(format, "Default", "f");
          label += "          Default: " + defaultValue(numericValue(record, default_field));
        }
        auto& series = parameters[label];
        series.name = "/1. Parameters/" + label;
        series.message_name = "PARM";
        series.field_name = "Value";
        series.samples.push_back({timestamp(record, format), numericValue(record, value)});
      } else if (format.name == "MSG") {
        const auto& text = requireField(format, "Message", "nNZ");
        messages.push_back({timestamp(record, format), readString(record, text.offset, fieldSize(text.code))});
      } else if (findField(format, "TimeUS")) {
        std::vector<double> row;
        row.reserve(format.fields.size());
        for (const auto& field : format.fields) {
          row.push_back(numericValue(record, field));
        }
        format.timestamps.push_back(timestamp(record, format));
        format.rows.push_back(std::move(row));
      } else {
        ++result.messages_without_time;
      }
    }
    ++result.records_read;
  }

  std::int64_t time_offset = 0;
  std::int64_t start_plot_time = 0;
  for (std::size_t id = 0; id < formats.size(); ++id) {
    if (formats[id] && format_units[id] &&
        (format_units[id]->units.size() != formats[id]->fields.size() ||
         format_units[id]->multipliers.size() != formats[id]->fields.size())) {
      throw ParseError("Invalid DataFlash FMTU field count");
    }
  }
  for (std::size_t id = 0; id < formats.size(); ++id) {
    if (!formats[id]) {
      continue;
    }
    const auto& format = *formats[id];
    if (format.name != "GPS" || format.rows.empty()) {
      continue;
    }
    const auto* week = findField(format, "GWk");
    const auto* milliseconds = findField(format, "GMS");
    const auto* satellites = findField(format, "NSats");
    if (!week || !milliseconds || !satellites) {
      continue;
    }
    const auto index = [&](const Field* field) { return static_cast<std::size_t>(field - format.fields.data()); };
    const auto instance_position = format_units[id] ? format_units[id]->units.find('#') : std::string::npos;
    double first_instance = 0;
    if (instance_position != std::string::npos) {
      first_instance = std::numeric_limits<double>::infinity();
      for (const auto& row : format.rows) {
        first_instance = std::min(first_instance, row[instance_position]);
      }
    }
    for (std::size_t row_index = 0; row_index < format.rows.size(); ++row_index) {
      const auto& row = format.rows[row_index];
      if (instance_position != std::string::npos && row[instance_position] != first_instance) {
        continue;
      }
      const auto gps_week = row[index(week)];
      const auto gps_ms = row[index(milliseconds)];
      if (format.timestamps[row_index] == 0 || gps_week <= 0 || gps_week > 65535 || !std::isfinite(gps_week) ||
          gps_week != std::floor(gps_week) || gps_ms <= 0 || gps_ms >= 604800000 || !std::isfinite(gps_ms) ||
          gps_ms != std::floor(gps_ms) || row[index(satellites)] < 4 || !std::isfinite(row[index(satellites)])) {
        continue;
      }
      // Preserve the source loader's 18-second GPS/UTC offset (valid since 2017).
      const auto epoch_us = (static_cast<std::int64_t>(gps_week) * 604800 + 315964782) * 1000000 +
                            static_cast<std::int64_t>(gps_ms) * 1000;
      start_plot_time = format.timestamps[row_index];
      time_offset = epoch_us - start_plot_time;
      result.gps_synchronized = true;
      break;
    }
    if (result.gps_synchronized) {
      break;
    }
  }

  std::map<std::string, Series> numeric;
  for (std::size_t id = 0; id < formats.size(); ++id) {
    if (!formats[id]) {
      continue;
    }
    const auto& format = *formats[id];
    const auto instance_position = format_units[id] ? format_units[id]->units.find('#') : std::string::npos;
    if (instance_position != std::string::npos &&
        format_units[id]->units.find('#', instance_position + 1) != std::string::npos) {
      throw ParseError("Multiple DataFlash instance fields");
    }
    for (std::size_t row_index = 0; row_index < format.rows.size(); ++row_index) {
      const auto& row = format.rows[row_index];
      std::string prefix = "/" + format.name + "/";
      if (instance_position != std::string::npos) {
        const double instance = row[instance_position];
        if (!isNumeric(format.fields[instance_position].code) || !std::isfinite(instance) || instance < 0 ||
            instance > 65535 || instance != std::floor(instance)) {
          throw ParseError("Invalid DataFlash instance value");
        }
        prefix += "#" + std::to_string(static_cast<unsigned>(instance)) + "/";
      }
      const auto time = shiftTime(format.timestamps[row_index], time_offset);
      for (std::size_t field_index = 0; field_index < format.fields.size(); ++field_index) {
        const auto& field = format.fields[field_index];
        if (!isNumeric(field.code) || field.name == "TimeUS" || field_index == instance_position) {
          continue;
        }
        double value = row[field_index];
        std::string unit;
        if (format_units[id]) {
          const auto multiplier = multipliers.find(format_units[id]->multipliers[field_index]);
          if (multiplier != multipliers.end() && std::abs(multiplier->second) >= 1e-10 &&
              std::abs(multiplier->second - 1.0) >= 1e-10) {
            value *= multiplier->second;
          }
          const auto found_unit = units.find(format_units[id]->units[field_index]);
          if (found_unit != units.end()) {
            unit = found_unit->second;
          }
        }
        const auto name = prefix + field.name + (unit.empty() ? "" : "\t[" + unit + "]");
        auto& series = numeric[name];
        series.name = name;
        series.message_name = format.name;
        series.field_name = field.name;
        series.unit = unit;
        series.samples.push_back({time, value});
      }
    }
  }
  for (auto& [name, series] : numeric) {
    result.series.push_back(std::move(series));
  }
  for (auto& [name, series] : parameters) {
    for (auto& sample : series.samples) {
      sample.timestamp_us = shiftTime(sample.timestamp_us, time_offset);
    }
    result.series.push_back(std::move(series));
  }
  Series timeline;
  timeline.name = "/2. Message Timeline";
  timeline.message_name = "MSG";
  timeline.field_name = "Message";
  for (std::size_t i = 0; i < messages.size(); ++i) {
    auto& message = messages[i];
    std::replace(message.text.begin(), message.text.end(), '/', '\\');
    timeline.samples.push_back({shiftTime(message.timestamp_us, time_offset), static_cast<double>(i + 1)});
    Series series;
    series.name = "/3. Message Log/" + std::to_string(i + 1) + ". " + message.text;
    series.message_name = "MSG";
    series.field_name = "Message";
    series.samples.push_back({0, static_cast<double>(message.timestamp_us - start_plot_time) * 1e-6});
    result.series.push_back(std::move(series));
  }
  if (!timeline.samples.empty()) {
    result.series.push_back(std::move(timeline));
  }
  if (result.series.empty() && !result.cancelled) {
    throw ParseError("No plottable DataFlash records found", ParseError::Code::kNoData);
  }
  if (progress && !result.cancelled && !progress(cursor)) {
    result.cancelled = true;
  }
  return result;
}

}  // namespace pj::ardupilot

// SPDX-License-Identifier: LGPL-3.0-or-later
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <random>
#include <string_view>

#include "ardupilot/DataFlashParser.h"

namespace {
using Bytes = std::vector<std::uint8_t>;
using pj::ardupilot::parse;
using pj::ardupilot::ParseError;
using pj::ardupilot::ParseResult;
using pj::ardupilot::Series;
int checks = 0;

void require(bool condition, std::string_view message) {
  ++checks;
  if (!condition) {
    throw std::runtime_error(std::string(message));
  }
}

template <class Function>
void rejects(Function function, std::string_view message) {
  bool rejected = false;
  try {
    function();
  } catch (const ParseError&) {
    rejected = true;
  }
  require(rejected, message);
}

Bytes readFile(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  require(file.good(), "fixture is readable");
  return Bytes(std::istreambuf_iterator<char>(file), {});
}

const Series& series(const ParseResult& data, std::string_view name) {
  const auto it =
      std::find_if(data.series.begin(), data.series.end(), [&](const auto& field) { return field.name == name; });
  require(it != data.series.end(), std::string("missing series: ") + std::string(name));
  return *it;
}

template <class T>
void append(Bytes& bytes, T value) {
  auto representation = std::bit_cast<std::array<std::uint8_t, sizeof(T)>>(value);
  if constexpr (std::endian::native == std::endian::big) {
    std::reverse(representation.begin(), representation.end());
  }
  bytes.insert(bytes.end(), representation.begin(), representation.end());
}

void string(Bytes& bytes, std::string_view value, std::size_t width) {
  require(value.size() <= width, "test string fits its field");
  bytes.insert(bytes.end(), value.begin(), value.end());
  bytes.resize(bytes.size() + width - value.size());
}

Bytes fmt(std::uint8_t id, std::string_view name, std::string_view codes, std::string_view labels) {
  const std::map<char, unsigned> sizes = {{'a', 64}, {'b', 1}, {'B', 1}, {'h', 2},  {'H', 2},  {'i', 4}, {'I', 4},
                                          {'f', 4},  {'d', 8}, {'n', 4}, {'N', 16}, {'Z', 64}, {'c', 2}, {'C', 2},
                                          {'e', 4},  {'E', 4}, {'L', 4}, {'M', 1},  {'q', 8},  {'Q', 8}};
  unsigned length = 3;
  for (char code : codes) {
    length += sizes.at(code);
  }
  require(length <= 255, "test record fits the DataFlash length byte");
  Bytes bytes{0xa3, 0x95, 128, id, static_cast<std::uint8_t>(length)};
  string(bytes, name, 4);
  string(bytes, codes, 16);
  string(bytes, labels, 64);
  return bytes;
}

void join(Bytes& target, const Bytes& source) { target.insert(target.end(), source.begin(), source.end()); }

Bytes packet(std::uint8_t id) { return {0xa3, 0x95, id}; }

Bytes simple(std::uint64_t time = 4000000, double value = 2.5) {
  auto bytes = fmt(140, "TST", "Qd", "TimeUS,Value");
  auto row = packet(140);
  append(row, time);
  append(row, value);
  join(bytes, row);
  return bytes;
}

void metadataFormats(Bytes& bytes) {
  join(bytes, fmt(129, "FMTU", "QBNN", "TimeUS,FmtType,UnitIds,MultIds"));
  join(bytes, fmt(130, "UNIT", "QBZ", "TimeUS,Id,Label"));
  join(bytes, fmt(131, "MULT", "QBd", "TimeUS,Id,Mult"));
}

void units(Bytes& bytes, std::uint8_t id, std::string_view unit_ids, std::string_view mult_ids) {
  auto row = packet(129);
  append(row, std::uint64_t{0});
  append(row, id);
  string(row, unit_ids, 16);
  string(row, mult_ids, 16);
  join(bytes, row);
}

void unit(Bytes& bytes, char id, std::string_view label) {
  auto row = packet(130);
  append(row, std::uint64_t{0});
  append(row, static_cast<std::uint8_t>(id));
  string(row, label, 64);
  join(bytes, row);
}

void multiplier(Bytes& bytes, char id, double value) {
  auto row = packet(131);
  append(row, std::uint64_t{0});
  append(row, static_cast<std::uint8_t>(id));
  append(row, value);
  join(bytes, row);
}

void fixtures(const std::filesystem::path& directory) {
  const auto synthetic = parse(readFile(directory / "synthetic.BIN"));
  for (const auto& [instance, value, time] : {std::tuple{0, 1.23, 1000000}, {1, 2.34, 2000000}, {200, 3.45, 3000000}}) {
    const auto& data = series(synthetic, "/TST/#" + std::to_string(instance) + "/Value\t[V]");
    require(data.samples.size() == 1, "one sample per sensor instance");
    require(std::abs(data.samples[0].value - value) < 1e-9, "FMTU and MULT scale values once");
    require(data.samples[0].timestamp_us == time, "TimeUS stays in microseconds");
    require(data.unit == "V", "unit provenance retained");
  }
  require(series(synthetic, "/1. Parameters/TEST_PARAM").samples[0].timestamp_us == 1500000,
          "legacy parameter timestamp");
  const auto gps = parse(readFile(directory / "gps.BIN"));
  require(gps.gps_synchronized, "GPS alignment found");
  constexpr std::int64_t epoch = 1525910382000000;
  const auto& gms = series(gps, "/GPS/#0/GMS\t[s]");
  require(gms.samples.size() == 2 && gms.samples[1].timestamp_us == epoch, "unresolved GPS week ignored");
  require(std::abs(gms.samples[1].value - 345600) < 1e-8, "GPS GMS multiplier applied after time alignment");
  require(series(gps, "/1. Parameters/TEST_PARAM").samples[0].timestamp_us == epoch - 500000,
          "parameters share GPS time offset");
  const auto second = parse(readFile(directory / "second.BIN"));
  require(second.series.size() == 1 && !second.gps_synchronized, "second-file state is isolated");
  const auto& data = series(second, "/TST/Value");
  require(data.samples[0].timestamp_us == 4000000 && data.samples[0].value == 2.5,
          "second-file has no leaked instance, unit, multiplier, parameter or GPS state");
  for (const auto* filename : {"invalid.BIN", "invalid_fmt.BIN", "invalid_fmtu.BIN"}) {
    rejects([&] { (void)parse(readFile(directory / filename)); }, filename);
  }
}

void malformed() {
  rejects([] { (void)parse({}); }, "empty input rejected");
  auto bytes = simple();
  bytes[9] = '?';
  rejects([&] { (void)parse(bytes); }, "unknown format rejected");
  bytes = fmt(140, "TST", "Qd", "TimeUS,TimeUS");
  rejects([&] { (void)parse(bytes); }, "duplicate labels rejected");
  bytes = fmt(140, "TST", "Qd", "TimeUS");
  rejects([&] { (void)parse(bytes); }, "missing labels rejected");
  bytes = fmt(140, "TST", "Qd", "TimeUS,Value,Extra");
  rejects([&] { (void)parse(bytes); }, "extra labels rejected");
  bytes = simple();
  join(bytes, fmt(140, "TST", "Qf", "TimeUS,Value"));
  rejects([&] { (void)parse(bytes); }, "conflicting format redefinition rejected");
  bytes = simple();
  join(bytes, fmt(140, "TST", "Qd", "TimeUS,Value"));
  require(parse(bytes).series.size() == 1, "identical repeated format preserves data");
  bytes = simple();
  metadataFormats(bytes);
  units(bytes, 140, "s", "F");
  rejects([&] { (void)parse(bytes); }, "short FMTU field vectors rejected");
  for (const auto* name : {"UNIT", "MULT", "PARM", "MSG"}) {
    bytes = fmt(140, name, "Qd", "TimeUS,Value");
    auto row = packet(140);
    append(row, std::uint64_t{1});
    append(row, 2.5);
    join(bytes, row);
    rejects([&] { (void)parse(bytes); }, std::string("missing required fields in ") + name);
  }
  bytes = simple();
  metadataFormats(bytes);
  multiplier(bytes, 'x', std::numeric_limits<double>::infinity());
  rejects([&] { (void)parse(bytes); }, "non-finite multiplier rejected");
  bytes = simple(std::numeric_limits<std::uint64_t>::max());
  rejects([&] { (void)parse(bytes); }, "timestamp overflow rejected");
  bytes = simple();
  bytes.resize(bytes.size() - 1);
  rejects([&] { (void)parse(bytes); }, "file with no complete data rejected");
  bytes = simple();
  join(bytes, Bytes{0xa3, 0x95, 140, 0});
  const auto partial = parse(bytes);
  require(partial.truncated && series(partial, "/TST/Value").samples.size() == 1,
          "truncated tail retains earlier complete records with warning");
  bytes = {0x55, 0x12, 0x99};
  join(bytes, simple());
  require(parse(bytes).bytes_skipped == 3, "resynchronizes leading garbage");
  require(parse(simple(), [](std::size_t) { return false; }).cancelled, "cancellation before first record");
  int calls = 0;
  const auto cancelled = parse(simple(), [&](std::size_t) { return ++calls < 2; });
  require(cancelled.cancelled && cancelled.series.size() == 1, "cancellation after decode retains prefix");
  const auto nan = parse(simple(1, std::numeric_limits<double>::quiet_NaN()));
  require(std::isnan(series(nan, "/TST/Value").samples[0].value), "NaN measurements remain missing-data values");
}

void valuesAndMetadata() {
  auto bytes = fmt(140, "ALL", "QbBhHiIfdqcCL", "TimeUS,b,B,h,H,i,I,f,d,q,c,C,L");
  auto row = packet(140);
  append(row, std::uint64_t{1234567890123});
  append(row, std::int8_t{-7});
  append(row, std::uint8_t{200});
  append(row, std::int16_t{-1234});
  append(row, std::uint16_t{60000});
  append(row, std::int32_t{-1000000});
  append(row, std::uint32_t{4000000000});
  append(row, 1.25f);
  append(row, 2.125);
  append(row, std::int64_t{-1234567890123});
  append(row, std::int16_t{-500});
  append(row, std::uint16_t{600});
  append(row, std::int32_t{-1221234567});
  join(bytes, row);
  const auto parsed = parse(bytes);
  for (const auto& [field, value] : std::map<std::string, double>{{"b", -7},
                                                                  {"B", 200},
                                                                  {"h", -1234},
                                                                  {"H", 60000},
                                                                  {"i", -1000000},
                                                                  {"I", 4000000000},
                                                                  {"f", 1.25},
                                                                  {"d", 2.125},
                                                                  {"q", -1234567890123},
                                                                  {"c", -500},
                                                                  {"C", 600},
                                                                  {"L", -1221234567}}) {
    const auto& samples = series(parsed, "/ALL/" + field).samples;
    require(samples[0].value == value && samples[0].timestamp_us == 1234567890123,
            "little-endian unaligned numeric decode and exact timestamp");
  }
  bytes = simple();
  metadataFormats(bytes);
  units(bytes, 140, "sx", "Fx");
  unit(bytes, 'x', "m/s/s");
  multiplier(bytes, 'x', 0.01);
  const auto late = parse(bytes);
  require(series(late, "/TST/Value\t[m s⁻²]").samples[0].value == 0.025, "late metadata and compound unit formatting");
  bytes = fmt(140, "TST", "QHd", "TimeUS,I,Value");
  row = packet(140);
  append(row, std::uint64_t{1});
  append(row, std::uint16_t{1000});
  append(row, 3.0);
  join(bytes, row);
  metadataFormats(bytes);
  units(bytes, 140, "s#-", "F--");
  require(series(parse(bytes), "/TST/#1000/Value").samples[0].value == 3.0,
          "instance metadata after data and complete integer instance width");
  bytes = fmt(140, "TST", "Qfd", "TimeUS,I,Value");
  row = packet(140);
  append(row, std::uint64_t{1});
  append(row, std::numeric_limits<float>::quiet_NaN());
  append(row, 3.0);
  join(bytes, row);
  metadataFormats(bytes);
  units(bytes, 140, "s#-", "F--");
  rejects([&] { (void)parse(bytes); }, "invalid instance number rejected");
}

void textAndParameters() {
  for (bool modern : {false, true}) {
    auto bytes = fmt(140, "MSG", modern ? "QBBZ" : "QZ", modern ? "TimeUS,ID,Seq,Message" : "TimeUS,Message");
    auto row = packet(140);
    append(row, std::uint64_t{2500000});
    if (modern) {
      append(row, std::uint8_t{1});
      append(row, std::uint8_t{2});
    }
    string(row, "ArduCopter/test", 64);
    join(bytes, row);
    const auto data = parse(bytes);
    require(series(data, "/2. Message Timeline").samples[0].timestamp_us == 2500000, "message timeline uses TimeUS");
    require(series(data, "/3. Message Log/1. ArduCopter\\test").samples[0].value == 2.5,
            "modern and legacy MSG payloads and slash escaping");
  }
  auto bytes = fmt(140, "PARM", "QNff", "TimeUS,Name,Value,Default");
  auto row = packet(140);
  append(row, std::uint64_t{1500000});
  string(row, "TEST", 16);
  append(row, 7.5f);
  append(row, 10.0f);
  join(bytes, row);
  require(series(parse(bytes), "/1. Parameters/TEST          Default: 10").samples[0].value == 7.5,
          "parameter Default labels retained");
}

/// Exercise every truncation boundary and deterministic damaged input under sanitizers.
void damagedCorpus(const std::filesystem::path& directory) {
  const auto original = readFile(directory / "synthetic.BIN");
  for (std::size_t size = 0; size < original.size(); ++size) {
    try {
      const auto data = parse(std::span(original.data(), size));
      require(!data.series.empty(), "a non-cancelled successful prefix has samples");
    } catch (const ParseError&) {
      ++checks;
    }
  }
  std::mt19937 random(0x41504249);
  for (int iteration = 0; iteration < 1000; ++iteration) {
    auto damaged = original;
    const auto count = 1 + random() % 8;
    for (unsigned mutation = 0; mutation < count; ++mutation) {
      damaged[random() % damaged.size()] = static_cast<std::uint8_t>(random());
    }
    try {
      (void)parse(damaged);
      ++checks;
    } catch (const ParseError&) {
      ++checks;
    }
  }
}

/// Public upstream fixture includes real signed-byte UNIT/MULT IDs and a cut-off tail.
void realLog(const std::filesystem::path& file) {
  const auto data = parse(readFile(file));
  std::size_t sample_count = 0;
  for (const auto& field : data.series) {
    sample_count += field.samples.size();
  }
  require(data.series.size() == 1940 && sample_count == 444443, "frozen upstream real-log curve/sample count");
  require(data.records_read == 48341 && data.bytes_skipped == 51 && data.truncated,
          "upstream real-log truncated tail is explicit");
  require(!series(data, "/RCOU/C1\t[us]").samples.empty(), "real-log servo channel and units preserved");
  std::cout << "Real-log: " << data.series.size() << " series, " << sample_count << " samples\n";
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 3) {
      throw std::runtime_error("usage: parser_test fixture-directory upstream-log");
    }
    fixtures(argv[1]);
    malformed();
    valuesAndMetadata();
    textAndParameters();
    damagedCorpus(argv[1]);
    realLog(argv[2]);
    std::cout << "PASS: " << checks << " DataFlash parser checks\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "FAIL after " << checks << " checks: " << error.what() << '\n';
    return 1;
  }
}

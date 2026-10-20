// Copyright Pierre Kancir, Jonas Withelm (IAV GmbH)
// SPDX-License-Identifier: LGPL-3.0-only
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

namespace pj::ardupilot {

/// One numeric observation. Time is integral microseconds, GPS-synchronized when available.
struct Sample {
  std::int64_t timestamp_us = 0;
  double value = 0;
};

/// A PJ3-compatible curve path with optional unit and message-description provenance.
struct Series {
  std::string name;
  std::string message_name;
  std::string field_name;
  std::string unit;
  std::vector<Sample> samples;
};

/// Complete, independently owned output; no state survives between parse() calls.
struct ParseResult {
  std::vector<Series> series;
  std::size_t records_read = 0;
  std::size_t bytes_skipped = 0;
  std::size_t records_skipped = 0;
  std::size_t messages_without_time = 0;
  bool truncated = false;
  bool cancelled = false;
  bool gps_synchronized = false;
};

/// Structural errors abort before an adapter publishes any data.
class ParseError : public std::runtime_error {
 public:
  enum class Code { kInvalidData, kNoData };
  explicit ParseError(const std::string& message, Code code = Code::kInvalidData)
      : std::runtime_error(message), code_(code) {}
  [[nodiscard]] Code code() const noexcept { return code_; }

 private:
  Code code_;
};

/// Returning false stops at a record boundary and returns the decoded prefix.
using Progress = std::function<bool(std::size_t)>;

/// Decode DataFlash FMT/FMTU/UNIT/MULT and numeric, PARM and MSG records.
/// Unknown packets are resynchronized; a truncated tail is reported, never read past.
/// Throws ParseError for malformed schemas and files without usable records.
/// The bytes need only remain alive for the duration of this call.
[[nodiscard]] ParseResult parse(std::span<const std::uint8_t> bytes, const Progress& progress = {});

}  // namespace pj::ardupilot

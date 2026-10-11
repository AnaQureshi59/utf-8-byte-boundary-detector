"""UTF-8 byte boundary analysis.

Given a buffer that may contain a partial trailing UTF-8 multi-byte sequence,
this module reports how many additional bytes are needed to complete it (or
zero if the trailing byte is a complete code point).

Design notes
------------
- A leading byte's high bits encode the total sequence length (2, 3, or 4).
- A continuation byte alone tells you nothing about the total length, so it is
  treated as an error state rather than a guess. A parser that receives a
  truncated stream should normally have the leading byte, so this is the common
  path and the one we support precisely.
- Continuation bytes encode only their position via the low five bits; they do
  not carry the total sequence length. We could look backwards in the buffer to
  find the leading byte and compute the remaining count, but that couples this
  helper to buffer history and assumptions about what \"truncated\" means.
  Instead we return a fixed sentinel (-1) for a trailing continuation byte.
- Invalid leading byte patterns (0xC0, 0xC1, 0xF5..0xFF) are reported as errors
  rather than guessed at, because guessing would produce bytes that can never
  form a valid UTF-8 code point.
- We intentionally accept an empty buffer as \"nothing in flight\" (0), since a
  caller polling for completion of a finished stream should not get an error.
"""
from __future__ import annotations


class DecodeStatus:
    """Reason codes returned alongside completion counts.

    Kept as a plain class (not an Enum) so callers can compare against the
    class attributes directly without importing Enum machinery.
    """

    COMPLETE = "complete"
    TRUNCATED = "truncated"
    INVALID = "invalid"


def _leading_length(b: int) -> int:
    """Return total sequence length for a leading byte, or 0 if not a leader.

    Returns:
        2, 3, or 4 for a valid leading byte; 0 for an ASCII or standalone byte;
        -1 for a continuation byte; -2 for an invalid leading byte.
    """
    if b < 0x80:
        # 0xxxxxxx: single-byte ASCII code point.
        return 1
    if b < 0xC0:
        # 10xxxxxx: continuation byte, not a leader.
        return -1
    if b < 0xE0:
        # 110xxxxx: two-byte sequence. 0xC0 and 0xC1 are invalid because they
        # would encode values that fit in one byte; we flag them as errors.
        if b in (0xC0, 0xC1):
            return -2
        return 2
    if b < 0xF0:
        # 1110xxxx: three-byte sequence.
        return 3
    if b < 0xF8:
        # 11110xxx: four-byte sequence. 0xF5..0xF7 would code beyond U+10FFFF,
        # the Unicode ceiling; 0xF8..0xFF start five/six-byte forms that RFC
        # 3629 forbids. We reject all of them.
        if b >= 0xF5:
            return -2
        return 4
    return -2

def _trailing_continuation_length(buffer: bytes) -> int:
    """Walk backwards from the end to find a leading byte.

    Returns:
        * -1 if a leading byte is not found within a valid distance.
        * The number of continuation bytes still needed if the leader is found.
    """
    last = buffer[-1]
    total = _leading_length(last)
    if total == 1:
        return 0
    if total < 0:
        return total
    # We have a valid leading byte. Determine how many continuation bytes
    # follow and whether the buffer already contains enough.
    # A leading byte implies the sequence is incomplete by definition (the
    # continuation bytes are not present yet when only the leader is the last
    # byte). remaining is always >= 1 here.
    return total - 1

    # Last byte is a continuation byte. Walk backwards to find the leader.
    # Per UTF-8, continuation bytes are 0x80..0xBF, and a valid leader starts
    # a sequence of 2, 3, or 4 bytes total. We scan backwards up to 3 bytes.
    for offset in range(2, 5):
        if offset > len(buffer):
            return -1
        candidate = buffer[-offset]
        leader_total = _leading_length(candidate)
        if leader_total == -1:
            # Still a continuation byte; keep scanning backwards.
            continue
        if leader_total == 1:
            # ASCII byte cannot be followed by a continuation byte.
            return -1
        if leader_total < 0:
            # Invalid leader byte.
            return leader_total
        # Valid leader found. The number of continuation bytes we have seen
        # is (offset - 1). The total continuation bytes expected is
        # (leader_total - 1). If the count matches, the sequence is complete.
        seen_continuations = offset - 1
        expected_continuations = leader_total - 1
        if seen_continuations == expected_continuations:
            return 0
        if seen_continuations < expected_continuations:
            return expected_continuations - seen_continuations
        # More continuation bytes than expected: malformed sequence.
        return -1
    # Ran off the start of the buffer without finding a leader.
    return -1


def completion_length(buffer: bytes) -> int:
    """Return bytes needed to complete the trailing UTF-8 sequence.

    Args:
        buffer: A bytes object that may end with a partial multi-byte sequence.

    Returns:
        *  0 if the buffer ends on a complete code point.
        *  k > 0 if the trailing k bytes are the leader of a k-byte sequence
           and fewer than k are present. Note: k here is the remaining count,
           not the total length.
        * -1 if the last byte is a bare continuation byte with no recoverable
           leader context.
        * -2 if the last byte is an invalid leading byte.

    Edge cases:
        Empty buffer -> 0 (nothing in flight).
    """
    if not buffer:
        return 0
    last = buffer[-1]
    total = _leading_length(last)
    if total == 1:
        return 0
    if total < 0:
        # For continuation bytes, we look backwards to find the leader.
        if total == -1:
            for offset in range(2, 5):
                if offset > len(buffer):
                    return -1
                candidate = buffer[-offset]
                leader_total = _leading_length(candidate)
                if leader_total == -1:
                    # Still a continuation byte; keep scanning backwards.
                    continue
                if leader_total == 1:
                    # ASCII byte cannot be followed by a continuation byte.
                    return -1
                if leader_total < 0:
                    # Invalid leader byte.
                    return leader_total
                # Valid leader found. The number of continuation bytes we have
                # seen is (offset - 1). The total continuation bytes expected is
                # (leader_total - 1). If the count matches, the sequence is
                # complete.
                seen_continuations = offset - 1
                expected_continuations = leader_total - 1
                if seen_continuations == expected_continuations:
                    return 0
                if seen_continuations < expected_continuations:
                    return expected_continuations - seen_continuations
                # More continuation bytes than expected: malformed sequence.
                return -1
            # Ran off the start of the buffer without finding a leader.
            return -1
        return total
    # We have a valid leading byte. Determine how many continuation bytes
    # follow and whether the buffer already contains enough.
    # A leading byte implies the sequence is incomplete by definition (the
    # continuation bytes are not present yet when only the leader is the last
    # byte). remaining is always >= 1 here.
    return total - 1


def decode_status(buffer: bytes) -> tuple[int, str]:
    """Return (completion_length, status) for a buffer.

    Convenience wrapper that pairs the numeric result with a human-readable
    status string from DecodeStatus.
    """
    n = completion_length(buffer)
    if n == 0:
        return n, DecodeStatus.COMPLETE
    if n < 0:
        return n, DecodeStatus.INVALID
    return n, DecodeStatus.TRUNCATED

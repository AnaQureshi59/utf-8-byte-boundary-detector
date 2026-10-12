# utf-8-byte-boundary-detector

Determines the number of bytes needed to complete a UTF-8 multi-byte sequence from a partial byte buffer.

```python
from utf_8_byte_boundary_detector import completion_length, decode_status, DecodeStatus

# A buffer ending on a three-byte leader needs two more bytes.
n = completion_length(b"prefix\xe2")  # -> 2

n, status = decode_status(b"\xc3")     # -> (1, DecodeStatus.TRUNCATED)
n, status = decode_status(b"A")       # -> (0, DecodeStatus.COMPLETE)
n, status = decode_status(b"\x80")    # -> (-1, DecodeStatus.INVALID)
```

## Why this exists

When reading UTF-8 text in fixed-size chunks (network reads, file blocks), a
multi-byte sequence can be split across chunk boundaries. You need to know how
many bytes to carry over so the next chunk forms a complete code point.

The trade-off: this library only answers the question when the buffer ends on a
*leading byte*. A bare continuation byte at the end has no recoverable leader
context, so it returns -1 (an error) rather than guessing. If your reader
carries the leading byte forward, that case never arises.

## The awkward edge

A leading byte encodes the total sequence length in its high bits, but a
continuation byte does not. If your buffer ends on a continuation byte with no
leader visible, `completion_length` returns -1. Callers that always preserve
the leading byte across chunk boundaries will not hit this.

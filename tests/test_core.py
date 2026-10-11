import unittest

from utf_8_byte_boundary_detector import completion_length, decode_status, DecodeStatus


class TestCompletionLength(unittest.TestCase):
    def test_empty_buffer(self):
        self.assertEqual(completion_length(b""), 0)

    def test_ascii_complete(self):
        self.assertEqual(completion_length(b"A"), 0)
        self.assertEqual(completion_length(b"hello"), 0)

    def test_two_byte_leader_only(self):
        # 0xC3 is the leader for e.g. U+00E9 (é) which is C3 A9.
        self.assertEqual(completion_length(b"\xc3"), 1)

    def test_two_byte_complete(self):
        self.assertEqual(completion_length(b"\xc3\xa9"), 0)

    def test_three_byte_leader_only(self):
        # 0xE2 0x80 0x99 is U+2019 (right single quotation mark).
        self.assertEqual(completion_length(b"\xe2"), 2)

    def test_three_byte_one_continuation(self):
        # The leader 0xE2 starts a three-byte sequence. With one continuation
        # byte present, one more is needed to complete the code point.
        self.assertEqual(completion_length(b"\xe2\x80"), 1)

    def test_three_byte_complete(self):
        self.assertEqual(completion_length(b"\xe2\x80\x99"), 0)

    def test_four_byte_leader_only(self):
        # 0xF0 0x9F 0x98 0x80 is U+1F600 (😀).
        self.assertEqual(completion_length(b"\xf0"), 3)

    def test_four_byte_complete(self):
        self.assertEqual(completion_length(b"\xf0\x9f\x98\x80"), 0)

    def test_invalid_leading_bytes_c0_c1(self):
        self.assertEqual(completion_length(b"\xc0"), -2)
        self.assertEqual(completion_length(b"\xc1"), -2)

    def test_invalid_leading_bytes_f5_to_ff(self):
        for b in range(0xF5, 0x100):
            with self.subTest(byte=b):
                self.assertEqual(completion_length(bytes([b])), -2)

    def test_bare_continuation_byte(self):
        # A continuation byte at the end with no leader is an error state.
        self.assertEqual(completion_length(b"\x80"), -1)

    def test_text_then_partial_leader(self):
        # Complete ASCII text followed by a two-byte leader.
        self.assertEqual(completion_length(b"hello\xc3"), 1)


class TestDecodeStatus(unittest.TestCase):
    def test_complete(self):
        n, status = decode_status(b"hello")
        self.assertEqual(n, 0)
        self.assertEqual(status, DecodeStatus.COMPLETE)

    def test_truncated(self):
        n, status = decode_status(b"\xe2")
        self.assertEqual(n, 2)
        self.assertEqual(status, DecodeStatus.TRUNCATED)

    def test_invalid_leader(self):
        n, status = decode_status(b"\xc0")
        self.assertEqual(n, -2)
        self.assertEqual(status, DecodeStatus.INVALID)

    def test_invalid_continuation(self):
        n, status = decode_status(b"\x80")
        self.assertEqual(n, -1)
        self.assertEqual(status, DecodeStatus.INVALID)


if __name__ == "__main__":
    unittest.main()

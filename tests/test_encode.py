import zlib
from peripage_a40.encode import (
    encode_page, decode_page, build_job, JOB_PRELUDE,
    BYTES_PER_ROW, PAGE_ROWS, PAGE_BYTES,
)


def _page(ink_rows=()):
    ba = bytearray(PAGE_BYTES)
    for r in ink_rows:
        ba[r * BYTES_PER_ROW:(r + 1) * BYTES_PER_ROW] = b"\xff" * BYTES_PER_ROW
    return bytes(ba)


def test_roundtrip():
    bm = _page((0, 100, 2326))
    block = encode_page(bm)
    assert block[:3] == b"\x1f\x00\x00"
    assert block[3] == BYTES_PER_ROW           # 0xCE
    assert int.from_bytes(block[4:6], "big") == PAGE_ROWS
    assert block[-2:] == b"\x1d\x0c"
    out, rows = decode_page(block)
    assert rows == PAGE_ROWS and out == bm


def test_lenfield_and_adler():
    bm = _page((5,))
    block = encode_page(bm)
    length = int.from_bytes(block[6:10], "big")
    deflate = block[10:10 + length - 4]
    assert zlib.decompress(deflate, -15) == bm
    adler = block[10 + length - 4:10 + length]
    assert int.from_bytes(adler, "big") == (zlib.adler32(bm) & 0xFFFFFFFF)


def test_build_job_structure():
    blk = encode_page(_page((0,)))
    job = build_job([blk, blk])
    assert job.startswith(JOB_PRELUDE)
    # prelude has one end-page; each of 2 pages adds one -> >=3 total
    assert job.count(b"\x10\xff\xfe\x45") >= 3
    assert job.count(b"\x10\xff\x80\x01") == 2     # one begin-page per page


def test_bad_size():
    import pytest
    with pytest.raises(ValueError):
        encode_page(b"\x00" * 10)

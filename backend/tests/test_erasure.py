from __future__ import annotations

from common.erasure import ErasureCoder, Fragment


class TestErasureCoder:
    def test_encode_decode_basic(self):
        coder = ErasureCoder(k=4, m=2)
        data = b"Hello, ChunkForge! This is a test of erasure coding." * 10
        fragments = coder.encode(data)
        assert len(fragments) == 6
        # All data shards reconstruct original
        result = coder.decode(fragments[:4], len(data))
        assert result == data

    def test_decode_with_missing_shards(self):
        coder = ErasureCoder(k=4, m=2)
        data = b"A" * 1000
        fragments = coder.encode(data)
        # Remove 2 data shards, use parity to reconstruct
        surviving = [fragments[0], fragments[1], fragments[4], fragments[5]]
        result = coder.decode(surviving, len(data))
        assert result == data

    def test_reconstruct_single_fragment(self):
        coder = ErasureCoder(k=4, m=2)
        data = b"B" * 800
        fragments = coder.encode(data)
        surviving = [f for f in fragments if f.index != 2]
        reconstructed = coder.reconstruct_fragment(surviving, 2)
        assert reconstructed.data == fragments[2].data

    def test_reconstruct_parity_fragment(self):
        coder = ErasureCoder(k=4, m=2)
        data = b"C" * 600
        fragments = coder.encode(data)
        surviving = [f for f in fragments if f.index != 5]
        reconstructed = coder.reconstruct_fragment(surviving, 5)
        assert reconstructed.data == fragments[5].data

    def test_minimum_fragments_required(self):
        coder = ErasureCoder(k=4, m=2)
        data = b"D" * 400
        fragments = coder.encode(data)
        # Only 3 fragments should fail
        import pytest
        with pytest.raises(ValueError):
            coder.decode(fragments[:3], len(data))

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class Fragment:
    index: int
    data: bytes
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = hashlib.sha256(self.data).hexdigest()


# GF(2^8) arithmetic with irreducible polynomial x^8 + x^4 + x^3 + x^2 + 1
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256


def _init_gf_tables():
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _GF_EXP[i] = _GF_EXP[i - 255]


_init_gf_tables()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("GF division by zero")
    if a == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] - _GF_LOG[b]) % 255]


def _gf_inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("GF inverse of zero")
    return _GF_EXP[255 - _GF_LOG[a]]


def _gf_pow(a: int, n: int) -> int:
    if n == 0:
        return 1
    if a == 0:
        return 0
    return _GF_EXP[(_GF_LOG[a] * n) % 255]


class ErasureCoder:
    def __init__(self, k: int = 4, m: int = 2):
        self.k = k
        self.m = m
        self.n = k + m
        self._matrix = self._vandermonde_matrix()

    def _vandermonde_matrix(self) -> list[list[int]]:
        matrix = []
        for i in range(self.n):
            row = [_gf_pow(i + 1, j) for j in range(self.k)]
            matrix.append(row)
        # Replace first k rows with identity for systematic encoding
        for i in range(self.k):
            matrix[i] = [1 if j == i else 0 for j in range(self.k)]
        return matrix

    def encode(self, data: bytes) -> list[Fragment]:
        shard_size = (len(data) + self.k - 1) // self.k
        # Pad data to be divisible by k
        padded = data + b"\x00" * (shard_size * self.k - len(data))

        data_shards = [
            padded[i * shard_size: (i + 1) * shard_size] for i in range(self.k)
        ]

        fragments = []
        for i in range(self.k):
            fragments.append(Fragment(index=i, data=data_shards[i]))

        for i in range(self.k, self.n):
            parity = bytearray(shard_size)
            for byte_idx in range(shard_size):
                val = 0
                for j in range(self.k):
                    val ^= _gf_mul(self._matrix[i][j], data_shards[j][byte_idx])
                parity[byte_idx] = val
            fragments.append(Fragment(index=i, data=bytes(parity)))

        return fragments

    def decode(self, fragments: list[Fragment], original_size: int) -> bytes:
        if len(fragments) < self.k:
            raise ValueError(f"Need at least {self.k} fragments, got {len(fragments)}")

        frags = sorted(fragments[:self.k], key=lambda f: f.index)
        shard_size = len(frags[0].data)

        # If we have all k data shards, just concatenate
        indices = [f.index for f in frags]
        if indices == list(range(self.k)):
            result = b"".join(f.data for f in frags)
            return result[:original_size]

        # Build sub-matrix from available indices and invert
        sub_matrix = [self._matrix[f.index] for f in frags]
        inv_matrix = self._invert_matrix(sub_matrix)

        # Reconstruct data shards
        data_shards = []
        for i in range(self.k):
            shard = bytearray(shard_size)
            for byte_idx in range(shard_size):
                val = 0
                for j in range(self.k):
                    val ^= _gf_mul(inv_matrix[i][j], frags[j].data[byte_idx])
                shard[byte_idx] = val
            data_shards.append(bytes(shard))

        result = b"".join(data_shards)
        return result[:original_size]

    def reconstruct_fragment(self, fragments: list[Fragment], target_index: int) -> Fragment:
        if len(fragments) < self.k:
            raise ValueError(f"Need at least {self.k} fragments, got {len(fragments)}")

        frags = sorted(fragments[:self.k], key=lambda f: f.index)
        shard_size = len(frags[0].data)

        sub_matrix = [self._matrix[f.index] for f in frags]
        inv_matrix = self._invert_matrix(sub_matrix)

        target_row = self._matrix[target_index]

        # Multiply target_row by inv_matrix to get coefficients
        coeffs = [0] * self.k
        for j in range(self.k):
            val = 0
            for l in range(self.k):
                val ^= _gf_mul(target_row[l], inv_matrix[l][j])
            coeffs[j] = val

        result = bytearray(shard_size)
        for byte_idx in range(shard_size):
            val = 0
            for j in range(self.k):
                val ^= _gf_mul(coeffs[j], frags[j].data[byte_idx])
            result[byte_idx] = val

        return Fragment(index=target_index, data=bytes(result))

    def _invert_matrix(self, matrix: list[list[int]]) -> list[list[int]]:
        n = len(matrix)
        # Augmented matrix [A | I]
        aug = [row[:] + [1 if i == j else 0 for j in range(n)] for i, row in enumerate(matrix)]

        for col in range(n):
            # Find pivot
            pivot = -1
            for row in range(col, n):
                if aug[row][col] != 0:
                    pivot = row
                    break
            if pivot == -1:
                raise ValueError("Matrix is singular")
            aug[col], aug[pivot] = aug[pivot], aug[col]

            inv_pivot = _gf_inv(aug[col][col])
            aug[col] = [_gf_mul(v, inv_pivot) for v in aug[col]]

            for row in range(n):
                if row != col and aug[row][col] != 0:
                    factor = aug[row][col]
                    aug[row] = [aug[row][j] ^ _gf_mul(factor, aug[col][j]) for j in range(2 * n)]

        return [row[n:] for row in aug]

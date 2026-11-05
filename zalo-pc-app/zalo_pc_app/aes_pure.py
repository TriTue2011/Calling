"""Pure-Python AES (FIPS-197) — no third-party dependency.

Only what the Zalo PC protocol needs is exposed:
  - AES-128/192/256 block encrypt/decrypt
  - CBC mode with PKCS#7 padding

The S-box is *generated* at import from the GF(2^8) definition
(inverse + affine transform) instead of hard-coding 256 constants,
so a typo in a table cannot silently corrupt the cipher.

Verified against the FIPS-197 vectors and against `openssl enc`
(see tests/test_aes.py).
"""

# ---------------------------------------------------------------- GF(2^8)
_POLY = 0x11B


def _xtime(a):
    a <<= 1
    if a & 0x100:
        a ^= _POLY
    return a & 0xFF


def _gmul(a, b):
    p = 0
    while b:
        if b & 1:
            p ^= a
        a = _xtime(a)
        b >>= 1
    return p


def _ginv(a):
    if a == 0:
        return 0
    # a^254 in GF(2^8)
    r = 1
    for _ in range(254):
        r = _gmul(r, a)
    return r


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _make_sbox():
    box = []
    for i in range(256):
        inv = _ginv(i)
        s = inv ^ _rotl8(inv, 1) ^ _rotl8(inv, 2) ^ _rotl8(inv, 3) ^ _rotl8(inv, 4) ^ 0x63
        box.append(s & 0xFF)
    return box


_SBOX = _make_sbox()
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i

_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


# ---------------------------------------------------------------- key schedule
def _expand_key(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr


# ---------------------------------------------------------------- core rounds
def _add_round_key(state, w, rnd):
    for c in range(4):
        for r in range(4):
            state[r + 4 * c] ^= w[rnd * 4 + c][r]


def _sub_bytes(state, box):
    for i in range(16):
        state[i] = box[state[i]]


def _shift_rows(state):
    s = state[:]
    for r in range(4):
        for c in range(4):
            state[r + 4 * c] = s[r + 4 * ((c + r) % 4)]


def _inv_shift_rows(state):
    s = state[:]
    for r in range(4):
        for c in range(4):
            state[r + 4 * c] = s[r + 4 * ((c - r) % 4)]


def _mix_columns(state):
    for c in range(4):
        col = state[4 * c:4 * c + 4]
        state[4 * c + 0] = _gmul(col[0], 2) ^ _gmul(col[1], 3) ^ col[2] ^ col[3]
        state[4 * c + 1] = col[0] ^ _gmul(col[1], 2) ^ _gmul(col[2], 3) ^ col[3]
        state[4 * c + 2] = col[0] ^ col[1] ^ _gmul(col[2], 2) ^ _gmul(col[3], 3)
        state[4 * c + 3] = _gmul(col[0], 3) ^ col[1] ^ col[2] ^ _gmul(col[3], 2)


def _inv_mix_columns(state):
    for c in range(4):
        col = state[4 * c:4 * c + 4]
        state[4 * c + 0] = _gmul(col[0], 14) ^ _gmul(col[1], 11) ^ _gmul(col[2], 13) ^ _gmul(col[3], 9)
        state[4 * c + 1] = _gmul(col[0], 9) ^ _gmul(col[1], 14) ^ _gmul(col[2], 11) ^ _gmul(col[3], 13)
        state[4 * c + 2] = _gmul(col[0], 13) ^ _gmul(col[1], 9) ^ _gmul(col[2], 14) ^ _gmul(col[3], 11)
        state[4 * c + 3] = _gmul(col[0], 11) ^ _gmul(col[1], 13) ^ _gmul(col[2], 9) ^ _gmul(col[3], 14)


def encrypt_block(key, block):
    """One 16-byte block. key: 16/24/32 bytes."""
    if len(block) != 16 or len(key) not in (16, 24, 32):
        raise ValueError("bad key/block length")
    w, nr = _expand_key(key)
    state = list(block)
    _add_round_key(state, w, 0)
    for rnd in range(1, nr):
        _sub_bytes(state, _SBOX)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, w, rnd)
    _sub_bytes(state, _SBOX)
    _shift_rows(state)
    _add_round_key(state, w, nr)
    return bytes(state)


def decrypt_block(key, block):
    if len(block) != 16 or len(key) not in (16, 24, 32):
        raise ValueError("bad key/block length")
    w, nr = _expand_key(key)
    state = list(block)
    _add_round_key(state, w, nr)
    for rnd in range(nr - 1, 0, -1):
        _inv_shift_rows(state)
        _sub_bytes(state, _INV_SBOX)
        _add_round_key(state, w, rnd)
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _sub_bytes(state, _INV_SBOX)
    _add_round_key(state, w, 0)
    return bytes(state)


# ---------------------------------------------------------------- CBC + PKCS#7
def _pad(data):
    n = 16 - (len(data) % 16)
    return data + bytes([n]) * n


def _unpad(data):
    if not data or len(data) % 16:
        raise ValueError("bad padded length")
    n = data[-1]
    if n < 1 or n > 16 or data[-n:] != bytes([n]) * n:
        raise ValueError("bad PKCS#7 padding")
    return data[:-n]


def cbc_encrypt(key, iv, plaintext):
    """AES-CBC, PKCS#7. iv: 16 bytes."""
    if len(iv) != 16:
        raise ValueError("iv must be 16 bytes")
    out = bytearray()
    prev = iv
    padded = _pad(plaintext)
    for i in range(0, len(padded), 16):
        blk = bytes(a ^ b for a, b in zip(padded[i:i + 16], prev))
        enc = encrypt_block(key, blk)
        out += enc
        prev = enc
    return bytes(out)


def cbc_decrypt(key, iv, ciphertext):
    if len(iv) != 16 or len(ciphertext) % 16:
        raise ValueError("bad iv/ciphertext")
    out = bytearray()
    prev = iv
    for i in range(0, len(ciphertext), 16):
        blk = ciphertext[i:i + 16]
        dec = decrypt_block(key, blk)
        out += bytes(a ^ b for a, b in zip(dec, prev))
        prev = blk
    return _unpad(bytes(out))


ZERO_IV = bytes(16)

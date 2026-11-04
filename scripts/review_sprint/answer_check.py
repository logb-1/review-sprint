"""Deterministic answer checkers shared by all subject profiles.

CSAPP-style calculations (integer representations, IEEE-754, ALU flags, ModRM,
a small x86-64 subset) live here, and so do generic choice/numeric/exact and
matrix/determinant checkers.  Anything outside the covered set is reported as
`unknown`, never guessed.
"""
from __future__ import annotations

import re
import struct
from typing import Any

REG_CODES = {
    "rax": 0, "rcx": 1, "rdx": 2, "rbx": 3, "rsp": 4, "rbp": 5, "rsi": 6, "rdi": 7,
    "r8": 8, "r9": 9, "r10": 10, "r11": 11, "r12": 12, "r13": 13, "r14": 14, "r15": 15,
    "eax": 0, "ecx": 1, "edx": 2, "ebx": 3, "esp": 4, "ebp": 5, "esi": 6, "edi": 7,
}
REX_W = 0x48


def mask(bits: int) -> int:
    return (1 << bits) - 1


def to_unsigned(value: int, bits: int) -> int:
    return int(value) & mask(bits)


def to_signed(value: int, bits: int) -> int:
    value &= mask(bits)
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def twos_complement(value: int, bits: int = 8) -> int:
    return to_unsigned(value, bits)


def hex_bits(value: int, bits: int = 8) -> str:
    digits = max(1, (bits + 3) // 4)
    return f"0x{to_unsigned(value, bits):0{digits}X}"


def bits_of(value: int, bits: int = 8) -> str:
    return format(to_unsigned(value, bits), f"0{bits}b")


def decode_bits(bits: str, signed: bool = True) -> int:
    bits = str(bits).strip().replace(" ", "").replace("_", "")
    if not bits or any(ch not in "01" for ch in bits):
        raise ValueError("bits 必须是只含 0/1 的字符串")
    value = int(bits, 2)
    return to_signed(value, len(bits)) if signed else value


def ieee754_encode(value: float, bits: int = 32) -> str:
    if bits == 32:
        raw = struct.pack(">f", float(value))
    elif bits == 64:
        raw = struct.pack(">d", float(value))
    else:
        raise ValueError("只支持 32 或 64 位 IEEE-754")
    return "0x" + raw.hex().upper()


def ieee754_decode(hex_value: str, bits: int = 32) -> float:
    text = str(hex_value).strip().replace("_", "")
    if text.lower().startswith("0x"):
        text = text[2:]
    raw = bytes.fromhex(text)
    expected = 4 if bits == 32 else 8
    if len(raw) != expected:
        raise ValueError(f"{bits} 位需要 {expected} 字节，实际 {len(raw)}")
    fmt = ">f" if bits == 32 else ">d"
    return struct.unpack(fmt, raw)[0]


def alu_flags(a: int, b: int, op: str = "add", bits: int = 32, signed: bool = True) -> dict[str, Any]:
    if op not in {"add", "sub"}:
        raise ValueError("op 只支持 add/sub")
    a_u = to_unsigned(a, bits)
    b_u = to_unsigned(b, bits)
    if op == "add":
        result = (a_u + b_u) & mask(bits)
        carry = (a_u + b_u) > mask(bits)
        overflow = ((a_u ^ result) & (b_u ^ result) & (1 << (bits - 1))) != 0
    else:
        result = (a_u - b_u) & mask(bits)
        carry = a_u < b_u
        overflow = ((a_u ^ b_u) & (a_u ^ result) & (1 << (bits - 1))) != 0
    sign = bool(result & (1 << (bits - 1)))
    zero = result == 0
    aux = ((a_u ^ b_u ^ result) & 0x10) != 0
    parity = (result & 0xFF).bit_count() % 2 == 0
    return {
        "op": op,
        "bits": bits,
        "a": a_u,
        "b": b_u,
        "result": result,
        "resultHex": hex_bits(result, bits),
        "resultSigned": to_signed(result, bits) if signed else result,
        "CF": int(carry),
        "OF": int(overflow),
        "SF": int(sign),
        "ZF": int(zero),
        "AF": int(aux),
        "PF": int(parity),
        "flags": "".join(k for k, v in (("CF", carry), ("OF", overflow), ("SF", sign), ("ZF", zero)) if v) or "none",
    }


def modrm(mod: int, reg: int, rm: int) -> int:
    for name, value in (("mod", mod), ("reg", reg), ("rm", rm)):
        if not 0 <= int(value) <= 7:
            raise ValueError(f"{name} 必须在 0..7")
    return ((int(mod) & 7) << 6) | ((int(reg) & 7) << 3) | (int(rm) & 7)


def _reg_code(name: str) -> int:
    key = str(name).strip().lower()
    if key not in REG_CODES:
        raise ValueError(f"未知寄存器: {name}")
    return REG_CODES[key]


def _rex(w: bool, r: int, b: int, x: int = 0) -> bytes:
    byte = 0x40
    if w:
        byte |= 0x08
    if r >= 8:
        byte |= 0x04
    if x >= 8:
        byte |= 0x02
    if b >= 8:
        byte |= 0x01
    return bytes([byte]) if byte != 0x40 else b""


def _encode_mem(base: str, disp: int) -> tuple[bytes, int]:
    """Return (modrm+disp bytes tail, rm code) for [base + disp]."""
    b = _reg_code(base)
    rm = b & 7
    disp = int(disp)
    out = b""
    if disp == 0 and rm != 5:          # rbp/r13 require disp8=0
        mod = 0
    elif -128 <= disp <= 127:
        mod = 1
        out = struct.pack("<b", disp)
    else:
        mod = 2
        out = struct.pack("<i", disp)
    head = bytes([((mod & 3) << 6) | rm])
    if rm == 4:                         # rsp/r12 need SIB
        head = bytes([((mod & 3) << 6) | 4, 0x24])
    return head + out, rm


def machine_code(op: str, operands: list[Any]) -> str:
    """Encode a tiny, documented x86-64 subset. Returns uppercase hex."""
    op = op.lower().strip()
    ops = list(operands)
    if op == "nop":
        return "90"
    if op == "ret":
        return "C3"
    if op == "leave":
        return "C9"
    if op == "syscall":
        return "0F05"
    if op in {"push", "pop"} and len(ops) == 1:
        code = _reg_code(ops[0])
        base = 0x50 if op == "push" else 0x58
        return (_rex(False, 0, code) + bytes([base + (code & 7)])).hex().upper()
    if op == "jmp" and len(ops) == 1:
        rel = int(ops[0])
        if -128 <= rel <= 127:
            return ("EB" + struct.pack("<b", rel).hex()).upper()
        return ("E9" + struct.pack("<i", rel).hex()).upper()
    if op == "call" and len(ops) == 1:
        return ("E8" + struct.pack("<i", int(ops[0])).hex()).upper()
    if op == "mov" and len(ops) == 2:
        dst, src = ops
        if isinstance(src, int) and isinstance(dst, str):
            code = _reg_code(dst)
            imm = struct.pack("<Q", src & mask(64))
            return (_rex(True, 0, code) + bytes([0xB8 + (code & 7)]) + imm).hex().upper()
        if isinstance(dst, str) and isinstance(src, str):
            d, s = _reg_code(dst), _reg_code(src)
            return (_rex(True, s, d) + bytes([0x89, 0xC0 | ((s & 7) << 3) | (d & 7)])).hex().upper()
        if isinstance(dst, tuple) and isinstance(src, str):
            base, disp = dst
            s = _reg_code(src)
            tail, rm = _encode_mem(base, disp)
            b = _reg_code(base)
            modrm_byte = tail[0]
            rest = tail[1:]
            new_modrm = (modrm_byte & 0xC0) | ((s & 7) << 3) | (rm & 7)
            return (_rex(True, s, b) + bytes([0x89, new_modrm]) + rest).hex().upper()
    if op == "lea" and len(ops) == 2 and isinstance(ops[0], str) and isinstance(ops[1], tuple):
        dst = _reg_code(ops[0])
        base, disp = ops[1]
        tail, rm = _encode_mem(base, disp)
        b = _reg_code(base)
        modrm_byte = tail[0]
        rest = tail[1:]
        new_modrm = (modrm_byte & 0xC0) | ((dst & 7) << 3) | (rm & 7)
        return (_rex(True, dst, b) + bytes([0x8D, new_modrm]) + rest).hex().upper()
    if op in {"add", "sub", "cmp", "xor", "and", "or"} and len(ops) == 2:
        opcodes = {"add": 0x01, "sub": 0x29, "cmp": 0x39, "xor": 0x31, "and": 0x21, "or": 0x09}
        dst, src = ops
        if isinstance(dst, str) and isinstance(src, str):
            d, s = _reg_code(dst), _reg_code(src)
            return (_rex(True, s, d) + bytes([opcodes[op], 0xC0 | ((s & 7) << 3) | (d & 7)])).hex().upper()
        if isinstance(dst, tuple) and isinstance(src, str):
            base, disp = dst
            s = _reg_code(src)
            tail, rm = _encode_mem(base, disp)
            b = _reg_code(base)
            modrm_byte = tail[0]
            rest = tail[1:]
            return (_rex(True, s, b) + bytes([opcodes[op], (modrm_byte & 0x38) | (rm & 7)]) + rest).hex().upper()
    raise ValueError(f"未覆盖的指令或操作数: {op} {operands}")


def determinant(rows: list[list[float]]) -> float:
    """Determinant by Gaussian elimination with partial pivoting."""
    matrix = [[float(x) for x in row] for row in rows]
    n = len(matrix)
    if n == 0 or any(len(row) != n for row in matrix):
        raise ValueError("行列式必须是 n×n 方阵")
    sign = 1.0
    det = 1.0
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(matrix[r][col]))
        if abs(matrix[pivot][col]) < 1e-12:
            return 0.0
        if pivot != col:
            matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
            sign *= -1
        det *= matrix[col][col]
        for r in range(col + 1, n):
            factor = matrix[r][col] / matrix[col][col]
            for c in range(col, n):
                matrix[r][c] -= factor * matrix[col][c]
    return sign * det


def compute(spec: dict[str, Any]) -> dict[str, Any]:
    kind = (spec or {}).get("kind", "")
    if kind == "twos":
        value = int(spec.get("value", 0))
        bits = int(spec.get("bits", 8))
        return {
            "kind": kind, "bits": bits, "value": value,
            "hex": hex_bits(value, bits), "binary": bits_of(value, bits),
            "unsigned": to_unsigned(value, bits),
        }
    if kind == "decode":
        bits = str(spec.get("bits", ""))
        signed = bool(spec.get("signed", True))
        value = decode_bits(bits, signed=signed)
        return {"kind": kind, "bits": bits, "signed": signed, "value": value, "hex": hex_bits(value, len(bits))}
    if kind == "ieee754":
        value = float(spec.get("value", 0.0))
        bits = int(spec.get("bits", 32))
        return {"kind": kind, "bits": bits, "value": value, "hex": ieee754_encode(value, bits)}
    if kind == "ieee754_decode":
        text = str(spec.get("hex", "0"))
        bits = int(spec.get("bits", 32))
        return {"kind": kind, "bits": bits, "hex": text, "value": ieee754_decode(text, bits)}
    if kind == "flags":
        return {"kind": kind, **alu_flags(
            int(spec.get("a", 0)), int(spec.get("b", 0)),
            op=str(spec.get("op", "add")), bits=int(spec.get("bits", 32)),
            signed=bool(spec.get("signed", True)),
        )}
    if kind == "modrm":
        value = modrm(int(spec.get("mod", 0)), int(spec.get("reg", 0)), int(spec.get("rm", 0)))
        return {"kind": kind, "byte": f"0x{value:02X}", "binary": f"{value:08b}"}
    if kind == "machine":
        code = machine_code(str(spec.get("op", "")), list(spec.get("operands", [])))
        return {"kind": kind, "hex": code, "bytes": len(code) // 2}
    if kind == "choice":
        answer = re.sub(r"[^A-Za-z]", "", str(spec.get("answer", ""))).upper()
        return {"kind": kind, "answer": answer}
    if kind == "exact":
        return {"kind": kind, "text": str(spec.get("text", "")).strip()}
    if kind == "numeric":
        return {"kind": kind, "value": float(spec.get("value", 0.0)), "tolerance": float(spec.get("tolerance", 0.0))}
    if kind in {"matrix", "determinant"}:
        rows = spec.get("rows") or spec.get("matrix") or spec.get("a") or []
        op = str(spec.get("op") or ("det" if kind == "determinant" else "det"))
        if op in {"det", "determinant"}:
            value = determinant(rows)
            return {"kind": kind, "op": "det", "rows": rows, "value": round(value, 10),
                    "tolerance": float(spec.get("tolerance", 1e-9))}
        if op in {"equal", "eq"}:
            other = spec.get("b") or spec.get("other") or []
            same = len(rows) == len(other) and all(
                len(r) == len(o) and all(abs(float(x) - float(y)) <= 1e-9 for x, y in zip(r, o))
                for r, o in zip(rows, other)
            )
            return {"kind": kind, "op": "equal", "rows": rows, "b": other, "equal": same}
        raise ValueError(f"matrix 只支持 op=det/equal，收到 {op}")
    raise ValueError(f"未知的校验类型: {kind}")


def primary_value(result: Any) -> Any:
    """Pick the field a student would write on the answer sheet."""
    if not isinstance(result, dict):
        return result
    kind = result.get("kind")
    if kind in {"twos", "ieee754", "machine"}:
        return result.get("hex")
    if kind in {"decode", "ieee754_decode"}:
        return result.get("value")
    if kind == "numeric":
        return result.get("value")
    if kind in {"matrix", "determinant"}:
        return result.get("value") if result.get("op") == "det" else result.get("equal")
    if kind == "exact":
        return result.get("text")
    if kind == "choice":
        return result.get("answer")
    if kind == "modrm":
        return result.get("byte")
    if kind == "flags":
        return {k: result.get(k) for k in ("CF", "OF", "SF", "ZF", "AF", "PF")}
    if "answer" in result:
        return result["answer"]
    return result


def _norm_text(value: Any) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = text.replace("＝", "=").replace("，", ",").replace("；", ";")
    text = text.replace(" ", "").replace("_", "")
    return text


def _as_number(value: Any) -> float | None:
    text = _norm_text(value)
    if not text:
        return None
    sign = -1 if text.startswith("-") else 1
    body = text.lstrip("+-")
    try:
        if body.startswith("0x"):
            return sign * float(int(body, 16))
        if body.startswith("0b"):
            return sign * float(int(body, 2))
        return sign * float(body)
    except (TypeError, ValueError):
        return None


def _parse_flags(value: Any) -> dict[str, int] | None:
    if isinstance(value, dict):
        flags = {str(k).upper(): int(v) for k, v in value.items() if str(k).upper() in {"CF", "OF", "SF", "ZF", "AF", "PF"}}
        return flags or None
    text = str(value or "").upper()
    found = dict(re.findall(r"\b(CF|OF|SF|ZF|AF|PF)\s*=\s*([01])\b", text))
    if found:
        return {k: int(v) for k, v in found.items()}
    return None


def compare(official: Any, recomputed: Any) -> str:
    """Return same / different / unknown for a question's answer fields.

    Compares the *field a student writes* (hex/value/byte/flags), not the whole
    diagnostics dict.  Accepts 0xFB / FB / 251, full-width punctuation, and
    partial flag strings such as "CF=1, SF=1".
    """
    if official is None or recomputed is None:
        return "unknown"
    if isinstance(recomputed, dict) and recomputed.get("kind") == "choice":
        def letters(value: Any) -> set[str]:
            return set(re.findall(r"[A-Za-z]", str(value or "").upper()))
        return "same" if letters(official) == letters(recomputed.get("answer")) and letters(official) else "different"
    if isinstance(recomputed, dict) and recomputed.get("kind") == "numeric":
        a_num, b_num = _as_number(official), _as_number(recomputed.get("value"))
        if a_num is None or b_num is None:
            return "unknown"
        tolerance = abs(float(recomputed.get("tolerance", 0.0)))
        return "same" if abs(a_num - b_num) <= max(tolerance, 1e-9) else "different"
    expected = primary_value(recomputed)
    if isinstance(expected, dict) and expected.get("CF") is not None:
        official_flags = _parse_flags(official)
        if official_flags is not None:
            return "same" if all(int(expected.get(k, -1)) == v for k, v in official_flags.items()) else "different"
    if isinstance(expected, dict):
        # generic dict: require every key the user supplied to match
        if isinstance(official, dict):
            return "same" if all(_norm_text(official.get(k)) == _norm_text(v) for k, v in expected.items() if k in official) else "different"
        return "unknown"

    a, b = _norm_text(official), _norm_text(expected)
    if a == b:
        return "same"

    def binary_like(value: str) -> bool:
        return 4 <= len(value) <= 16 and all(ch in "01" for ch in value)

    # decode/twos often answers with a bit string; accept signed or unsigned reading
    if binary_like(a) or binary_like(b):
        bits_text = a if binary_like(a) else b
        other = _as_number(b if binary_like(a) else a)
        if other is not None:
            raw = int(bits_text, 2)
            signed = to_signed(raw, len(bits_text))
            return "same" if other in {float(raw), float(signed)} else "different"

    # numeric / radix equivalence: 0xFB == 251 == FB(hex literal)
    na, nb = _as_number(official), _as_number(expected)
    if na is not None and nb is not None:
        return "same" if abs(na - nb) < 1e-9 else "different"

    # bare hex on one side: accept FB vs 0xFB
    try:
        ah = a[2:] if a.startswith(("0x", "+0x", "-0x")) else a
        bh = b[2:] if b.startswith(("0x", "+0x", "-0x")) else b
        if ah and bh and all(ch in "0123456789abcdef" for ch in ah) and all(ch in "0123456789abcdef" for ch in bh):
            return "same" if int(ah, 16) == int(bh, 16) else "different"
    except ValueError:
        pass
    return "different"


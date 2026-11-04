"""Deterministic recomputation for CSAPP-style answers.

The goal is not to be a full assembler: it covers the calculations that appear
most often in 计算机系统基础 papers (integer representations, IEEE-754, ALU
flags, ModRM and a small x86-64 instruction subset).  Anything outside the
covered set is reported as `unknown`, never guessed.
"""
from __future__ import annotations

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
    raise ValueError(f"未知的校验类型: {kind}")


def compare(official: Any, recomputed: Any) -> str:
    """Return same / different / unknown for a question's answer fields."""
    if official is None or recomputed is None:
        return "unknown"

    def norm(value: Any) -> str:
        if isinstance(value, dict):
            return "|".join(f"{k}={norm(v)}" for k, v in sorted(value.items()))
        if isinstance(value, (list, tuple)):
            return "|".join(norm(v) for v in value)
        return str(value).strip().lower().replace(" ", "").replace("0x", "")

    return "same" if norm(official) == norm(recomputed) else "different"

"""Package with a build-local workaround for CPython 3.10.0 bpo-45757."""
import dis
import sys


def unpack_opargs(code):
    # CPython fixed this in 3.10.1: no-argument opcodes must clear EXTENDED_ARG.
    # https://github.com/python/cpython/issues/89918
    extended = 0
    for offset in range(0, len(code), 2):
        opcode = code[offset]
        operand = code[offset + 1] | extended if opcode >= dis.HAVE_ARGUMENT else None
        extended = operand << 8 if opcode == dis.EXTENDED_ARG else 0
        yield offset, opcode, operand


if __name__ == "__main__":
    if sys.version_info[:3] == (3, 10, 0):
        dis._unpack_opargs = unpack_opargs
    from PyInstaller.__main__ import run
    run()

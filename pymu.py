import logging
from collections import Generator
from pathlib import Path
from typing import List, Iterator

_LOGGER = logging.getLogger(__name__)
THIS_DIR = Path(__file__).parent


def load_rom(pathname: str) -> bytes:
    path = THIS_DIR / pathname
    data = path.read_bytes()
    _LOGGER.info("Loading ROM %s", path)
    if len(data) != 0x4000:
        raise RuntimeError(f"Bad ROM size: {len(data)} for {path}")
    return data


class Memory:
    _ram: bytearray = bytearray(65536)

    def read_word(self, offset: int) -> int:
        return self.read_byte(offset) + 256 * self.read_byte(offset + 1)

    def read_byte(self, offset: int) -> int:
        return self._ram[offset & 0xffff]

    def write_byte(self, offset: int, value: int) -> None:
        if offset < 0x8000:
            self._ram[offset] = value

    def load_os(self, data: bytes) -> None:
        for i in range(len(data)):
            self._ram[0xc000 + i] = data[i]


class Flags:
    zero: bool = False
    negative: bool = False
    irq_disable: bool = False
    decimal: bool = False

    def setzn(self, value):
        self.zero = value == 0
        self.negative = value & 0x80


class Cpu:
    _memory: Memory
    _flags: Flags
    _a: int = 0
    _x: int = 0
    _y: int = 0
    _s: int = 0
    _pc: int = 0
    _handlers: list

    def __init__(self, memory: Memory):
        self._flags = Flags()
        self._memory = memory
        self._pc = memory.read_word(0xfffc)
        _LOGGER.info("CPU starting at %04x", self._pc)
        self._handlers = 256 * [self._unknown]
        self._handlers[0xa9] = self._lda_imm
        self._handlers[0x8d] = self._sta_abs
        self._handlers[0x78] = self._sei
        self._handlers[0xd8] = self._cld

    def _unknown(self, opcode: int):
        raise RuntimeError(f"Bad opcode {opcode:2x}")

    def _read_pc(self):
        result = self._memory.read_byte(self._pc)
        yield
        self._pc += 1
        return result

    def _read_pc_addr(self):
        low_addr = yield from self._read_pc()
        high_addr = yield from self._read_pc()
        return low_addr + 256 * high_addr

    def _setzn(self, value: int):
        self._flags.setzn(value)
        return value & 0xff

    def _lda_imm(self, _: int):
        imm = yield from self._read_pc()
        self._a = self._setzn(imm)
        _LOGGER.info("a = %02x", self._a)
        yield

    def _sta_abs(self, _: int):
        addr = yield from self._read_pc_addr()
        self._memory.write_byte(addr, self._a)
        _LOGGER.info("Storing A: %04x = %02x", addr, self._a)
        yield

    def _sei(self, _: int):
        self._flags.irq_disable = True  # really this lags a cycle...
        yield  # Really does another read of next?

    def _cld(self, _: int):
        self._flags.decimal = False
        yield  # Really does another read of next?

    def run(self):
        while True:
            opcode = self._memory.read_byte(self._pc)
            _LOGGER.info("%04x: read opcode %02x", self._pc, opcode)
            self._pc += 1
            yield
            yield from self._handlers[opcode](opcode)


class Clock:
    _devices: List[Iterator]

    def __init__(self, devices: List[Generator]):
        self._devices = [iter(device) for device in devices]

    def tick(self):
        for device in self._devices:
            next(device)


def main():
    memory = Memory()
    memory.load_os(load_rom('os.rom'))
    cpu = Cpu(memory)
    clock = Clock([cpu.run()])
    for cycle in range(10000):
        _LOGGER.info("Tick %d", cycle)
        clock.tick()


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)-4s %(name)-10s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    main()

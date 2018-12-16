"""
Created on 6 Apr 2016

@author: npetroni@volexity.com
"""

import struct
from typing import Optional, Tuple

from volatility.framework import exceptions, interfaces, validity
from volatility.framework.layers import segmented


class LimeFormatException(exceptions.LayerException):
    """Thrown when an error occurs with the underlying Lime file format"""


class LimeLayer(segmented.SegmentedLayer):
    """A Lime format TranslationLayer. Lime is generally used to store
    physical memory images where there are large holes in the physical
    address space"""

    priority = 21

    MAGIC = 0x4c694d45
    VERSION = 1

    # Magic[4], Version[4], Start[8], End[8], Reserved[8]
    # XXX move this to a custom SymbolSpace?
    _header_struct = struct.Struct('<IIQQQ')

    def __init__(self,
                 context: interfaces.context.ContextInterface,
                 config_path: str,
                 name: str) -> None:
        super().__init__(context, config_path, name)

        # We must run this on creation in order to get the right min/maxaddr in case scanning is our first action
        self._load_segments()

    def _load_segments(self) -> None:
        base_layer = self._context.memory[self._base_layer]
        base_maxaddr = base_layer.maximum_address
        maxaddr = 0
        offset = 0
        header_size = self._header_struct.size
        segments = []

        while offset < base_maxaddr:
            start, end = self._check_header(base_layer, offset)

            if start < maxaddr or end < start:
                raise LimeFormatException(
                    "bad start/end 0x{:x}/0x{:x} at file offset 0x{:x}".format(start, end, offset))

            segment_length = end - start + 1
            segments.append((start, offset + header_size, segment_length))
            maxaddr = end
            offset = offset + header_size + segment_length

        if len(segments) == 0:
            raise LimeFormatException("No LiME segments defined in {}".format(self._base_layer))

        self._segments = segments

    @classmethod
    def _check_header(cls,
                      base_layer: interfaces.layers.DataLayerInterface,
                      offset: int = 0) -> Tuple[int, int]:
        try:
            header_data = base_layer.read(offset, cls._header_struct.size)
        except exceptions.InvalidAddressException:
            raise LimeFormatException("Offset 0x{:0x} does not exist within the base layer".format(offset))
        (magic, version, start, end, reserved) = cls._header_struct.unpack(header_data)
        if magic != cls.MAGIC:
            raise LimeFormatException("bad magic 0x{:x} at file offset 0x{:x}".format(magic, offset))
        if version != cls.VERSION:
            raise LimeFormatException("unexpected version {:d} at file offset 0x{:x}".format(version, offset))
        return start, end


class LimeStacker(interfaces.automagic.StackerLayerInterface):
    stack_order = 10

    @classmethod
    def stack(cls,
              context: interfaces.context.ContextInterface,
              layer_name: str,
              progress_callback: validity.ProgressCallback = None) \
            -> Optional[interfaces.layers.DataLayerInterface]:
        try:
            LimeLayer._check_header(context.memory[layer_name])
        except LimeFormatException:
            return None
        new_name = context.memory.free_layer_name("LimeLayer")
        context.config[interfaces.configuration.path_join(new_name, "base_layer")] = layer_name
        return LimeLayer(context, new_name, new_name)

"""Read NDEF Text records from NFC Forum Type 2 tags (NTAG/Ultralight)."""


def decode_text_records(message):
    texts, offset, first = [], 0, True
    while offset < len(message):
        def take(size):
            nonlocal offset
            if offset + size > len(message):
                raise ValueError('Truncated NDEF record')
            value = message[offset:offset + size]
            offset += size
            return value

        header, type_length = take(2)
        if bool(header & 0x80) != first or header & 0x20:
            raise ValueError('Invalid or chunked NDEF message')
        first = False
        length = int.from_bytes(take(1 if header & 0x10 else 4), 'big')
        id_length = take(1)[0] if header & 0x08 else 0
        record_type = take(type_length)
        take(id_length)
        payload = take(length)
        if header & 7 == 1 and record_type == b'T':
            if not payload or payload[0] & 0x40:
                raise ValueError('Invalid NDEF Text record')
            language_length = payload[0] & 0x3f
            if len(payload) < 1 + language_length:
                raise ValueError('Truncated NDEF language code')
            payload[1:1 + language_length].decode('ascii')
            text = payload[1 + language_length:]
            encoding = 'utf-8'
            if payload[0] & 0x80:
                encoding = 'utf-16' if text.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-16-be'
            texts.append(text.decode(encoding))
        if header & 0x40:
            if offset != len(message):
                raise ValueError('Data after final NDEF record')
            return texts
    if message:
        raise ValueError('Missing final NDEF record')
    return texts


def read_text_records(reader, cancelled=lambda: False):
    def page(number):
        if cancelled():
            raise RuntimeError('NFC read cancelled')
        data = reader.ntag2xx_read_block(number)
        if data is None or len(data) != 4:
            raise ValueError(f'Cannot read NFC page {number}')
        return bytes(data)

    cc = page(3)
    if cc[0] != 0xe1 or cc[1] >> 4 != 1 or cc[3] >> 4:
        raise ValueError('Tag is not a readable NDEF Type 2 tag')
    capacity = cc[2] * 8
    if not 0 < capacity <= 1008:
        raise ValueError('Unsupported Type 2 tag memory size')
    data = bytearray()
    offset = 0

    def take(size):
        nonlocal offset
        if offset + size > capacity:
            raise ValueError('NDEF data exceeds tag capacity')
        while len(data) < offset + size:
            data.extend(page(4 + len(data) // 4))
        result = bytes(data[offset:offset + size])
        offset += size
        return result

    while offset < capacity:
        kind = take(1)[0]
        if kind == 0xfe:
            return []
        if kind == 0:
            continue
        length = take(1)[0]
        if length == 0xff:
            length = int.from_bytes(take(2), 'big')
        payload = take(length)
        if kind == 3:
            return decode_text_records(payload)
        if kind in (1, 2):
            if len(payload) != 3:
                raise ValueError('Invalid memory-control TLV')
            start = (payload[0] >> 4) * (1 << (payload[2] & 0x0f)) + (payload[0] & 0x0f)
            size = payload[1] or 256
            if kind == 1:
                size = (size + 7) // 8
            if start < 16 + capacity and start + size > 16:
                raise ValueError('Reserved memory inside NDEF data is not supported')
    return []

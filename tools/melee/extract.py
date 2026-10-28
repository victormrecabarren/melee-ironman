"""Extract the preview fighters, stage, revival platform and common effects from a local GALE01 disc or zipped disc."""
import argparse
import contextlib
import json
import hashlib
from pathlib import Path
import struct
import zipfile


@contextlib.contextmanager
def disc_stream(source):
    if source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as archive:
            discs = [x for x in archive.infolist() if x.filename.lower().endswith(('.iso', '.gcm'))]
            if len(discs) != 1:
                raise ValueError('Expected exactly one ISO/GCM inside the ZIP')
            with archive.open(discs[0]) as stream:
                yield stream, discs[0].file_size
    else:
        with source.open('rb') as stream:
            yield stream, source.stat().st_size


def extract(source, output):
    wanted = {f'Pl{code}{suffix}.dat' for code in ('Dr', 'Fe') for suffix in ('', 'Nr', 'AJ')}
    wanted.update({'GrNLa.dat', 'PlCo.dat', 'EfCoData.dat', 'IfAll.dat', 'IfAll.usd'})
    wanted.update({'audio/us/'+name for name in ['main.ssm','emblem.ssm','drmario.ssm','nr_name.ssm','smash2.sem']})
    with disc_stream(source) as (stream, disc_size):
        header = stream.read(0x440)
        if len(header) != 0x440 or header[:6] != b'GALE01' or struct.unpack_from('>I', header, 0x1c)[0] != 0xc2339f3d:
            raise ValueError('Expected a US Melee GameCube disc (GALE01)')
        offset, length = struct.unpack_from('>II', header, 0x424)
        if offset + length > disc_size or length > 16 * 1024 * 1024:
            raise ValueError('Invalid disc filesystem table')
        stream.seek(offset)
        table = stream.read(length)
        count = struct.unpack_from('>I', table, 8)[0]
        if count * 12 > len(table):
            raise ValueError('Invalid filesystem entry count')
        strings = table[count * 12:]
        entries = []
        directories = []
        for i in range(1, count):
            flags, offset, length = struct.unpack_from('>III', table, i * 12)
            while directories and i >= directories[-1][1]: directories.pop()
            name_offset = flags & 0xffffff
            name = strings[name_offset:strings.index(0, name_offset)].decode('ascii')
            full_name = '/'.join([part[0] for part in directories]+[name])
            if flags >> 24:
                directories.append((name,length));continue
            if full_name in wanted:
                if offset + length > disc_size:
                    raise ValueError(f'Invalid bounds for {name}')
                entries.append((offset, length, full_name))
        if {name for _, _, name in entries} != wanted:
            raise ValueError('The disc is missing required character data')
        output.mkdir(parents=True, exist_ok=True)
        report = {'discId': 'GALE01', 'revision': header[7], 'files': {}}
        for offset, length, name in sorted(entries):
            stream.seek(offset)
            data = stream.read(length)
            if len(data) != length:
                raise ValueError(f'Truncated data for {name}')
            (output / Path(name).name).write_bytes(data)
            report['files'][Path(name).name] = {'discPath': name, 'bytes': length, 'sha256': hashlib.sha256(data).hexdigest()}
        (output / 'extraction.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'Extracted {len(entries)} files to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.source, args.output)

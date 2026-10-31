#!/usr/bin/env python3
"""Normalize a source tar.gz without changing member contents or modes."""

import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile


def normalized_bytes(source: Path) -> bytes:
    output = io.BytesIO()
    with tarfile.open(source, "r:gz") as original:
        members = original.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate archive member names")
        with gzip.GzipFile(filename="", mode="wb", fileobj=output,
                           compresslevel=9, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w",
                              format=tarfile.PAX_FORMAT) as archive:
                for member in sorted(members, key=lambda item: item.name):
                    if not (member.isfile() or member.isdir() or member.issym()):
                        raise ValueError(f"unsupported member type: {member.name}")
                    payload = original.extractfile(member) if member.isfile() else None
                    member.uid = member.gid = 0
                    member.uname = member.gname = ""
                    member.mtime = 0
                    member.pax_headers = {}
                    try:
                        archive.addfile(member, payload)
                    finally:
                        if payload is not None:
                            payload.close()
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("use a separate output path, then review and replace the source")
    data = normalized_bytes(args.source)
    with args.output.open("xb") as output:
        output.write(data)
    print(f"{hashlib.sha256(data).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()

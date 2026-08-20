#!/usr/bin/env python3
"""生成保留中文文件名且不带Finder扩展属性的ZIP。"""

import sys
import zipfile
from pathlib import Path


def make_zip(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            archive_name = Path(source.name) / path.relative_to(source)
            bundle.write(path, archive_name.as_posix())


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("用法：make_zip.py <来源目录> <目标ZIP>")
    make_zip(Path(sys.argv[1]), Path(sys.argv[2]))

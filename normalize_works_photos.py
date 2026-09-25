#!/usr/bin/env python3
"""Разовая нормализация works_photos: JPEG ≤1280px / ≤400 КБ.
Бэкап рядом: works_photos.bak-<ts>/
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

# обрезанные файлы с десктопа — спасаем частичным декодом
ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "works_photos")
MAX_SIDE = 1280
MAX_BYTES = 400 * 1024
TS = time.strftime("%Y%m%d-%H%M%S")


def needs_shrink(p: Path) -> bool:
    if p.stat().st_size > MAX_BYTES:
        return True
    try:
        with Image.open(p) as im:
            return max(im.size) > MAX_SIDE
    except Exception:
        return True  # битый — перекодируем


def shrink(p: Path) -> None:
    with Image.open(p) as im:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            im.draft("RGB", (MAX_SIDE, MAX_SIDE))
        except Exception:
            pass
        try:
            im.load()
        except Exception:
            # частичный декод после draft
            pass
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.mode == "RGBA":
            im = im.convert("RGB")
        buf_q = 80
        tmp = p.with_suffix(p.suffix + ".tmpnorm")
        im.save(tmp, format="JPEG", quality=buf_q, optimize=True)
        if tmp.stat().st_size > MAX_BYTES:
            if max(im.size) > 1024:
                im.thumbnail((1024, 1024))
            im.save(tmp, format="JPEG", quality=65, optimize=True)
    final = p.with_suffix(".jpg")
    if final != p and p.exists():
        p.unlink()
    os.replace(tmp, final)


def main() -> int:
    if not ROOT.is_dir():
        print("no dir", ROOT)
        return 1
    files = [p for p in ROOT.rglob("*") if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    to_fix = [p for p in files if needs_shrink(p)]
    print(f"total={len(files)} need_shrink={len(to_fix)}")
    if not to_fix:
        return 0
    bak = ROOT.with_name(f"{ROOT.name}.bak-{TS}")
    # бэкап только тех, что правим (и дерево)
    for p in to_fix:
        rel = p.relative_to(ROOT)
        dest = bak / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    print("backup ->", bak)
    ok = fail = 0
    for p in to_fix:
        try:
            shrink(p)
            ok += 1
            print("OK", p)
        except Exception as e:
            fail += 1
            print("FAIL", p, e)
    print(f"done ok={ok} fail={fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())

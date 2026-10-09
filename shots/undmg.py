"""纯 python 解 Apple UDIF dmg → raw 磁盘镜像, 再 carve PNG/PSD。

无 7z/dmg2img/sudo 环境的替代: koly 尾部头 → plist blkx 表 → mish 块
表 (zlib/raw/zero) → 拼回原始镜像; 不解析文件系统, 直接按魔数抠 PNG。
"""
import base64
import plistlib
import struct
import sys
import zlib
from pathlib import Path

DMG = Path.home() / "shotlab" / "bezel17.dmg"
RAW = Path.home() / "shotlab" / "bezel17.raw"

data = DMG.read_bytes()

# ---- koly trailer (末 512 字节) ----
koly = data[-512:]
assert koly[:4] == b"koly", "不是 UDIF dmg"
xml_off, xml_len = struct.unpack_from(">QQ", koly, 216)
fork_off, fork_len = struct.unpack_from(">QQ", koly, 24)
print(f"xml @{xml_off}+{xml_len}, data fork @{fork_off}+{fork_len}")

plist = plistlib.loads(data[xml_off:xml_off + xml_len])
blocks = []          # (sector_no, sector_count, type, comp_off, comp_len)
for part in plist["resource-fork"]["blkx"]:
    mish = part["Data"] if isinstance(part["Data"], bytes) \
        else base64.b64decode(part["Data"])     # plistlib 已解 <data> 为 bytes
    assert mish[:4] == b"mish", f"blkx 头异常: {mish[:8]!r}"
    n_ent = struct.unpack_from(">I", mish, 200)[0]
    for i in range(n_ent):
        e = 204 + i * 40
        etype, _cmt, sec, cnt, coff, clen = struct.unpack_from(">IIQQQQ", mish, e)
        if etype in (0x7FFFFFFE, 0xFFFFFFFF):    # comment / terminator
            continue
        if cnt:
            blocks.append((sec, cnt, etype, coff, clen))
total_sectors = max(s + c for s, c, *_ in blocks)
print(f"{len(blocks)} 块, 镜像 {total_sectors * 512 / 1e9:.2f} GB")

out = bytearray(total_sectors * 512)
for sec, cnt, etype, coff, clen in sorted(blocks):
    dst = sec * 512
    if etype == 0x00000002:             # ignore (保留零)
        continue
    if etype in (0x00000000, 0x7FFFFFF8, 0x7FFFFFF9, 0x7FFFFFFA):
        continue                        # zero / 0xFF 填充, 默认已是
    raw = data[fork_off + coff:fork_off + coff + clen]
    if etype == 0x80000005:
        raw = zlib.decompress(raw)
    elif etype != 0x00000001:
        print(f"  ! 未知块类型 {etype:#x}, 跳过")
        continue
    out[dst:dst + len(raw)] = raw
print("解压完成", flush=True)
RAW.write_bytes(out)
print(f"written {RAW} ({len(out)/1e9:.2f} GB)")

# ---- carve PNG: 扫魔数, IHDR 宽高, 顺着 chunk 链到 IEND ----
PNG = b"\x89PNG\r\n\x1a\n"
pos = 0
found = []
while True:
    p = out.find(PNG, pos)
    if p < 0:
        break
    pos = p + 1
    try:
        w, h = struct.unpack_from(">II", out, p + 16)
        q = p + 8
        while q < len(out) - 8:
            ln, typ = struct.unpack_from(">I4s", out, q)
            q += 12 + ln
            if typ == b"IEND":
                if 500 < w < 6000 and 500 < h < 12000 and w / h > 0.3:
                    found.append((p, q - p, w, h))
                break
    except struct.error:
        continue
print(f"PNG 候选 {len(found)} 张")
outdir = Path.home() / "shotlab" / "bezel-png"
outdir.mkdir(exist_ok=True)
for i, (p, ln, w, h) in enumerate(found):
    (outdir / f"{i:03d}_{w}x{h}.png").write_bytes(bytes(out[p:p + ln]))
    print(f"  {i:03d}: {w}x{h} @{p} ({ln/1e6:.1f}MB)")

# PSD 也记个数 (魔数 8BPS)
psd = out.count(b"8BPS")
print(f"PSD 魔数出现 {psd} 次")

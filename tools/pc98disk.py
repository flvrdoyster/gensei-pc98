#!/usr/bin/env python3
"""PC-98 디스크 이미지 생성/편집 도구 (FDI, HDI, IMG)"""

import argparse
import os
import shutil
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 디스크 지오메트리 프리셋
# ---------------------------------------------------------------------------

GEOMETRY = {
    "fdi-2hd": {
        "label": "2HD 1.23 MB",
        "cylinders": 77,
        "heads": 2,
        "spt": 8,           # sectors per track
        "sector_size": 1024,
        "fat_type": 12,
        "media_byte": 0xFE,
        "root_entries": 192,
        "spc": 1,           # sectors per cluster
        "spf": 2,           # sectors per FAT
        "reserved": 1,
        "num_fats": 2,
        "fmt": "fdi",
    },
    "hdi-20mb": {
        "label": "HDD 20 MB",
        "cylinders": 615,
        "heads": 4,
        "spt": 17,
        "sector_size": 512,
        "fat_type": 16,
        "media_byte": 0xF8,
        "root_entries": 512,
        "spc": 4,
        "spf": 40,
        "reserved": 1,
        "num_fats": 2,
        "fmt": "hdi",
    },
    "hdi-40mb": {
        "label": "HDD 40 MB",
        "cylinders": 615,
        "heads": 8,
        "spt": 17,
        "sector_size": 512,
        "fat_type": 16,
        "media_byte": 0xF8,
        "root_entries": 512,
        "spc": 8,
        "spf": 40,
        "reserved": 1,
        "num_fats": 2,
        "fmt": "hdi",
    },
    "hdi-80mb": {
        "label": "HDD 80 MB",
        "cylinders": 1024,
        "heads": 8,
        "spt": 17,
        "sector_size": 512,
        "fat_type": 16,
        "media_byte": 0xF8,
        "root_entries": 512,
        "spc": 16,
        "spf": 40,
        "reserved": 1,
        "num_fats": 2,
        "fmt": "hdi",
    },
}

# ---------------------------------------------------------------------------
# 헤더 생성
# ---------------------------------------------------------------------------

FDI_HEADER_SIZE = 4096
HDI_HEADER_SIZE = 4096


def make_fdi_header(geo):
    data_size = geo["cylinders"] * geo["heads"] * geo["spt"] * geo["sector_size"]
    hdr = bytearray(FDI_HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x00, 0)
    struct.pack_into("<I", hdr, 0x04, 0x90)  # fdd type: 2HD
    struct.pack_into("<I", hdr, 0x08, FDI_HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x0C, data_size)
    struct.pack_into("<I", hdr, 0x10, geo["sector_size"])
    struct.pack_into("<I", hdr, 0x14, geo["spt"])
    struct.pack_into("<I", hdr, 0x18, geo["heads"])
    struct.pack_into("<I", hdr, 0x1C, geo["cylinders"])
    return bytes(hdr)


def make_hdi_header(geo):
    data_size = geo["cylinders"] * geo["heads"] * geo["spt"] * geo["sector_size"]
    hdr = bytearray(HDI_HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x00, 0)
    struct.pack_into("<I", hdr, 0x04, 0)  # data type
    struct.pack_into("<I", hdr, 0x08, HDI_HEADER_SIZE)
    struct.pack_into("<I", hdr, 0x0C, data_size)
    struct.pack_into("<I", hdr, 0x10, geo["sector_size"])
    struct.pack_into("<I", hdr, 0x14, geo["spt"])
    struct.pack_into("<I", hdr, 0x18, geo["heads"])
    struct.pack_into("<I", hdr, 0x1C, geo["cylinders"])
    return bytes(hdr)


# ---------------------------------------------------------------------------
# FAT 포맷
# ---------------------------------------------------------------------------

def make_bpb(geo):
    """BIOS Parameter Block (BPB) — 섹터 0에 기록"""
    total_sectors = geo["cylinders"] * geo["heads"] * geo["spt"]
    ss = geo["sector_size"]
    bpb = bytearray(ss)

    # JMP + NOP
    bpb[0] = 0xEB
    bpb[1] = 0x3C
    bpb[2] = 0x90
    # OEM
    bpb[3:11] = b"PC98DISK"
    # bytes per sector
    struct.pack_into("<H", bpb, 11, ss)
    # sectors per cluster
    bpb[13] = geo["spc"]
    # reserved sectors
    struct.pack_into("<H", bpb, 14, geo["reserved"])
    # number of FATs
    bpb[16] = geo["num_fats"]
    # root entries
    struct.pack_into("<H", bpb, 17, geo["root_entries"])
    # total sectors (16-bit)
    if total_sectors < 0x10000:
        struct.pack_into("<H", bpb, 19, total_sectors)
    else:
        struct.pack_into("<H", bpb, 19, 0)
        struct.pack_into("<I", bpb, 32, total_sectors)
    # media byte
    bpb[21] = geo["media_byte"]
    # sectors per FAT
    struct.pack_into("<H", bpb, 22, geo["spf"])
    # sectors per track
    struct.pack_into("<H", bpb, 24, geo["spt"])
    # heads
    struct.pack_into("<H", bpb, 26, geo["heads"])

    # boot signature
    bpb[ss - 2] = 0x55
    bpb[ss - 1] = 0xAA

    return bytes(bpb)


def make_fat(geo):
    """초기 FAT 테이블"""
    ss = geo["sector_size"]
    fat = bytearray(geo["spf"] * ss)
    if geo["fat_type"] == 12:
        fat[0] = geo["media_byte"]
        fat[1] = 0xFF
        fat[2] = 0xFF
    else:
        fat[0] = geo["media_byte"]
        fat[1] = 0xFF
        fat[2] = 0xFF
        fat[3] = 0xFF
    return bytes(fat)


def format_disk_data(geo):
    """FAT 포맷된 디스크 데이터 (헤더 제외) 생성"""
    ss = geo["sector_size"]
    total_sectors = geo["cylinders"] * geo["heads"] * geo["spt"]

    data = bytearray(total_sectors * ss)

    # 섹터 0: BPB
    bpb = make_bpb(geo)
    data[0:ss] = bpb

    # FAT 영역
    fat = make_fat(geo)
    offset = geo["reserved"] * ss
    for i in range(geo["num_fats"]):
        data[offset:offset + len(fat)] = fat
        offset += len(fat)

    # 루트 디렉토리 영역은 0으로 초기화된 상태 그대로
    return bytes(data)


# ---------------------------------------------------------------------------
# 디스크 이미지 읽기/쓰기 래퍼
# ---------------------------------------------------------------------------

class DiskImage:
    """FDI/HDI/IMG 디스크 이미지 래퍼"""

    def __init__(self, path, geo=None):
        self.path = Path(path)
        self.geo = geo
        self.header = b""
        self.data = b""

    @classmethod
    def create(cls, path, geo_name):
        geo = GEOMETRY[geo_name]
        img = cls(path, geo)

        if geo["fmt"] == "fdi":
            img.header = make_fdi_header(geo)
        elif geo["fmt"] == "hdi":
            img.header = make_hdi_header(geo)
        else:
            img.header = b""

        img.data = bytearray(format_disk_data(geo))
        return img

    @classmethod
    def open(cls, path):
        p = Path(path)
        raw = p.read_bytes()
        ext = p.suffix.lower()

        img = cls(path)

        if ext == ".fdi":
            if _has_fdi_header(raw):
                img.header = raw[:FDI_HEADER_SIZE]
                img.data = bytearray(raw[FDI_HEADER_SIZE:])
                ss = struct.unpack_from("<I", img.header, 0x10)[0]
                spt = struct.unpack_from("<I", img.header, 0x14)[0]
                heads = struct.unpack_from("<I", img.header, 0x18)[0]
                cyls = struct.unpack_from("<I", img.header, 0x1C)[0]
            else:
                img.header = b""
                img.data = bytearray(raw)
                ss, spt, heads, cyls = _guess_img_geometry(len(raw))
        elif ext == ".hdi":
            hdr_size = struct.unpack_from("<I", raw, 0x08)[0]
            if 256 <= hdr_size <= 65536 and hdr_size < len(raw):
                img.header = raw[:hdr_size]
                img.data = bytearray(raw[hdr_size:])
                ss = struct.unpack_from("<I", img.header, 0x10)[0]
                spt = struct.unpack_from("<I", img.header, 0x14)[0]
                heads = struct.unpack_from("<I", img.header, 0x18)[0]
                cyls = struct.unpack_from("<I", img.header, 0x1C)[0]
            else:
                img.header = b""
                img.data = bytearray(raw)
                ss, spt, heads, cyls = _guess_img_geometry(len(raw))
        else:
            img.header = b""
            img.data = bytearray(raw)
            ss, spt, heads, cyls = _guess_img_geometry(len(raw))

        img.geo = _rebuild_geo(img.data, ss, spt, heads, cyls)
        if not img.geo["is_fat"]:
            # 섹터0이 BPB가 아니면 PC-98 파티션 HDD일 수 있음 → 파티션 테이블 스캔
            part = _find_pc98_partition(img.data, ss, spt, heads)
            if part is not None:
                img.geo = _rebuild_geo(img.data, ss, spt, heads, cyls, base=part)
        return img

    def save(self, path=None):
        p = Path(path) if path else self.path
        p.write_bytes(self.header + bytes(self.data))

    # -- FAT 접근 헬퍼 --

    def _fat_offset(self):
        return self.geo.get("part_base", 0) + self.geo["reserved"] * self.geo["sector_size"]

    def _root_dir_offset(self):
        ss = self.geo["sector_size"]
        return (self.geo.get("part_base", 0)
                + (self.geo["reserved"] + self.geo["num_fats"] * self.geo["spf"]) * ss)

    def _root_dir_sectors(self):
        ss = self.geo["sector_size"]
        return (self.geo["root_entries"] * 32 + ss - 1) // ss

    def _data_area_offset(self):
        return self._root_dir_offset() + self._root_dir_sectors() * self.geo["sector_size"]

    def _cluster_to_offset(self, cluster):
        return self._data_area_offset() + (cluster - 2) * self.geo["spc"] * self.geo["sector_size"]

    def _cluster_size(self):
        return self.geo["spc"] * self.geo["sector_size"]

    # -- FAT 테이블 읽기/쓰기 --

    def _read_fat_entry(self, cluster):
        fat_off = self._fat_offset()
        if self.geo["fat_type"] == 12:
            byte_off = fat_off + (cluster * 3) // 2
            pair = struct.unpack_from("<H", self.data, byte_off)[0]
            if cluster % 2 == 0:
                return pair & 0x0FFF
            else:
                return (pair >> 4) & 0x0FFF
        else:
            byte_off = fat_off + cluster * 2
            return struct.unpack_from("<H", self.data, byte_off)[0]

    def _write_fat_entry(self, cluster, value):
        ss = self.geo["sector_size"]
        base = self.geo.get("part_base", 0)
        for fat_i in range(self.geo["num_fats"]):
            fat_off = base + (self.geo["reserved"] + fat_i * self.geo["spf"]) * ss
            if self.geo["fat_type"] == 12:
                byte_off = fat_off + (cluster * 3) // 2
                pair = struct.unpack_from("<H", self.data, byte_off)[0]
                if cluster % 2 == 0:
                    pair = (pair & 0xF000) | (value & 0x0FFF)
                else:
                    pair = (pair & 0x000F) | ((value & 0x0FFF) << 4)
                struct.pack_into("<H", self.data, byte_off, pair)
            else:
                byte_off = fat_off + cluster * 2
                struct.pack_into("<H", self.data, byte_off, value & 0xFFFF)

    def _find_free_cluster(self):
        if self.geo.get("total_clusters"):
            # 파티션/BPB 기준 클러스터 수 (파티션 HDI에서 디스크 전체 크기로 넘치는 것 방지)
            max_cluster = self.geo["total_clusters"] + 2
        else:
            total = len(self.data) // self.geo["sector_size"]
            data_sectors = total - (self._data_area_offset() // self.geo["sector_size"])
            max_cluster = data_sectors // self.geo["spc"] + 2
        for c in range(2, max_cluster):
            if self._read_fat_entry(c) == 0:
                return c
        return None

    def _end_marker(self):
        return 0x0FFF if self.geo["fat_type"] == 12 else 0xFFFF

    def _free_cluster_chain(self, start):
        c = start
        while True:
            nxt = self._read_fat_entry(c)
            self._write_fat_entry(c, 0)
            if nxt >= self._end_marker() - 7 or nxt < 2:
                break
            c = nxt

    # -- 디렉토리 엔트리 --

    def _parse_dir_entry(self, offset):
        raw = self.data[offset:offset + 32]
        if raw[0] == 0x00 or raw[0] == 0xE5:
            return None
        if raw[11] & 0x08:  # 볼륨 라벨
            return None
        if raw[11] & 0x0F == 0x0F:  # LFN
            return None

        name = raw[0:8].decode("ascii", errors="replace").rstrip()
        ext = raw[8:11].decode("ascii", errors="replace").rstrip()
        attr = raw[11]
        cluster = struct.unpack_from("<H", raw, 26)[0]
        size = struct.unpack_from("<I", raw, 28)[0]

        filename = f"{name}.{ext}" if ext else name
        return {
            "filename": filename,
            "name83": (name, ext),
            "attr": attr,
            "cluster": cluster,
            "size": size,
            "offset": offset,
            "is_dir": bool(attr & 0x10),
        }

    def _list_root(self):
        entries = []
        root_off = self._root_dir_offset()
        for i in range(self.geo["root_entries"]):
            off = root_off + i * 32
            entry = self._parse_dir_entry(off)
            if entry:
                entries.append(entry)
            elif self.data[off] == 0x00:
                break
        return entries

    def _find_entry(self, filename):
        name83 = _to_8_3(filename)
        for entry in self._list_root():
            if entry["name83"] == name83:
                return entry
        return None

    def _find_free_dir_slot(self):
        root_off = self._root_dir_offset()
        for i in range(self.geo["root_entries"]):
            off = root_off + i * 32
            if self.data[off] in (0x00, 0xE5):
                return off
        return None

    def _write_dir_entry(self, offset, name83, cluster, size, attr=0x20):
        entry = bytearray(32)
        n, e = name83
        entry[0:8] = n.encode("ascii").ljust(8)[:8]
        entry[8:11] = e.encode("ascii").ljust(3)[:3]
        entry[11] = attr
        struct.pack_into("<H", entry, 26, cluster)
        struct.pack_into("<I", entry, 28, size)
        self.data[offset:offset + 32] = entry

    # -- 공개 API --

    def is_fat(self):
        return self.geo.get("is_fat", True)

    def list_files(self):
        if not self.is_fat():
            return []
        return self._list_root()

    def read_file(self, filename):
        entry = self._find_entry(filename)
        if not entry:
            raise FileNotFoundError(f"{filename} not found in image")

        result = bytearray()
        cluster = entry["cluster"]
        remaining = entry["size"]
        cs = self._cluster_size()

        while remaining > 0 and cluster >= 2:
            off = self._cluster_to_offset(cluster)
            chunk = min(cs, remaining)
            result.extend(self.data[off:off + chunk])
            remaining -= chunk
            nxt = self._read_fat_entry(cluster)
            if nxt >= self._end_marker() - 7:
                break
            cluster = nxt

        return bytes(result)

    def add_file(self, filename, file_data):
        name83 = _to_8_3(filename)

        existing = self._find_entry(filename)
        if existing:
            self._free_cluster_chain(existing["cluster"])
            dir_offset = existing["offset"]
        else:
            dir_offset = self._find_free_dir_slot()
            if dir_offset is None:
                raise RuntimeError("root directory full")

        if len(file_data) == 0:
            self._write_dir_entry(dir_offset, name83, 0, 0)
            return

        cs = self._cluster_size()
        clusters_needed = (len(file_data) + cs - 1) // cs
        chain = []
        for _ in range(clusters_needed):
            c = self._find_free_cluster()
            if c is None:
                for prev in chain:
                    self._write_fat_entry(prev, 0)
                raise RuntimeError("disk full")
            chain.append(c)
            self._write_fat_entry(c, self._end_marker())

        for i in range(len(chain) - 1):
            self._write_fat_entry(chain[i], chain[i + 1])

        offset = 0
        for c in chain:
            dest = self._cluster_to_offset(c)
            chunk = file_data[offset:offset + cs]
            self.data[dest:dest + len(chunk)] = chunk
            if len(chunk) < cs:
                self.data[dest + len(chunk):dest + cs] = b"\x00" * (cs - len(chunk))
            offset += cs

        self._write_dir_entry(dir_offset, name83, chain[0], len(file_data))

    def delete_file(self, filename):
        entry = self._find_entry(filename)
        if not entry:
            raise FileNotFoundError(f"{filename} not found in image")
        self._free_cluster_chain(entry["cluster"])
        self.data[entry["offset"]] = 0xE5


# ---------------------------------------------------------------------------
# 인서터 공용 헬퍼
# ---------------------------------------------------------------------------

def prepare_output_copy(base_path, out_dir, out_name=None):
    """베이스 이미지(base_path)를 out_dir 아래로 복사하고 그 경로를 반환.

    각 타이틀 인서터가 '배포용 베이스 이미지는 건드리지 않고 build/ 에 복사본을
    만들어 패치'하는 동일한 절차를 반복 구현하던 것을 공통화한 것.
    """
    if not os.path.exists(base_path):
        raise FileNotFoundError(f'{base_path} 없음')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name or os.path.basename(base_path))
    shutil.copy(base_path, out_path)
    return out_path


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _to_8_3(filename):
    """파일명을 8.3 포맷 (name, ext) 튜플로 변환"""
    filename = filename.upper().strip()
    if "." in filename:
        parts = filename.rsplit(".", 1)
        name = parts[0][:8]
        ext = parts[1][:3]
    else:
        name = filename[:8]
        ext = ""
    return (name, ext)


def _has_fdi_header(raw):
    """Anex86 FDI 헤더가 있는지 판별"""
    if len(raw) <= FDI_HEADER_SIZE:
        return False
    hdr_size = struct.unpack_from("<I", raw, 0x08)[0]
    if hdr_size != FDI_HEADER_SIZE:
        return False
    ss = struct.unpack_from("<I", raw, 0x10)[0]
    if ss not in (128, 256, 512, 1024):
        return False
    spt = struct.unpack_from("<I", raw, 0x14)[0]
    if not (1 <= spt <= 64):
        return False
    return True


def _guess_img_geometry(size):
    """raw IMG 파일의 지오메트리 추측"""
    if size == 1261568:  # 1232 * 1024
        return 1024, 8, 2, 77
    if size == 655360:  # 640K
        return 512, 8, 2, 80
    return 512, 17, 4, max(size // (512 * 17 * 4), 1)


def _has_valid_bpb(data):
    """섹터 0이 유효한 BPB인지 판별"""
    if len(data) < 64:
        return False
    bpb_ss = struct.unpack_from("<H", data, 11)[0]
    if bpb_ss not in (128, 256, 512, 1024, 2048, 4096):
        return False
    spc = data[13]
    if spc == 0 or (spc & (spc - 1)) != 0:  # power of 2
        return False
    num_fats = data[16]
    if num_fats not in (1, 2):
        return False
    media = data[21]
    if media < 0xF0:
        return False
    return True


def _rebuild_geo(data, ss, spt, heads, cyls, base=0):
    """BPB에서 FAT 파라미터를 읽어 geo dict 재구성 (BPB가 없으면 non-FAT).

    base: 파일시스템(BPB) 시작 바이트 오프셋. 0이면 종전과 동일(플로피/통짜 이미지),
          PC-98 파티션 HDI는 파티션 시작 오프셋. FAT 파라미터는 디스크 CHS가 아니라
          해당 BPB 자체 값(섹터 크기·총 섹터 수)으로 계산한다.
    """
    bpb = data[base:base + 64]
    if not _has_valid_bpb(bpb):
        return {
            "cylinders": cyls,
            "heads": heads,
            "spt": spt,
            "sector_size": ss,
            "fat_type": 0,
            "media_byte": 0,
            "root_entries": 0,
            "spc": 1,
            "spf": 0,
            "reserved": 0,
            "num_fats": 0,
            "fmt": "raw",
            "is_fat": False,
            "part_base": 0,
        }

    bpb_ss = struct.unpack_from("<H", bpb, 11)[0]
    spc = bpb[13]
    reserved = struct.unpack_from("<H", bpb, 14)[0]
    num_fats = bpb[16]
    root_entries = struct.unpack_from("<H", bpb, 17)[0]
    media_byte = bpb[21]
    spf = struct.unpack_from("<H", bpb, 22)[0]

    # 총 섹터: BPB 16-bit 값 우선(파티션이면 파티션 크기), 0이면 디스크 CHS에서 환산
    total_sectors = struct.unpack_from("<H", bpb, 19)[0]
    if total_sectors == 0:
        total_sectors = (cyls * heads * spt * ss) // bpb_ss
    root_sectors = (root_entries * 32 + bpb_ss - 1) // bpb_ss
    data_sectors = total_sectors - reserved - num_fats * spf - root_sectors
    total_clusters = data_sectors // spc
    fat_type = 12 if total_clusters < 4085 else 16

    return {
        "cylinders": cyls,
        "heads": heads,
        "spt": spt,
        "sector_size": bpb_ss,
        "fat_type": fat_type,
        "media_byte": media_byte,
        "root_entries": root_entries,
        "spc": spc,
        "spf": spf,
        "reserved": reserved,
        "num_fats": num_fats,
        "fmt": "raw",
        "is_fat": True,
        "part_base": base,
        "total_clusters": total_clusters,
    }


def _find_pc98_partition(data, ss, spt, heads):
    """PC-98 HDD 파티션 테이블에서 첫 FAT 파티션의 시작 바이트 오프셋을 찾는다.

    레이아웃: 섹터0 = IPL(부트시그 55AA), 섹터1 = 파티션 테이블(32B 엔트리).
    엔트리의 시작 CHS(ssect@8, shead@9, scyl@10-11)를 디스크 지오메트리(ss/spt/heads)로
    바이트 오프셋으로 환산하고, 거기에 유효한 BPB가 있는 엔트리만 인정한다.
    없으면 None.
    """
    if len(data) < ss * 2 or ss < 256:
        return None
    if data[ss - 2:ss] != b"\x55\xaa":
        return None
    for i in range(16):
        off = ss + i * 32
        e = data[off:off + 32]
        if len(e) < 32 or e[0] == 0:
            continue
        ssect, shead = e[8], e[9]
        scyl = struct.unpack_from("<H", e, 10)[0]
        part = ((scyl * heads + shead) * spt + ssect) * ss
        if part < len(data) and _has_valid_bpb(data[part:part + 64]):
            return part
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_create(args):
    geo_name = args.type
    if geo_name not in GEOMETRY:
        print(f"알 수 없는 타입: {geo_name}")
        print(f"사용 가능: {', '.join(GEOMETRY.keys())}")
        return 1

    img = DiskImage.create(args.output, geo_name)
    img.save()
    total = len(img.data)
    print(f"생성: {args.output} ({GEOMETRY[geo_name]['label']}, {total:,} bytes)")
    return 0


def cmd_ls(args):
    img = DiskImage.open(args.image)
    if not img.is_fat():
        total = len(img.data)
        geo = img.geo
        print(f"non-FAT 이미지: {total:,} bytes ({geo['cylinders']}C/{geo['heads']}H/{geo['spt']}S, {geo['sector_size']}B/sec)")
        return 0
    entries = img.list_files()
    if not entries:
        print("(빈 디스크)")
        return 0

    print(f"{'파일명':<16} {'크기':>10}  {'클러스터':>8}")
    print("-" * 38)
    total_size = 0
    for e in entries:
        flag = "<DIR>" if e["is_dir"] else ""
        size_str = flag if flag else f"{e['size']:,}"
        print(f"{e['filename']:<16} {size_str:>10}  {e['cluster']:>8}")
        total_size += e["size"]
    print("-" * 38)
    print(f"{len(entries)} files, {total_size:,} bytes")
    return 0


def cmd_add(args):
    img = DiskImage.open(args.image)
    src = Path(args.src)
    dest_name = args.dest or src.name

    file_data = src.read_bytes()
    action = "교체" if img._find_entry(dest_name) else "추가"
    img.add_file(dest_name, file_data)
    img.save()
    print(f"{action}: {dest_name} ({len(file_data):,} bytes)")
    return 0


def cmd_get(args):
    img = DiskImage.open(args.image)
    data = img.read_file(args.filename)
    out = Path(args.output) if args.output else Path(args.filename)
    out.write_bytes(data)
    print(f"추출: {args.filename} → {out} ({len(data):,} bytes)")
    return 0


def cmd_delete(args):
    img = DiskImage.open(args.image)
    img.delete_file(args.filename)
    img.save()
    print(f"삭제: {args.filename}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="PC-98 디스크 이미지 도구 (FDI/HDI/IMG)",
    )
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="빈 디스크 이미지 생성")
    p_create.add_argument("output", help="출력 파일 경로")
    p_create.add_argument(
        "-t", "--type", required=True,
        choices=list(GEOMETRY.keys()),
        help="디스크 타입",
    )

    # ls
    p_ls = sub.add_parser("ls", help="파일 목록")
    p_ls.add_argument("image", help="디스크 이미지 경로")

    # add
    p_add = sub.add_parser("add", help="파일 추가/교체")
    p_add.add_argument("image", help="디스크 이미지 경로")
    p_add.add_argument("src", help="추가할 로컬 파일")
    p_add.add_argument("dest", nargs="?", help="이미지 내 파일명 (생략 시 원본명)")

    # get
    p_get = sub.add_parser("get", help="파일 추출")
    p_get.add_argument("image", help="디스크 이미지 경로")
    p_get.add_argument("filename", help="추출할 파일명")
    p_get.add_argument("output", nargs="?", help="저장 경로")

    # delete
    p_del = sub.add_parser("delete", help="파일 삭제")
    p_del.add_argument("image", help="디스크 이미지 경로")
    p_del.add_argument("filename", help="삭제할 파일명")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    handlers = {
        "create": cmd_create,
        "ls": cmd_ls,
        "add": cmd_add,
        "get": cmd_get,
        "delete": cmd_delete,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)

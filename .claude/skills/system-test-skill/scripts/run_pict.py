#!/usr/bin/env python3
"""PICT(https://github.com/microsoft/pict) 래퍼. pict 실행파일 탐색 후 모델을 실행한다.

사용: run_pict.py model.txt [--order N] [-o out.tsv] [--seed seed.txt] [--install]
탐색 순서: PICT_PATH 환경변수 -> PATH -> <skill>/bin/pict(.exe)
--install: 실행파일이 없을 때 gh CLI로 GitHub 릴리스(Windows: pict.exe)를 <skill>/bin 에 다운로드.
"""
import argparse, os, shutil, subprocess, sys
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
EXE = "pict.exe" if os.name == "nt" else "pict"


def find_pict():
    env = os.environ.get("PICT_PATH")
    if env and Path(env).is_file():
        return env
    found = shutil.which("pict")
    if found:
        return found
    local = BIN_DIR / EXE
    return str(local) if local.is_file() else None


def install():
    if os.name != "nt":
        sys.exit("Linux/macOS는 소스 빌드 필요: git clone https://github.com/microsoft/pict && cd pict && make "
                 "(결과 pict 를 PATH 또는 PICT_PATH 에 지정)")
    if not shutil.which("gh"):
        sys.exit("gh CLI 없음. https://github.com/microsoft/pict/releases 에서 pict.exe 를 받아 "
                 f"{BIN_DIR} 에 두거나 PICT_PATH 를 지정하세요.")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gh", "release", "download", "-R", "microsoft/pict", "-p", "pict.exe",
                    "-D", str(BIN_DIR), "--clobber"], check=True)


def ascii_copy(p):
    """PICT(Windows)는 비ASCII 경로를 열지 못함 -> ASCII 경로의 임시 복사본을 사용."""
    import tempfile
    p = str(Path(p).resolve())
    if p.isascii():
        return p
    for base in (BIN_DIR.parent, Path(os.environ.get("PUBLIC", "C:/Users/Public")), Path("C:/Windows/Temp")):
        if str(base).isascii() and base.is_dir():
            fd, tmp = tempfile.mkstemp(suffix=".txt", dir=base)
            os.close(fd)
            shutil.copyfile(p, tmp)
            TMP_FILES.append(tmp)
            return tmp
    sys.exit(f"비ASCII 경로를 PICT에 전달할 수 없습니다. ASCII 경로로 복사하세요: {p}")


TMP_FILES = []


def main():
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?")
    ap.add_argument("--order", type=int, default=2, help="조합 강도 (기본 2=pairwise)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--seed")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()

    exe = find_pict()
    if not exe and a.install:
        install()
        exe = find_pict()
    if not exe:
        sys.exit("pict 실행파일을 찾지 못했습니다. --install 로 다운로드하거나 PICT_PATH 를 지정하세요.")
    if not a.model:
        sys.exit("모델 파일 경로 필요")

    cmd = [exe, ascii_copy(a.model), f"/o:{a.order}"]
    if a.seed:
        cmd.append(f"/e:{ascii_copy(a.seed)}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    for t in TMP_FILES:
        os.remove(t)
    if r.returncode != 0:
        sys.exit(f"PICT 오류({r.returncode}): {r.stderr or r.stdout}")
    if a.out:
        Path(a.out).write_text(r.stdout, encoding="utf-8")
        print(f"{len(r.stdout.splitlines()) - 1} rows -> {a.out}")
    else:
        print(r.stdout)


if __name__ == "__main__":
    main()

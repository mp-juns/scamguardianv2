"""
AI Hub CLI(`aihubshell`) 래퍼 — 데이터셋 목록 조회 + 라벨링 파일만 골라 다운로드.

사용법:
    # 1. 사용자 단계 (수동, 사이트에서)
    #    - aihub.or.kr 회원가입 + API key 발급
    #    - 원하는 데이터셋 활용 신청 + 승인 대기

    # 2. 환경변수 설정
    export AIHUB_API_KEY="..."
    export AIHUB_SHELL="./data/aihubshell"   # 기본값

    # 3. 전체 목록 + 키워드 필터
    python scripts/aihub.py list-datasets --grep 콜센터,상담,민원

    # 4. 특정 dataset 의 파일 트리
    python scripts/aihub.py list-files 98

    # 5. 라벨링 파일만 다운로드 (원천 음성 skip, 자동 재시도)
    python scripts/aihub.py download-labels 98 --out data/aihub
    python scripts/aihub.py download-labels 100 --out data/aihub --domain 금융

본 모듈은 aihubshell 의 stdout 을 파싱해서 filekey 만 뽑아 -mode d 로 재호출한다.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_SHELL = os.getenv("AIHUB_SHELL", "./data/aihubshell")
LABELING_HINTS = ("라벨링", "label", "Label", "LABEL", "TL_", "VL_")
RAW_HINTS = ("원천", "wav", "WAV", "TS_", "VS_")
# size + filekey 패턴 (line 끝쪽). name 은 별도로 추출.
FILE_TAIL_RE = re.compile(r"\|\s*(?P<size>\S+(?:\s*[KMG]?B|))\s*\|\s*(?P<key>\d+)\s*$")
# 트리 가지 위치(├ 또는 └) — depth 측정용
BRANCH_RE = re.compile(r"[├└]")


def _shell() -> str:
    shell = os.getenv("AIHUB_SHELL", DEFAULT_SHELL)
    path = Path(shell)
    if not path.exists():
        sys.exit(f"aihubshell 을 찾을 수 없습니다: {shell}\nAIHUB_SHELL 환경변수로 경로 지정")
    if not os.access(path, os.X_OK):
        sys.exit(f"실행 권한 없음: {shell}\n  chmod +x {shell}")
    return str(path)


def _api_key() -> str:
    key = os.getenv("AIHUB_API_KEY")
    if not key:
        sys.exit("AIHUB_API_KEY 환경변수가 비어 있습니다.")
    return key


def _run(args: list[str], capture: bool = True) -> str:
    cmd = [_shell(), "-aihubapikey", _api_key(), *args]
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout + result.stderr
    subprocess.run(cmd, check=False)
    return ""


def list_datasets(grep_terms: list[str] | None = None) -> None:
    out = _run(["-mode", "l"])
    started = False
    for line in out.splitlines():
        if "DataSet 목록" in line:
            started = True
            continue
        if not started:
            continue
        if not re.match(r"\s*\d+,\s*\S", line):
            continue
        if grep_terms:
            if not any(term in line for term in grep_terms):
                continue
        print(line.rstrip())


def list_files(dataset_key: str) -> None:
    out = _run(["-mode", "l", "-datasetkey", str(dataset_key)])
    print(out)


def _classify_path(parts: list[str]) -> str:
    joined = "/".join(parts)
    if any(h in joined for h in LABELING_HINTS):
        return "label"
    if any(h in joined for h in RAW_HINTS):
        return "raw"
    return "unknown"


def _parse_files(text: str, want: str = "label", domain: str | None = None) -> list[tuple[str, str, str]]:
    """aihubshell -mode l 트리 출력에서 (kind, filekey, full_path) 를 뽑는다.

    들여쓰기로 부모 폴더 stack 을 유지해 라벨링/원천 구분.
    """
    items: list[tuple[str, str, str]] = []
    stack: list[tuple[int, str]] = []  # (depth, folder_name)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        m_branch = BRANCH_RE.search(line)
        if not m_branch:
            continue
        depth = m_branch.start()
        # 가지 문자 직후의 텍스트가 노드 이름 (또는 파일 라인의 시작)
        after = line[m_branch.end():].lstrip("─").lstrip()
        # 파일 라인이면 끝에 size + filekey 가 붙는다
        m_tail = FILE_TAIL_RE.search(after)
        if m_tail:
            name = after[: m_tail.start()].strip()
            filekey = m_tail.group("key")
            # 현재 라인보다 얕은 폴더만 부모로 취급
            parents = [n for d, n in stack if d < depth]
            kind = _classify_path([*parents, name])
            full = "/".join([*parents, name])
            if want != "any" and kind != want:
                continue
            if domain and domain not in full:
                continue
            items.append((kind, filekey, full))
        else:
            # 폴더 노드 — stack 갱신
            name = after.strip()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, name))
    return items


def _filekeys_for(dataset_key: str, domain: str | None) -> list[tuple[str, str]]:
    out = _run(["-mode", "l", "-datasetkey", str(dataset_key)])
    if not out.strip():
        sys.exit(f"dataset {dataset_key}: 목록 응답 없음. 활용 신청·승인 상태 확인 필요.")
    items = _parse_files(out, want="label", domain=domain)
    if not items:
        sys.exit(
            f"dataset {dataset_key}: 라벨링 파일을 찾지 못했습니다."
            + (f" (domain={domain!r} 필터)" if domain else "")
        )
    return [(k, name) for _kind, k, name in items]


def download_labels(
    dataset_key: str,
    out_dir: Path,
    domain: str | None = None,
    chunk: int = 30,
    retries: int = 3,
    sleep_between: float = 1.0,
    dry_run: bool = False,
) -> None:
    items = _filekeys_for(dataset_key, domain)
    print(f"[dataset {dataset_key}] 라벨링 파일 {len(items)}개 매칭")
    for _, name in items:
        print(f"  · {name}")
    if dry_run:
        print(f"\n[dry-run] 실제 다운로드 안 함 — out={out_dir}")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    cwd_before = os.getcwd()
    os.chdir(out_dir)
    try:
        for i in range(0, len(items), chunk):
            batch = items[i : i + chunk]
            keys = ",".join(k for k, _ in batch)
            label = ", ".join(name.split("/")[-1] for _, name in batch[:3])
            if len(batch) > 3:
                label += f" 외 {len(batch) - 3}개"
            print(f"\n[batch {i // chunk + 1}] {len(batch)}개 → {label}")
            for attempt in range(1, retries + 1):
                rc = subprocess.run(
                    [
                        _shell(),
                        "-aihubapikey",
                        _api_key(),
                        "-mode",
                        "d",
                        "-datasetkey",
                        str(dataset_key),
                        "-filekey",
                        keys,
                    ],
                    check=False,
                ).returncode
                if rc == 0:
                    break
                print(f"  attempt {attempt}/{retries} 실패 (rc={rc}). 재시도...", file=sys.stderr)
                time.sleep(sleep_between * attempt)
            else:
                sys.exit(f"  batch {i // chunk + 1} 다운로드 실패 — 중단")
            time.sleep(sleep_between)
    finally:
        os.chdir(cwd_before)
    print(f"\n[done] dataset {dataset_key} 라벨링 다운로드 완료 → {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="aihub", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-datasets", help="전체 데이터셋 목록 (grep 필터 가능)")
    p_list.add_argument("--grep", help="콤마로 구분된 키워드 — 하나라도 매치하면 출력", default=None)

    p_files = sub.add_parser("list-files", help="특정 dataset 의 파일 트리")
    p_files.add_argument("dataset_key", help="datasetkey (예: 98)")

    p_dl = sub.add_parser("download-labels", help="라벨링 파일만 다운로드 (원천 skip)")
    p_dl.add_argument("dataset_key")
    p_dl.add_argument("--out", default="data/aihub", help="저장 루트 (기본: data/aihub)")
    p_dl.add_argument("--domain", default=None, help="파일 경로에 포함되어야 하는 부분 문자열 (예: 금융)")
    p_dl.add_argument("--chunk", type=int, default=30, help="배치 크기 (기본 30)")
    p_dl.add_argument("--retries", type=int, default=3)
    p_dl.add_argument("--dry-run", action="store_true", help="다운로드 안 하고 매칭 파일만 출력")

    args = parser.parse_args()

    if args.cmd == "list-datasets":
        terms = [t.strip() for t in (args.grep or "").split(",") if t.strip()]
        list_datasets(terms or None)
    elif args.cmd == "list-files":
        list_files(args.dataset_key)
    elif args.cmd == "download-labels":
        out_dir = Path(args.out) / f"dataset_{args.dataset_key}"
        download_labels(
            args.dataset_key,
            out_dir,
            domain=args.domain,
            chunk=args.chunk,
            retries=args.retries,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()

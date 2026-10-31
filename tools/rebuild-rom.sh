#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/.." && pwd)

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Build an EFI PCI option ROM from a vendor GOP and optional helper EFI images.

With no input overrides this reproduces the verified MS-01 S1260 8086:46a6
artifact using only files tracked under roms/vendor/.

Usage:
  tools/rebuild-rom.sh [options]

Identity and output:
  --model NAME                    Label used in logs and the default filename.
  --vendor-id HEX                 Four-digit PCI vendor ID (default: 8086).
  --device-id HEX                 Four-digit PCI device ID (default: 46a6).
  --output FILE                   Result path. Defaults below firmware-extraction/.
  --expected-output-sha256 HASH   If supplied, require this result ROM hash.
  --force                         Atomically replace an existing output file.

Vendor GOP input, method 1 - extract from a BIOS archive:
  --bios-archive FILE
  --bios-archive-sha256 HASH
  --bios-member PATH              Firmware image path inside the archive.
  --bios-image-sha256 HASH
  --uefi-extract-archive FILE     ZIP containing a UEFIExtract executable.
  --uefi-extract-sha256 HASH
  --uefi-extract-member PATH      Executable path in that ZIP.
  --uefi-extract-bin FILE         Use an already installed UEFIExtract instead.
  --gop-container-guid GUID
  --gop-subtype-guid GUID
  --gop-path-glob GLOB            Override the complete find(1) path glob.
  --gop-sha256 HASH

Vendor GOP input, method 2 - use an already extracted EFI payload:
  --gop-efi FILE                  Skips BIOS and UEFIExtract processing.
  --gop-sha256 HASH

Helper EFI images:
  --reference-rom FILE            PCI ROM from which helpers are extracted.
  --reference-rom-sha256 HASH
  --helper-image-indexes LIST     Comma-separated image indexes (default: 1,2).
  --helper-efi FILE               Direct helper EFI; repeat in payload order.
  --helper-sha256s LIST           Comma-separated hashes matching the helpers.
  --no-helpers                    Package the GOP without helper images.

EfiRom utility:
  --edk2-source-archive FILE      Archive containing BaseTools and MdePkg/Include.
  --edk2-source-sha256 HASH
  --efi-rom-bin FILE              Use an already compiled EfiRom utility.

Execution:
  --work-dir DIR                  Use and retain this build directory.
  --keep-work-dir                 Retain an automatically created build directory.
  --verify-only                   Validate parameters and input hashes, then exit.
  --print-config                  Print resolved configuration, then exit.
  -h, --help

Every --*-sha256 option is optional. If supplied, a mismatch is fatal. If
omitted, the build prints the observed hash so it can be reviewed and pinned.
Changing an input path or helper selection clears its verified-profile checksum
unless the corresponding --*-sha256 option is also supplied. The no-argument
validated MS-01 profile remains pinned by default.
EOF
}

sha256_file() {
  local file=$1
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print $1}'
  else
    die "neither shasum nor sha256sum is available"
  fi
}

verify_file() {
  local label=$1
  local file=$2
  local expected=$3
  local actual
  [[ -f "$file" ]] || die "$label not found: $file"
  actual=$(sha256_file "$file")
  if [[ -n "$expected" ]]; then
    [[ "$actual" == "$expected" ]] ||
      die "$label SHA-256 mismatch: expected $expected, got $actual"
    printf 'verified %-24s %s\n' "$label" "$actual"
  else
    printf 'observed %-24s %s  %s\n' "$label" "$actual" "$file"
  fi
}

normalize_pci_id() {
  local value=${1#0x}
  value=${value#0X}
  [[ "$value" =~ ^[[:xdigit:]]{4}$ ]] ||
    die "PCI ID must contain exactly four hexadecimal digits: $1"
  printf '%s' "$value" | tr '[:upper:]' '[:lower:]'
}

normalize_sha256() {
  local value=$1
  [[ "$value" =~ ^[[:xdigit:]]{64}$ ]] || die "invalid SHA-256: $value"
  printf '%s' "$value" | tr '[:upper:]' '[:lower:]'
}

MODEL=ms01-s1260
VENDOR_ID=8086
DEVICE_ID=46a6

BIOS_ARCHIVE="$REPO_ROOT/roms/vendor/MS-01-AHWSA-V1.27_4_28_V2.zip"
BIOS_ARCHIVE_SHA256=cf6710534f1de22f0f94515a0bd91b6d95d78e002a060cbe85dfd788865e57d6
BIOS_MEMBER=AHWSA.1.27_250403/AHWSA.bin
BIOS_IMAGE_SHA256=dfd4ec78bfe81c33f236b222ffc9acdde648fe39641d0aa0df7e1796e0951201

UEFIEXTRACT_ARCHIVE="$REPO_ROOT/roms/vendor/tools/UEFIExtract_NE_A75_universal_mac.zip"
UEFIEXTRACT_SHA256=8cbdd6d42193d6fb8a0c37dc860b4695c618f923b8ecfff9c0042fbdd80aaa80
UEFIEXTRACT_MEMBER=UEFIExtract
UEFIEXTRACT_BIN=

GOP_EFI=
GOP_CONTAINER_GUID=A0327FE0-1FDA-4E5B-905D-B510C45A61D0
GOP_SUBTYPE_GUID=380B6B4F-1454-41F2-A6D3-61D1333E8CB4
GOP_PATH_GLOB=
GOP_PATH_GLOB_EXPLICIT=0
GOP_SHA256=8ed7384baa07772525d007d62cdaba18254e5e6d9e081323c808f0f061e7eb8f

REFERENCE_ROM="$REPO_ROOT/roms/vendor/reference/pc-12-13-14-q10.rom"
REFERENCE_ROM_SHA256=b73c83330a80a18e1780e64e964f1e7b477904316f5362667c648737f40da92f
HELPER_IMAGE_INDEXES=1,2
HELPER_SHA256S=784fc780ef0606da5978e5a9f51b4dcee0cbf241cf9e50f09ead9b0c8885f21f,3a0ce851696dfdc3980f4f105b4701f3146308bf1f8e02b8dd4f97b82b436ed7
NO_HELPERS=0
DIRECT_HELPERS=()

EDK2_SOURCE_ARCHIVE="$REPO_ROOT/roms/vendor/sources/edk2-cc9a0425-EfiRom-source.tar.gz"
EDK2_SOURCE_SHA256=d0a3c823a646133690633982af41285723b266943980e84a61a25296e661046e
EFI_ROM_BIN=

OUTPUT=
EXPECTED_OUTPUT_SHA256=954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9
OUTPUT_PROFILE_CHANGED=0
EXPECTED_OUTPUT_SHA256_EXPLICIT=0
BIOS_ARCHIVE_CHANGED=0
BIOS_ARCHIVE_SHA256_EXPLICIT=0
BIOS_MEMBER_CHANGED=0
BIOS_IMAGE_SHA256_EXPLICIT=0
UEFIEXTRACT_ARCHIVE_CHANGED=0
UEFIEXTRACT_SHA256_EXPLICIT=0
GOP_INPUT_CHANGED=0
GOP_SHA256_EXPLICIT=0
REFERENCE_ROM_CHANGED=0
REFERENCE_ROM_SHA256_EXPLICIT=0
HELPER_SELECTION_CHANGED=0
HELPER_SHA256S_EXPLICIT=0
EDK2_SOURCE_CHANGED=0
EDK2_SOURCE_SHA256_EXPLICIT=0
WORK_DIR=
KEEP_WORK_DIR=0
FORCE=0
VERIFY_ONLY=0
PRINT_CONFIG=0

while (($#)); do
  case "$1" in
    --model)
      (($# >= 2)) || die "$1 requires a value"
      MODEL=$2
      shift 2
      ;;
    --vendor-id)
      (($# >= 2)) || die "$1 requires a value"
      VENDOR_ID=$2
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --device-id)
      (($# >= 2)) || die "$1 requires a value"
      DEVICE_ID=$2
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --output)
      (($# >= 2)) || die "$1 requires a value"
      OUTPUT=$2
      shift 2
      ;;
    --expected-output-sha256)
      (($# >= 2)) || die "$1 requires a value"
      EXPECTED_OUTPUT_SHA256=$2
      EXPECTED_OUTPUT_SHA256_EXPLICIT=1
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --bios-archive)
      (($# >= 2)) || die "$1 requires a value"
      BIOS_ARCHIVE=$2
      BIOS_ARCHIVE_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --bios-archive-sha256)
      (($# >= 2)) || die "$1 requires a value"
      BIOS_ARCHIVE_SHA256=$2
      BIOS_ARCHIVE_SHA256_EXPLICIT=1
      shift 2
      ;;
    --bios-member)
      (($# >= 2)) || die "$1 requires a value"
      BIOS_MEMBER=$2
      BIOS_MEMBER_CHANGED=1
      GOP_INPUT_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --bios-image-sha256)
      (($# >= 2)) || die "$1 requires a value"
      BIOS_IMAGE_SHA256=$2
      BIOS_IMAGE_SHA256_EXPLICIT=1
      shift 2
      ;;
    --uefi-extract-archive)
      (($# >= 2)) || die "$1 requires a value"
      UEFIEXTRACT_ARCHIVE=$2
      UEFIEXTRACT_ARCHIVE_CHANGED=1
      shift 2
      ;;
    --uefi-extract-sha256)
      (($# >= 2)) || die "$1 requires a value"
      UEFIEXTRACT_SHA256=$2
      UEFIEXTRACT_SHA256_EXPLICIT=1
      shift 2
      ;;
    --uefi-extract-member)
      (($# >= 2)) || die "$1 requires a value"
      UEFIEXTRACT_MEMBER=$2
      shift 2
      ;;
    --uefi-extract-bin)
      (($# >= 2)) || die "$1 requires a value"
      UEFIEXTRACT_BIN=$2
      shift 2
      ;;
    --gop-container-guid)
      (($# >= 2)) || die "$1 requires a value"
      GOP_CONTAINER_GUID=$2
      GOP_INPUT_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --gop-subtype-guid)
      (($# >= 2)) || die "$1 requires a value"
      GOP_SUBTYPE_GUID=$2
      GOP_INPUT_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --gop-path-glob)
      (($# >= 2)) || die "$1 requires a value"
      GOP_PATH_GLOB=$2
      GOP_PATH_GLOB_EXPLICIT=1
      GOP_INPUT_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --gop-efi)
      (($# >= 2)) || die "$1 requires a value"
      GOP_EFI=$2
      GOP_INPUT_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --gop-sha256)
      (($# >= 2)) || die "$1 requires a value"
      GOP_SHA256=$2
      GOP_SHA256_EXPLICIT=1
      shift 2
      ;;
    --reference-rom)
      (($# >= 2)) || die "$1 requires a value"
      REFERENCE_ROM=$2
      REFERENCE_ROM_CHANGED=1
      HELPER_SELECTION_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --reference-rom-sha256)
      (($# >= 2)) || die "$1 requires a value"
      REFERENCE_ROM_SHA256=$2
      REFERENCE_ROM_SHA256_EXPLICIT=1
      shift 2
      ;;
    --helper-image-indexes)
      (($# >= 2)) || die "$1 requires a value"
      HELPER_IMAGE_INDEXES=$2
      DIRECT_HELPERS=()
      NO_HELPERS=0
      HELPER_SELECTION_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --helper-efi)
      (($# >= 2)) || die "$1 requires a value"
      DIRECT_HELPERS+=("$2")
      NO_HELPERS=0
      HELPER_SELECTION_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift 2
      ;;
    --helper-sha256s)
      (($# >= 2)) || die "$1 requires a value"
      HELPER_SHA256S=$2
      HELPER_SHA256S_EXPLICIT=1
      shift 2
      ;;
    --no-helpers)
      NO_HELPERS=1
      DIRECT_HELPERS=()
      HELPER_IMAGE_INDEXES=
      HELPER_SHA256S=
      HELPER_SELECTION_CHANGED=1
      OUTPUT_PROFILE_CHANGED=1
      shift
      ;;
    --edk2-source-archive)
      (($# >= 2)) || die "$1 requires a value"
      EDK2_SOURCE_ARCHIVE=$2
      EDK2_SOURCE_CHANGED=1
      shift 2
      ;;
    --edk2-source-sha256)
      (($# >= 2)) || die "$1 requires a value"
      EDK2_SOURCE_SHA256=$2
      EDK2_SOURCE_SHA256_EXPLICIT=1
      shift 2
      ;;
    --efi-rom-bin)
      (($# >= 2)) || die "$1 requires a value"
      EFI_ROM_BIN=$2
      shift 2
      ;;
    --work-dir)
      (($# >= 2)) || die "$1 requires a value"
      WORK_DIR=$2
      KEEP_WORK_DIR=1
      shift 2
      ;;
    --keep-work-dir)
      KEEP_WORK_DIR=1
      shift
      ;;
    --verify-only)
      VERIFY_ONLY=1
      shift
      ;;
    --print-config)
      PRINT_CONFIG=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if ((BIOS_ARCHIVE_CHANGED)) && ((BIOS_ARCHIVE_SHA256_EXPLICIT == 0)); then
  BIOS_ARCHIVE_SHA256=
fi
if ((BIOS_MEMBER_CHANGED)) && ((BIOS_IMAGE_SHA256_EXPLICIT == 0)); then
  BIOS_IMAGE_SHA256=
fi
if ((UEFIEXTRACT_ARCHIVE_CHANGED)) && ((UEFIEXTRACT_SHA256_EXPLICIT == 0)); then
  UEFIEXTRACT_SHA256=
fi
if ((GOP_INPUT_CHANGED)) && ((GOP_SHA256_EXPLICIT == 0)); then
  GOP_SHA256=
fi
if ((REFERENCE_ROM_CHANGED)) && ((REFERENCE_ROM_SHA256_EXPLICIT == 0)); then
  REFERENCE_ROM_SHA256=
fi
if ((HELPER_SELECTION_CHANGED)) && ((HELPER_SHA256S_EXPLICIT == 0)); then
  HELPER_SHA256S=
fi
if ((EDK2_SOURCE_CHANGED)) && ((EDK2_SOURCE_SHA256_EXPLICIT == 0)); then
  EDK2_SOURCE_SHA256=
fi

[[ "$MODEL" =~ ^[A-Za-z0-9._-]+$ ]] ||
  die "model may contain only letters, digits, dot, underscore, and hyphen"
VENDOR_ID=$(normalize_pci_id "$VENDOR_ID")
DEVICE_ID=$(normalize_pci_id "$DEVICE_ID")

for sha_name in \
  BIOS_ARCHIVE_SHA256 BIOS_IMAGE_SHA256 UEFIEXTRACT_SHA256 GOP_SHA256 \
  REFERENCE_ROM_SHA256 EDK2_SOURCE_SHA256 EXPECTED_OUTPUT_SHA256; do
  sha_value=${!sha_name}
  if [[ -n "$sha_value" ]]; then
    printf -v "$sha_name" '%s' "$(normalize_sha256 "$sha_value")"
  fi
done

if ((OUTPUT_PROFILE_CHANGED)) && ((EXPECTED_OUTPUT_SHA256_EXPLICIT == 0)); then
  EXPECTED_OUTPUT_SHA256=
fi

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="$REPO_ROOT/firmware-extraction/output/${MODEL}-${VENDOR_ID}-${DEVICE_ID}.rom"
fi

if [[ -e "$OUTPUT" ]] && ((FORCE == 0)) && ((VERIFY_ONLY == 0)) &&
  ((PRINT_CONFIG == 0)); then
  die "output already exists (use --force to replace): $OUTPUT"
fi

if ((GOP_PATH_GLOB_EXPLICIT == 0)); then
  GOP_PATH_GLOB="*${GOP_CONTAINER_GUID}/* ${GOP_SUBTYPE_GUID}/body.bin"
fi

if ((PRINT_CONFIG)); then
  cat <<EOF
model=$MODEL
vendor_id=$VENDOR_ID
device_id=$DEVICE_ID
output=$OUTPUT
expected_output_sha256=${EXPECTED_OUTPUT_SHA256:-UNPINNED}
gop_mode=$([[ -n "$GOP_EFI" ]] && printf direct || printf bios-extraction)
gop_efi=${GOP_EFI:-N/A}
bios_archive=$BIOS_ARCHIVE
bios_member=$BIOS_MEMBER
gop_path_glob=$GOP_PATH_GLOB
reference_rom=$REFERENCE_ROM
helper_image_indexes=${HELPER_IMAGE_INDEXES:-N/A}
direct_helper_count=${#DIRECT_HELPERS[@]}
no_helpers=$NO_HELPERS
edk2_source_archive=$EDK2_SOURCE_ARCHIVE
efi_rom_bin=${EFI_ROM_BIN:-BUILD_FROM_SOURCE}
EOF
  exit 0
fi

command -v python3 >/dev/null 2>&1 || die "python3 is required"
[[ -f "$REPO_ROOT/tools/inspect_efi_pci_rom.py" ]] ||
  die "ROM inspector is missing: $REPO_ROOT/tools/inspect_efi_pci_rom.py"

if [[ -n "$GOP_EFI" ]]; then
  verify_file "GOP EFI" "$GOP_EFI" "$GOP_SHA256"
else
  command -v unzip >/dev/null 2>&1 || die "unzip is required"
  verify_file "BIOS archive" "$BIOS_ARCHIVE" "$BIOS_ARCHIVE_SHA256"
  if [[ -n "$UEFIEXTRACT_BIN" ]]; then
    [[ -x "$UEFIEXTRACT_BIN" ]] || die "UEFIExtract is not executable: $UEFIEXTRACT_BIN"
  else
    verify_file "UEFIExtract archive" "$UEFIEXTRACT_ARCHIVE" "$UEFIEXTRACT_SHA256"
  fi
fi

helper_indices=()
helper_hashes=()
if ((NO_HELPERS == 0)); then
  if ((${#DIRECT_HELPERS[@]} == 0)); then
    verify_file "reference ROM" "$REFERENCE_ROM" "$REFERENCE_ROM_SHA256"
    IFS=',' read -r -a helper_indices <<<"$HELPER_IMAGE_INDEXES"
    ((${#helper_indices[@]} > 0)) || die "at least one helper image index is required"
    for index in "${helper_indices[@]}"; do
      [[ "$index" =~ ^[0-9]+$ ]] || die "invalid helper image index: $index"
    done
  fi
  if [[ -n "$HELPER_SHA256S" ]]; then
    IFS=',' read -r -a helper_hashes <<<"$HELPER_SHA256S"
    helper_count=${#DIRECT_HELPERS[@]}
    if ((helper_count == 0)); then
      helper_count=${#helper_indices[@]}
    fi
    ((${#helper_hashes[@]} == helper_count)) ||
      die "helper SHA-256 count does not match helper count"
    for index in "${!helper_hashes[@]}"; do
      helper_hashes[$index]=$(normalize_sha256 "${helper_hashes[$index]}")
    done
  fi
  if ((${#DIRECT_HELPERS[@]} > 0)); then
    for index in "${!DIRECT_HELPERS[@]}"; do
      expected=
      if ((${#helper_hashes[@]} > 0)); then
        expected=${helper_hashes[$index]}
      fi
      verify_file "helper EFI $index" "${DIRECT_HELPERS[$index]}" "$expected"
    done
  fi
fi

if [[ -n "$EFI_ROM_BIN" ]]; then
  [[ -x "$EFI_ROM_BIN" ]] || die "EfiRom is not executable: $EFI_ROM_BIN"
else
  command -v make >/dev/null 2>&1 || die "make is required"
  command -v cc >/dev/null 2>&1 || die "a C compiler named cc is required"
  command -v tar >/dev/null 2>&1 || die "tar is required"
  verify_file "EDK II source" "$EDK2_SOURCE_ARCHIVE" "$EDK2_SOURCE_SHA256"
fi

if ((VERIFY_ONLY)); then
  printf 'Input verification complete for %s (%s:%s).\n' \
    "$MODEL" "$VENDOR_ID" "$DEVICE_ID"
  exit 0
fi

AUTO_WORK_DIR=0
if [[ -z "$WORK_DIR" ]]; then
  WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/igd-rom-rebuild.XXXXXX")
  AUTO_WORK_DIR=1
else
  if [[ -e "$WORK_DIR" ]]; then
    [[ -d "$WORK_DIR" ]] || die "work directory path is not a directory: $WORK_DIR"
    [[ -z "$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] ||
      die "work directory must be empty: $WORK_DIR"
  else
    mkdir -p "$WORK_DIR"
  fi
fi

cleanup() {
  local status=$?
  if ((AUTO_WORK_DIR)) && ((KEEP_WORK_DIR == 0)) && ((status == 0)); then
    rm -rf -- "$WORK_DIR"
  else
    printf 'work_dir=%s\n' "$WORK_DIR" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

mkdir -p \
  "$WORK_DIR/input" \
  "$WORK_DIR/reference" \
  "$WORK_DIR/edk2" \
  "$WORK_DIR/validation"

if [[ -n "$GOP_EFI" ]]; then
  GOP_INPUT=$GOP_EFI
else
  mkdir -p "$WORK_DIR/bios" "$WORK_DIR/uefi-extract"
  unzip -q "$BIOS_ARCHIVE" -d "$WORK_DIR/bios"
  BIOS_BIN="$WORK_DIR/bios/$BIOS_MEMBER"
  verify_file "BIOS image" "$BIOS_BIN" "$BIOS_IMAGE_SHA256"

  if [[ -n "$UEFIEXTRACT_BIN" ]]; then
    UEFIEXTRACT=$UEFIEXTRACT_BIN
  else
    unzip -q "$UEFIEXTRACT_ARCHIVE" -d "$WORK_DIR/uefi-extract"
    UEFIEXTRACT="$WORK_DIR/uefi-extract/$UEFIEXTRACT_MEMBER"
    [[ -x "$UEFIEXTRACT" ]] || die "UEFIExtract not found in archive root"
  fi

  "$UEFIEXTRACT" "$BIOS_BIN" all
  GOP_MATCHES=$(find "$BIOS_BIN.dump" -type f -path "$GOP_PATH_GLOB" -print)
  GOP_COUNT=$(printf '%s\n' "$GOP_MATCHES" | awk 'NF {count++} END {print count+0}')
  ((GOP_COUNT == 1)) ||
    die "GOP path glob must match exactly one file, matched $GOP_COUNT: $GOP_PATH_GLOB"
  GOP_INPUT=$GOP_MATCHES
fi

verify_file "extracted GOP" "$GOP_INPUT" "$GOP_SHA256"
cp "$GOP_INPUT" "$WORK_DIR/input/image-0.efi"
payloads=("$WORK_DIR/input/image-0.efi")

if ((NO_HELPERS == 0)); then
  if ((${#DIRECT_HELPERS[@]} > 0)); then
    for index in "${!DIRECT_HELPERS[@]}"; do
      expected=
      if ((${#helper_hashes[@]} > 0)); then
        expected=${helper_hashes[$index]}
      fi
      verify_file "helper EFI $index" "${DIRECT_HELPERS[$index]}" "$expected"
      destination="$WORK_DIR/input/image-$((index + 1)).efi"
      cp "${DIRECT_HELPERS[$index]}" "$destination"
      payloads+=("$destination")
    done
  else
    python3 "$REPO_ROOT/tools/inspect_efi_pci_rom.py" "$REFERENCE_ROM" \
      --extract-dir "$WORK_DIR/reference"
    for position in "${!helper_indices[@]}"; do
      image_index=${helper_indices[$position]}
      helper="$WORK_DIR/reference/image-${image_index}.efi"
      expected=
      if ((${#helper_hashes[@]} > 0)); then
        expected=${helper_hashes[$position]}
      fi
      verify_file "helper image $image_index" "$helper" "$expected"
      destination="$WORK_DIR/input/image-$((position + 1)).efi"
      cp "$helper" "$destination"
      payloads+=("$destination")
    done
  fi
fi

if [[ -n "$EFI_ROM_BIN" ]]; then
  EFI_ROM=$EFI_ROM_BIN
else
  tar --no-same-owner -xzf "$EDK2_SOURCE_ARCHIVE" -C "$WORK_DIR/edk2"
  make -C "$WORK_DIR/edk2/BaseTools/Source/C" EfiRom
  EFI_ROM="$WORK_DIR/edk2/BaseTools/Source/C/bin/EfiRom"
  [[ -x "$EFI_ROM" ]] || die "EfiRom build did not produce an executable"
fi

BUILT_ROM="$WORK_DIR/result.rom"
SECOND_ROM="$WORK_DIR/result-second.rom"
"$EFI_ROM" -e "${payloads[@]}" \
  -f "0x$VENDOR_ID" -i "0x$DEVICE_ID" -o "$BUILT_ROM"
"$EFI_ROM" -e "${payloads[@]}" \
  -f "0x$VENDOR_ID" -i "0x$DEVICE_ID" -o "$SECOND_ROM"
cmp "$BUILT_ROM" "$SECOND_ROM" || die "repeated EfiRom builds are not identical"

ROM_REPORT=$(python3 "$REPO_ROOT/tools/inspect_efi_pci_rom.py" "$BUILT_ROM" \
  --extract-dir "$WORK_DIR/validation")
printf '%s\n' "$ROM_REPORT"
ROM_IMAGE_COUNT=0
while IFS= read -r line; do
  [[ "$line" == image=* ]] || continue
  [[ "$line" == *"vendor=$VENDOR_ID device=$DEVICE_ID"* ]] ||
    die "unexpected PCIR identity: $line"
  ((ROM_IMAGE_COUNT += 1))
done <<<"$ROM_REPORT"
((ROM_IMAGE_COUNT == ${#payloads[@]})) ||
  die "output contains $ROM_IMAGE_COUNT images; expected ${#payloads[@]}"

for index in "${!payloads[@]}"; do
  cmp "${payloads[$index]}" "$WORK_DIR/validation/image-${index}.efi" ||
    die "packaging changed EFI payload $index"
done

RESULT_SHA256=$(sha256_file "$BUILT_ROM")
if [[ -n "$EXPECTED_OUTPUT_SHA256" ]]; then
  [[ "$RESULT_SHA256" == "$EXPECTED_OUTPUT_SHA256" ]] ||
    die "output SHA-256 mismatch: expected $EXPECTED_OUTPUT_SHA256, got $RESULT_SHA256"
else
  printf 'observed %-24s %s  %s\n' \
    "output ROM" "$RESULT_SHA256" "$BUILT_ROM"
fi

if [[ -e "$OUTPUT" ]] && ((FORCE == 0)); then
  die "output already exists (use --force to replace): $OUTPUT"
fi
mkdir -p "$(dirname -- "$OUTPUT")"
OUTPUT_PART="${OUTPUT}.part.$$"
cp "$BUILT_ROM" "$OUTPUT_PART"
mv -f "$OUTPUT_PART" "$OUTPUT"

printf 'model=%s\n' "$MODEL"
printf 'pci_id=%s:%s\n' "$VENDOR_ID" "$DEVICE_ID"
printf 'output=%s\n' "$OUTPUT"
printf 'sha256=%s\n' "$RESULT_SHA256"

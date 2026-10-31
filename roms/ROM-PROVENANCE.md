# Verified MS-01 S1260 option ROM

## Artifact

```text
file: ms01-adlp-8086-46a6-gop21.0.1066.rom
size: 195072 bytes
sha256: 954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9
PCI ID in all three PCIR headers: 8086:46a6
```

The ROM was used for the verified S1260 physical-HDMI and accelerated-rendering
result described in the repository README. Device-specific experiment logs are
kept outside this public repository.

The S1290 validation used a separately generated `8086:4626` ROM, not
this tracked `8086:46a6` artifact. Its discovery and strict-reproduction builds
were byte-identical at 195,072 bytes with SHA-256
`a08b8f9aa797d9b5622957a4284ef8976a4641c800bf7a33f7dc63b09e18ded2`.
That ROM produced operator-confirmed physical HDMI with the Ubuntu 22.04 Xorg
software-rendered fallback, but it is not tracked or distributed here. Never
mix ROMs between unsupported PCI IDs; rebuild, inspect, and validate an exact
ROM for the live device identity.

The qualified S1390 artifact
`ms01-s1390-8086-a720-6e166a89e84b.rom` is a strict, byte-for-byte reproduction
of a discovery build made from the pinned inputs below with every PCIR image
declaring exact identity `8086:a720`. It is 195,072 bytes with SHA-256
`6e166a89e84b5f20fe41edc68400a5e43cb4b3f7b704c39ea46b9e3cbd3d4538`.
On 2026-09-04, PVE HA started a portable mapped VM on an S1390-class MS-01 with
this ROM, `pc-i440fx-11.0`, and the shared QEMU argument set recorded in the
manifest. With Ubuntu 22.04 HWE kernel `6.8.0-138-generic`, the guest bound
`8086:a720` to `i915`, created a DRM device, and ran Xorg with Mesa Iris direct
rendering (`Accelerated: yes`). The same run produced operator-confirmed
physical HDMI output. The earlier Ubuntu 22.04 kernel
`5.15.0-97-generic` exposed the PCI function but did not bind a driver, so a
guest kernel that supports `8086:a720` is part of this qualified result.

## Components

The ROM contains these EFI images in order:

| Image | Origin | Size | SHA-256 |
|---:|---|---:|---|
| 0 | Intel GOP extracted from official MS-01 BIOS 1.27 | 163840 | `8ed7384baa07772525d007d62cdaba18254e5e6d9e081323c808f0f061e7eb8f` |
| 1 | Reference `IgdAssignmentDxe` | 20928 | `784fc780ef0606da5978e5a9f51b4dcee0cbf241cf9e50f09ead9b0c8885f21f` |
| 2 | Reference `PlatformGopPolicy` | 9472 | `3a0ce851696dfdc3980f4f105b4701f3146308bf1f8e02b8dd4f97b82b436ed7` |

The original MINISFORUM package is tracked at
[`roms/vendor/MS-01-AHWSA-V1.27_4_28_V2.zip`](vendor/MS-01-AHWSA-V1.27_4_28_V2.zip).
It was downloaded from the vendor's
[`MS-01-AHWSA-V1.27_4_28_V2.zip`](https://pc-file.s3.us-west-1.amazonaws.com/ms-01/Bios/MS-01-AHWSA-V1.27_4_28_V2.zip)
URL:

```text
ZIP sha256: cf6710534f1de22f0f94515a0bd91b6d95d78e002a060cbe85dfd788865e57d6
AHWSA.bin sha256: dfd4ec78bfe81c33f236b222ffc9acdde648fe39641d0aa0df7e1796e0951201
GOP version from vendor release notes: 21.0.1066
```

MINISFORUM does not publish a checksum alongside the download. These hashes
identify the files used; they do not independently authenticate the vendor
package.

The two helper drivers were taken from
[`AICodo/intel6-14rom`](https://github.com/AICodo/intel6-14rom) revision
`72c428ce0a8f7af8ee277180190c67d0fe0404ad`; the exact reference ROM is tracked
at `roms/vendor/reference/pc-12-13-14-q10.rom`. The final ROM was packaged with
TianoCore EDK II `EfiRom` from revision
`cc9a0425a21a41b723311801f5dfeb6e07ff9ed9` using vendor `0x8086` and device
`0x46a6` for every image. The minimal source required to rebuild that utility is
tracked at `roms/vendor/sources/edk2-cc9a0425-EfiRom-source.tar.gz`.

## Automated rebuild

[`tools/rebuild-rom.sh`](../tools/rebuild-rom.sh) implements the complete local
pipeline below. With no input overrides it uses the verified MS-01 S1260
profile and writes the result below the ignored `firmware-extraction/output/`
directory:

```bash
tools/rebuild-rom.sh
```

The helper verifies every retained input, extracts the GOP and helper images,
builds `EfiRom`, creates the option ROM twice, requires the two results to be
identical, checks the requested PCI ID in every PCIR header, and compares every
packaged EFI payload with its input. The default build must produce SHA-256
`954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9`.

### Exact command for the validated MS-01 S1260

Run this command from the repository root. It is the fully expanded equivalent
of the no-argument command above:

```bash
tools/rebuild-rom.sh \
  --model ms01-s1260 \
  --vendor-id 8086 \
  --device-id 46a6 \
  --bios-archive roms/vendor/MS-01-AHWSA-V1.27_4_28_V2.zip \
  --bios-archive-sha256 cf6710534f1de22f0f94515a0bd91b6d95d78e002a060cbe85dfd788865e57d6 \
  --bios-member AHWSA.1.27_250403/AHWSA.bin \
  --bios-image-sha256 dfd4ec78bfe81c33f236b222ffc9acdde648fe39641d0aa0df7e1796e0951201 \
  --uefi-extract-archive roms/vendor/tools/UEFIExtract_NE_A75_universal_mac.zip \
  --uefi-extract-sha256 8cbdd6d42193d6fb8a0c37dc860b4695c618f923b8ecfff9c0042fbdd80aaa80 \
  --uefi-extract-member UEFIExtract \
  --gop-container-guid A0327FE0-1FDA-4E5B-905D-B510C45A61D0 \
  --gop-subtype-guid 380B6B4F-1454-41F2-A6D3-61D1333E8CB4 \
  --gop-sha256 8ed7384baa07772525d007d62cdaba18254e5e6d9e081323c808f0f061e7eb8f \
  --reference-rom roms/vendor/reference/pc-12-13-14-q10.rom \
  --reference-rom-sha256 b73c83330a80a18e1780e64e964f1e7b477904316f5362667c648737f40da92f \
  --helper-image-indexes 1,2 \
  --helper-sha256s 784fc780ef0606da5978e5a9f51b4dcee0cbf241cf9e50f09ead9b0c8885f21f,3a0ce851696dfdc3980f4f105b4701f3146308bf1f8e02b8dd4f97b82b436ed7 \
  --edk2-source-archive roms/vendor/sources/edk2-cc9a0425-EfiRom-source.tar.gz \
  --edk2-source-sha256 d0a3c823a646133690633982af41285723b266943980e84a61a25296e661046e \
  --expected-output-sha256 954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9 \
  --output firmware-extraction/output/ms01-s1260-8086-46a6.rom
```

The script refuses to overwrite an existing output file. Add `--force` only
when intentionally replacing a previously generated ROM.

All SHA-256 options are optional command-line constraints. The validated S1260
profile supplies its recorded constraints by default, which is why the command
above is strict. For a changed input, the corresponding profile hash is cleared
unless a replacement `--*-sha256` value is supplied. A supplied hash must match
exactly; an omitted hash does not stop the build and is reported as `observed`.

Use these inspection modes before a custom build:

```bash
tools/rebuild-rom.sh --print-config
tools/rebuild-rom.sh --verify-only
tools/rebuild-rom.sh --help
```

### Parameters for another model

The binary-affecting parameters are grouped as follows:

| Group | Parameters | Purpose |
|---|---|---|
| PCI identity | `--model`, `--vendor-id`, `--device-id` | Set the label and PCIR vendor/device IDs. |
| GOP from BIOS | `--bios-archive`, `--bios-member`, `--uefi-extract-archive` or `--uefi-extract-bin`, `--gop-container-guid`, `--gop-subtype-guid` or `--gop-path-glob` | Extract a model-specific vendor GOP. |
| Direct GOP | `--gop-efi` | Skip BIOS parsing and supply an already extracted GOP EFI image. |
| Helpers | `--reference-rom`, `--helper-image-indexes`, repeatable `--helper-efi`, or `--no-helpers` | Select the EFI payloads packaged after the GOP. |
| Packager | `--edk2-source-archive` or `--efi-rom-bin` | Build or supply the host-side `EfiRom` utility. |
| Reproducibility | the matching optional `--*-sha256` options and `--expected-output-sha256` | Strictly validate each value that has been pinned. |

### Scenario 1: discovery build for a new platform

At this point the extracted BIOS image, GOP, and final ROM hashes are not known.
Do not invent placeholders and do not pass `--expected-output-sha256`. Supply
the identity and extraction parameters, then let the complete build calculate
the values:

```bash
tools/rebuild-rom.sh \
  --model MODEL-NAME \
  --vendor-id 8086 \
  --device-id DEVICE_ID \
  --bios-archive /path/to/vendor-bios.zip \
  --bios-member path/inside/archive/firmware.bin \
  --gop-container-guid GOP_CONTAINER_GUID \
  --gop-subtype-guid GOP_SUBTYPE_GUID \
  --output firmware-extraction/output/MODEL-NAME.discovery.rom \
  --keep-work-dir
```

For every checksum that was not supplied, the script prints a line like:

```text
observed BIOS archive             <BIOS_ZIP_SHA256>  /path/to/vendor-bios.zip
observed BIOS image               <BIOS_IMAGE_SHA256>  <work-dir>/bios/...
observed extracted GOP            <GOP_SHA256>  <work-dir>/.../body.bin
observed output ROM               <OUTPUT_SHA256>  <work-dir>/result.rom
sha256=<OUTPUT_SHA256>
```

Known retained inputs, such as the repository's reference helper ROM and EDK II
source, remain pinned and are printed as `verified`. `--keep-work-dir` preserves
the extracted payloads and prints `work_dir=...`, so they can be inspected before
their hashes are accepted. `--verify-only` checks only files available before
extraction; it cannot discover the BIOS member, extracted GOP, helper payload,
or output ROM hashes because it intentionally does not perform a build.

### Scenario 2: strict reproduction after review

First inspect the discovery ROM, verify its PCIR identity and payloads, and test
it on the intended hardware. Only an accepted artifact becomes a reference.
Then copy the `observed` values into the matching options and rebuild to a new
path:

```bash
tools/rebuild-rom.sh \
  --model MODEL-NAME \
  --vendor-id 8086 \
  --device-id DEVICE_ID \
  --bios-archive /path/to/vendor-bios.zip \
  --bios-archive-sha256 BIOS_ZIP_SHA256 \
  --bios-member path/inside/archive/firmware.bin \
  --bios-image-sha256 BIOS_IMAGE_SHA256 \
  --gop-container-guid GOP_CONTAINER_GUID \
  --gop-subtype-guid GOP_SUBTYPE_GUID \
  --gop-sha256 GOP_SHA256 \
  --expected-output-sha256 OUTPUT_SHA256 \
  --output firmware-extraction/output/MODEL-NAME.reproduced.rom
```

Every provided value is a strict constraint: any mismatch stops the build
before the result is installed. SHA validation is per input, not an all-or-none
mode; an omitted SHA remains observational while every supplied SHA remains
strict. Compare the discovery and reproduced files as a final independent
check:

```bash
cmp \
  firmware-extraction/output/MODEL-NAME.discovery.rom \
  firmware-extraction/output/MODEL-NAME.reproduced.rom
```

### Getting SHA-256 values manually

The build output is the preferred source because it identifies the role of each
file. The same values can be calculated independently:

```bash
# macOS
shasum -a 256 /path/to/file

# Linux
sha256sum /path/to/file
```

For a discovery build retained with `--keep-work-dir`, hash these artifacts as
needed:

| Value | File |
|---|---|
| `BIOS_ZIP_SHA256` | original `--bios-archive` file |
| `BIOS_IMAGE_SHA256` | `<work-dir>/bios/<bios-member>` |
| `GOP_SHA256` | `<work-dir>/input/image-0.efi` |
| helper SHA values | `<work-dir>/input/image-1.efi`, `image-2.efi`, ... |
| `OUTPUT_SHA256` | final `--output` file |

If the GOP and helpers are already available as EFI payloads, the discovery
build can likewise omit their unknown hashes:

```bash
tools/rebuild-rom.sh \
  --model MODEL-NAME \
  --vendor-id 8086 \
  --device-id DEVICE_ID \
  --gop-efi /path/to/IntelGopDriver.efi \
  --helper-efi /path/to/IgdAssignmentDxe.efi \
  --helper-efi /path/to/PlatformGopPolicy.efi \
  --output firmware-extraction/output/MODEL-NAME.discovery.rom
```

After review, add `--gop-sha256`, `--helper-sha256s`, and
`--expected-output-sha256` with the values printed by that build.

Changing only `--device-id` repackages the same EFI payloads under another PCIR
identity. It does **not** establish that the GOP supports that GPU generation,
that the platform firmware supplies the required IGD state, or that physical
display output will work. Hardware compatibility still requires a model-correct
GOP and an end-to-end guest/display test.

Existing outputs are never replaced without `--force`. Use `--work-dir` to
retain a chosen empty workspace, or `--keep-work-dir` to retain the generated
temporary workspace for inspection after a successful build.

## Manual rebuild runbook

The final operation is packaging, not recompiling the three EFI payloads. The
vendor GOP is extracted unchanged from MS-01 BIOS 1.27. The two helper DXEs are
extracted unchanged from AICodo's reference option ROM. Only EDK II's `EfiRom`
host utility is compiled; it wraps the payloads in new PCI option-ROM headers
declaring `8086:46a6`.

Run the commands from the repository root. `firmware-extraction/` is ignored by
Git and is the intended disposable workspace. The recorded extraction used
macOS `shasum`; on Linux, replace `shasum -a 256` with `sha256sum` and use the
matching UEFIExtract A75 binary for that platform.

### 1. Create the workspace

```bash
ROM_BUILD_ROOT=firmware-extraction
mkdir -p \
  "$ROM_BUILD_ROOT/tools" \
  "$ROM_BUILD_ROOT/tools/reference-rom/extracted" \
  "$ROM_BUILD_ROOT/tools/sources" \
  "$ROM_BUILD_ROOT/ms01-bios-1.27/unpacked" \
  "$ROM_BUILD_ROOT/ms01-bios-1.27/extracted" \
  "$ROM_BUILD_ROOT/ms01-bios-1.27/packaged"
```

### 2. Verify and unpack MS-01 BIOS 1.27

```bash
BIOS_ARCHIVE=roms/vendor/MS-01-AHWSA-V1.27_4_28_V2.zip
printf '%s  %s\n' \
  cf6710534f1de22f0f94515a0bd91b6d95d78e002a060cbe85dfd788865e57d6 \
  "$BIOS_ARCHIVE" | shasum -a 256 -c
unzip -q "$BIOS_ARCHIVE" \
  -d "$ROM_BUILD_ROOT/ms01-bios-1.27/unpacked"
```

Verify the contained firmware image:

```bash
BIOS_BIN="$ROM_BUILD_ROOT/ms01-bios-1.27/unpacked/AHWSA.1.27_250403/AHWSA.bin"
printf '%s  %s\n' \
  dfd4ec78bfe81c33f236b222ffc9acdde648fe39641d0aa0df7e1796e0951201 \
  "$BIOS_BIN" | shasum -a 256 -c
```

MINISFORUM did not publish an independent checksum next to the original
download. The recorded hashes identify the exact HTTPS payload retained in the
repository and used for the verified ROM.

### 3. Extract the vendor Intel GOP

The recorded extraction used LongSoft UEFIExtract NE alpha 75 for macOS. Its
original release archive is tracked in the repository:

```bash
UEFIEXTRACT_ARCHIVE=roms/vendor/tools/UEFIExtract_NE_A75_universal_mac.zip
printf '%s  %s\n' \
  8cbdd6d42193d6fb8a0c37dc860b4695c618f923b8ecfff9c0042fbdd80aaa80 \
  "$UEFIEXTRACT_ARCHIVE" | shasum -a 256 -c
unzip -q "$UEFIEXTRACT_ARCHIVE" \
  -d "$ROM_BUILD_ROOT/tools/UEFIExtract-A75"
"$ROM_BUILD_ROOT/tools/UEFIExtract-A75/UEFIExtract" "$BIOS_BIN" all
```

The original release URL was
`https://github.com/LongSoft/UEFITool/releases/download/A75/UEFIExtract_NE_A75_universal_mac.zip`.

UEFIExtract creates `AHWSA.bin.dump` beside the input image. The GOP payload is
the `body.bin` below option-ROM container GUID
`A0327FE0-1FDA-4E5B-905D-B510C45A61D0` and subtype GUID
`380B6B4F-1454-41F2-A6D3-61D1333E8CB4`. Locate it without depending on the
numbered parent directories generated by UEFIExtract:

```bash
GOP_SOURCE=$(find "$BIOS_BIN.dump" -type f \
  -path '*A0327FE0-1FDA-4E5B-905D-B510C45A61D0/1 380B6B4F-1454-41F2-A6D3-61D1333E8CB4/body.bin' \
  -print -quit)
test -n "$GOP_SOURCE"
GOP_EFI="$ROM_BUILD_ROOT/ms01-bios-1.27/extracted/IntelGopDriver-MS01-BIOS-1.27-GOP-21.0.1066.efi"
cp "$GOP_SOURCE" "$GOP_EFI"
cmp "$GOP_SOURCE" "$GOP_EFI"
test "$(stat -f %z "$GOP_EFI")" = 163840
printf '%s  %s\n' \
  8ed7384baa07772525d007d62cdaba18254e5e6d9e081323c808f0f061e7eb8f \
  "$GOP_EFI" | shasum -a 256 -c
```

On Linux use `stat -c %s` in the size check. `file "$GOP_EFI"` should identify
a PE32+ x86-64 EFI boot-service driver.

### 4. Extract the two reference helper DXEs

Use the exact AICodo reference ROM retained in the repository:

```bash
REFERENCE_ROM=roms/vendor/reference/pc-12-13-14-q10.rom
printf '%s  %s\n' \
  b73c83330a80a18e1780e64e964f1e7b477904316f5362667c648737f40da92f \
  "$REFERENCE_ROM" | shasum -a 256 -c
```

Its original release URL was
`https://github.com/AICodo/intel6-14rom/releases/download/v2.0-20260306-092336/pc-12-13-14-q10.rom`.

Extract its three EFI payloads with the tracked parser:

```bash
python3 tools/inspect_efi_pci_rom.py "$REFERENCE_ROM" \
  --extract-dir "$ROM_BUILD_ROOT/tools/reference-rom/extracted"
```

The reference ROM declares wildcard device `8086:ffff`. Its image 0 is a
generic GOP and is deliberately not used. Images 1 and 2 are the helper DXEs:

```bash
IGD_ASSIGNMENT="$ROM_BUILD_ROOT/tools/reference-rom/extracted/image-1.efi"
GOP_POLICY="$ROM_BUILD_ROOT/tools/reference-rom/extracted/image-2.efi"
printf '%s  %s\n' \
  784fc780ef0606da5978e5a9f51b4dcee0cbf241cf9e50f09ead9b0c8885f21f \
  "$IGD_ASSIGNMENT" | shasum -a 256 -c
printf '%s  %s\n' \
  3a0ce851696dfdc3980f4f105b4701f3146308bf1f8e02b8dd4f97b82b436ed7 \
  "$GOP_POLICY" | shasum -a 256 -c
strings -a -n 5 "$IGD_ASSIGNMENT" | grep -F IgdAssignmentDxe
strings -a -n 5 "$GOP_POLICY" | grep -F PlatformGopPolicy
```

For source audit, the helper project checkout inspected during the build was
[`AICodo/intel6-14rom`](https://github.com/AICodo/intel6-14rom) at
`72c428ce0a8f7af8ee277180190c67d0fe0404ad`. The successful binary build used
the two payloads from the release ROM above; it did not rebuild them from that
checkout.

### 5. Compile the EDK II `EfiRom` utility

This is a build-machine step, separate from deployment of existing ROMs by
Ansible. PVE nodes do not need this source archive or a compiler.

```bash
EDK2_SOURCE_ARCHIVE=roms/vendor/sources/edk2-cc9a0425-EfiRom-source.tar.gz
printf '%s  %s\n' \
  d0a3c823a646133690633982af41285723b266943980e84a61a25296e661046e \
  "$EDK2_SOURCE_ARCHIVE" | shasum -a 256 -c
mkdir -p "$ROM_BUILD_ROOT/tools/sources/edk2"
tar --no-same-owner -xzf "$EDK2_SOURCE_ARCHIVE" \
  -C "$ROM_BUILD_ROOT/tools/sources/edk2"
make -C "$ROM_BUILD_ROOT/tools/sources/edk2/BaseTools/Source/C" EfiRom
EFI_ROM="$ROM_BUILD_ROOT/tools/sources/edk2/BaseTools/Source/C/bin/EfiRom"
test -x "$EFI_ROM"
```

This compiles only the host-side option-ROM packaging utility. The source
archive contains the tracked `BaseTools` and `MdePkg/Include` paths from EDK II
commit `cc9a0425a21a41b723311801f5dfeb6e07ff9ed9`; both paths are required to
compile `EfiRom`. The upstream source is
[`tianocore/edk2`](https://github.com/tianocore/edk2).

The retained archive has sorted members, UID/GID zero, empty owner/group
names, zero timestamps, and no inherited PAX metadata. The gzip header has
neither an original filename nor a build timestamp. File contents, modes,
and symlink targets are preserved. Extraction uses `--no-same-owner` so that
files belong to the extracting user, including when extraction runs as root.
Tar has no wildcard owner value; suppressing ownership restoration is an
extraction option, separate from archive anonymization.

To normalize an equivalent source archive on another build machine:

```bash
python3 tools/normalize-source-archive.py input.tar.gz normalized.tar.gz
```

The normalizer uses only Python's standard library. Given identical member
contents, modes, types, and symlink targets, it removes differences in input
ordering, ownership, and timestamps. Use the same Python and zlib versions
when requiring a byte-identical gzip stream; compression implementations can
differ. The checked-in SHA-256 pins the exact archive used by the build.

### 6. Package the exact `8086:46a6` ROM

Payload order is significant and matches the verified artifact: vendor GOP,
`IgdAssignmentDxe`, then `PlatformGopPolicy`.

```bash
OUTPUT_ROM="$ROM_BUILD_ROOT/ms01-bios-1.27/packaged/ms01-adlp-8086-46a6-gop21.0.1066.rom"
"$EFI_ROM" \
  -e \
  "$GOP_EFI" \
  "$IGD_ASSIGNMENT" \
  "$GOP_POLICY" \
  -f 0x8086 \
  -i 0x46a6 \
  -o "$OUTPUT_ROM"
```

Verify the complete output:

```bash
test "$(stat -f %z "$OUTPUT_ROM")" = 195072
printf '%s  %s\n' \
  954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9 \
  "$OUTPUT_ROM" | shasum -a 256 -c
python3 tools/inspect_efi_pci_rom.py "$OUTPUT_ROM" \
  --extract-dir "$ROM_BUILD_ROOT/ms01-bios-1.27/packaged/validation-extracted"
```

Again, use `stat -c %s` on Linux. The parser must report:

```text
image=0 start=0x0 size=164352 vendor=8086 device=46a6 code_type=03 indicator=00 pe_start=0x200 pe_size=163840
image=1 start=0x28200 size=20992 vendor=8086 device=46a6 code_type=03 indicator=00 pe_start=0x28240 pe_size=20928
image=2 start=0x2d400 size=9728 vendor=8086 device=46a6 code_type=03 indicator=80 pe_start=0x2d500 pe_size=9472
```

Prove that packaging did not alter any EFI payload:

```bash
VALIDATION_DIR="$ROM_BUILD_ROOT/ms01-bios-1.27/packaged/validation-extracted"
cmp "$GOP_EFI" "$VALIDATION_DIR/image-0.efi"
cmp "$IGD_ASSIGNMENT" "$VALIDATION_DIR/image-1.efi"
cmp "$GOP_POLICY" "$VALIDATION_DIR/image-2.efi"
```

Finally, build a second output and require byte identity:

```bash
SECOND_ROM="$ROM_BUILD_ROOT/ms01-bios-1.27/packaged/rebuilt.rom"
"$EFI_ROM" -e "$GOP_EFI" "$IGD_ASSIGNMENT" "$GOP_POLICY" \
  -f 0x8086 -i 0x46a6 -o "$SECOND_ROM"
cmp "$OUTPUT_ROM" "$SECOND_ROM"
```

Successful `cmp` with no output confirms the deterministic package rebuild.

The three EFI payloads are unsigned. Disable Secure Boot in the VM's EFI
variable store before using this ROM.

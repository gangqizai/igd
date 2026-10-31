# MINISFORUM MS-01 IGD passthrough compatibility

**Report date:** 2026-09-01

This report compares observed MS-01 hardware variants for exclusive Intel iGPU
assignment to a Proxmox VM with physical HDMI output. Results concern physical
scanout, not merely loading the guest `i915` driver, headless rendering, or
video transcoding. A result from one or two sampled units is not a guarantee
for every unit of the same model.

## Model comparison

| MS-01 variant | CPU | iGPU | GPU IOMMU isolation | Host display evidence | ROM support | Guest physical-display result | Status |
|---|---|---|---|---|---|---|---|
| S1260-class | Intel Core i5-12600H | `8086:46a6`, rev `0c` | `00:02.0` isolated | HDMI connected, 256-byte EDID, modes through 2560x1440 | Exact combined ROM tracked in `roms/` | Physical GDM over HDMI and accelerated Mesa Intel Iris Xe (ADL GT2) | Verified on one sampled unit; native-first late handoff and explicit host return are machine-validated, with partial physical stress observation and an EDID reliability caveat |
| S1390 | Intel Core i9-13900H | `8086:a720`, rev `04` | `00:02.0` isolated | No connected display or EDID in the collected samples | No bundled ROM declares `a720` | Not tested | Not validated; prerequisite evidence only, with no exact ROM or passthrough experiment |
| S1290 | Intel Core i9-12900H | `8086:4626`, rev `0c` | `00:02.0` isolated | HDMI connected, 128-byte EDID, preferred 1600x1200 mode | Exact custom ROM is reproducibly buildable but is not tracked or distributed | Physical GDM/desktop UI over HDMI with Xorg `AccelMethod none`, `ShadowFB`, and `swrast` | Verified on the tested S1290 unit with the mapped i440fx/OVMF profile; native-first late handoff, guest alternation, and explicit host return are machine-validated, while software rendering is required and physical observation of every handoff remains pending |

## Shared platform evidence

The completely collected samples across these variants shared:

| Property | Observed result |
|---|---|
| BIOS | Version 1.27, dated 2025-04-03 |
| VBT | 9,216 bytes; SHA-256 `1e0ae4005e51c648bc29844481aeba8228ce2a895fa10a53a706c073caaf6646` |
| OpRegion | 8,192 bytes; SHA-256 `49d61274ff2616b4487f3ea762c10ce95a4a187d86ad853e77302cdd3f76d219` |
| Graphics stolen-memory aperture | 60 MiB |
| BIOS DVMT Pre-Allocated value | Not operator-verified |
| IOMMU and interrupt remapping | Active |
| Safe standalone iGPU assignment | Yes: `00:02.0` was isolated |
| Safe PCH HDMI-audio assignment | No |

The identical VBT and OpRegion suggest that these CPU variants share the same
basic MS-01 display-firmware description. Matching the iGPU PCI ID and GOP is
still necessary, but does not eliminate QEMU/OVMF, stolen-memory,
connector-routing, or physical-scanout risks.

## HDMI audio restriction

On every completely collected sample, PCH audio function `00:1f.3` shared an
IOMMU group with host-critical chipset functions:

- `00:1f.0`: eSPI/ISA bridge;
- `00:1f.4`: SMBus controller;
- `00:1f.5`: SPI controller.

Do not bind or assign this whole group merely to obtain HDMI audio. Start with
GPU-only passthrough and use virtual or USB audio when sound is required.

## ROM compatibility

| ROM | Declared PCI device | Model relevance |
|---|---:|---|
| `2in1_rom/igd_rpls.rom` | `8086:a780` | Desktop Raptor Lake-S; not an exact match for the observed MS-01 variants |
| `gen12_igd.rom` | `8086:a780` | Assignment component in the older two-ROM recipe; mismatched for the observed variants |
| `gen12_gop.rom` | `8086:a780` | Not an exact match for the observed variants |
| `gop_rom_by_platform/1240p_gop.rom` | `8086:46a6` | Exact S1260 GOP header, but not a complete combined assignment ROM |
| `roms/ms01-adlp-8086-46a6-gop21.0.1066.rom` | `8086:46a6` | Exact combined S1260 ROM used for verified physical HDMI and accelerated rendering |
| S1290 validation ROM, generated and not tracked | `8086:4626` | Exact-ID combined ROM used for verified S1290 physical HDMI with the software-rendered guest fallback |

The older two-ROM recipe is unsuitable for the observed S1260 configuration:
its assignment ROM declares the wrong PCI ID and it expects the unsafe PCH
audio group. The verified combined S1260 ROM contains the MS-01 BIOS 1.27
Alder Lake-P GOP, `IgdAssignmentDxe`, and `PlatformGopPolicy`, with every PCIR
header declaring `8086:46a6`. See
[`roms/ROM-PROVENANCE.md`](roms/ROM-PROVENANCE.md) for hashes and provenance.

### S1260 and S1290 combined-ROM comparison

The repository contains the S1260 combined ROM but does **not** contain the
generated S1290 validation ROM:

| Target | Repository status | Size | SHA-256 |
|---|---|---:|---|
| S1260 / `8086:46a6` | Tracked at `roms/ms01-adlp-8086-46a6-gop21.0.1066.rom` | 195,072 bytes | `954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9` |
| S1290 / `8086:4626` | Generated for validation; not tracked or distributed | 195,072 bytes | `a08b8f9aa797d9b5622957a4284ef8976a4641c800bf7a33f7dc63b09e18ded2` |

The S1290 discovery and strict-reproduction builds were byte-identical. When
compared with the tracked S1260 ROM, only three bytes differed: the low byte of
the PCI device ID in each of the three PCIR headers (`a6` for `46a6`, `26` for
`4626`). The extracted Intel GOP, `IgdAssignmentDxe`, and
`PlatformGopPolicy` payloads were byte-identical and retained the three hashes
recorded in `roms/ROM-PROVENANCE.md`.

This comparison proves deterministic repackaging under the exact `4626` PCIR
identity. The end-to-end S1290 test separately proves physical scanout with the
documented software-rendered Ubuntu 22.04 fallback; the binary comparison alone
does not. Use the other-model discovery and strict-reproduction workflow in
`roms/ROM-PROVENANCE.md`; do not install the tracked `46a6` ROM on a `4626`
device.

## Variant assessments

### S1260-class / Core i5-12600H / `8086:46a6`

This is the verified configuration. The tested host exposed the iGPU alone in
its IOMMU group and could read the attached HDMI sink's EDID. With the tracked
combined ROM, official QEMU 11, i440fx, OVMF, Secure Boot disabled, and
GPU-only assignment, Ubuntu 26.04.1 displayed GDM over physical HDMI under
Wayland. GNOME Shell opened both i915 DRM nodes and Mesa reported accelerated
Intel Iris Xe Graphics (ADL GT2), rather than software rendering.

Native-first late handoff is also validated on the sampled system. The host can
boot with `i915`, hand the mapped IGD to a guest at VM startup, pass ownership
between stopped and started mapped guests, and explicitly reclaim the IGD for
the host console. Early initramfs isolation remains available for a dedicated
passthrough host that does not require host graphics services.

The machine sequence completed, while physical stress observation was partial.
Repeated handoffs also exposed an EDID reliability caveat despite continued
physical scanout.

The guest still reported its reserved stolen-memory area outside the advertised
stolen-memory window. That warning did not prevent the verified result, but it
remains a stability boundary for further testing.

### S1390 / Core i9-13900H / `8086:a720`

The collected samples had isolated iGPUs and satisfied the host IOMMU
prerequisites. No sample had an attached display detected during collection,
this repository contains no exact `a720` combined ROM, and no passthrough
experiment was completed. This model is not validated. Before attempting
passthrough, prove EDID acquisition with the intended display and build and
inspect an exact ROM.

### S1290 / Core i9-12900H / `8086:4626`

The documented rebuild workflow produced byte-identical discovery and
strict-reproduction ROMs with all three PCIR images declaring `8086:4626`.
The result was installed under a model-specific filename and attached through
a node-specific PVE PCI mapping. The mapping included the live
`subsystem-id=0000:0000`, disabled live migration, and passed the PVE 9.2 node
validator with an empty `checks` array.

With i440fx 11.0, OVMF, `vga: none`, the mapped iGPU at guest `00:02.0`,
OpRegion enabled, and GMS `0x2`, QEMU detected the Intel `4626` OpRegion and
started successfully. The host handed the device to `vfio-pci`; Ubuntu 22.04.5
bound it to `i915`, created `card0` and `renderD128`, authenticated HuC, enabled
GuC submission, started GDM/Xorg and GNOME Shell, and exposed initialized
render, copy, and video engines with zero GPU resets.

After the monitor was connected, the guest read a 128-byte EDID and exposed a
preferred 1600x1200 mode. The accelerated Wayland path still failed scanout;
forcing GDM to Xorg and configuring the `modesetting` driver with
`AccelMethod "none"` activated HDMI at 1600x1200 on pipe A. Xorg reported
`glamor disabled`, `ShadowFB` enabled, and the DRISWRAST GL provider; both Xorg
and GNOME Shell mapped `swrast_dri.so`. DRM state showed an active pipe A,
primary and cursor framebuffers, and HDMI-A-1 attached to that CRTC. No new
AddFB, buffer-import, or modeset failure appeared after the fallback, and the
operator confirmed that the physical display showed GDM or the desktop.

This supersedes the earlier negative physical-output result for the exact
mapped S1290 configuration, but it does not establish accelerated scanout.
The guest still reported its reserved stolen-memory area outside the advertised
window, so the accelerated Wayland path and long-term stability remain open
boundaries.

Native-first late handoff, alternating ownership between mapped guests, and
explicit return to the host were machine-validated on the tested S1290 unit. Physical
observation across the handoff sequence remains pending.

## Recommendation

Use the documented S1260 i440fx/OVMF configuration as the accelerated
reproducible baseline. Prefer native-first late handoff when host-console return
is required; retain early initramfs isolation for a dedicated passthrough host.
For S1290 on the tested Ubuntu 22.04/kernel 5.15 stack, use the exact
`8086:4626` ROM and mapped profile plus the documented Xorg no-acceleration
fallback when physical output is required. For every model, preserve remote
host access and an exclusive-device rollback path before changing VFIO or
initramfs state. Keep the initial configuration GPU-only; HDMI audio remains
unverified and the observed PCH-audio IOMMU groups are unsafe to assign
wholesale.

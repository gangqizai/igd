# Reproduce MS-01 S1260 iGPU passthrough on Proxmox VE

This guide starts with an ordinary Proxmox VE host and Ubuntu VM and reproduces
the repository's verified result: GDM on a physical MS-01 HDMI output with
hardware-accelerated Intel Iris Xe rendering inside the guest.

The verified reference environment was:

- MINISFORUM MS-01 S1260-class, Intel Core i5-12600H;
- Intel Alder Lake-P GT2 iGPU `8086:46a6`, revision `0c`;
- Proxmox VE 9.2.11, kernel 7.0.14-14-pve;
- official `pve-qemu-kvm` 11.0.3-3;
- Ubuntu 26.04.1, kernel 7.0.0-30-generic;
- physical HDMI display attached to the MS-01.

Later PVE and Ubuntu versions may work, but this exact combination is the
verified baseline. The procedure is intentionally GPU-only. HDMI audio through
PCH function `00:1f.3` was not tested and its observed IOMMU group was unsafe
to assign.

## Before you start

Passthrough gives the iGPU exclusively to one running VM. The PVE host loses
its local graphics console and cannot use the iGPU for Quick Sync or
`/dev/dri`. Ensure that the host is reachable through a separate network
interface and SSH before continuing.

Do not proceed unless all of these are true:

- BIOS virtualization and Intel VT-d/IOMMU are enabled;
- the host iGPU is exactly `8086:46a6` at `0000:00:02.0`;
- `00:02.0` is alone in its IOMMU group;
- the intended display works on the host before the iGPU is detached;
- no running VM is already using the iGPU;
- the target VM can boot normally before passthrough is added.

Treat the option-ROM PCI identity as a hard safety boundary on every model.
Before copying a ROM to PVE or referencing it with `romfile=`, inspect every
PCIR image and require its vendor/device ID to match the live PCI function
exactly. Do not mix a ROM from another CPU or model generation merely because
the platform BIOS, VBT, OpRegion, filename, or GPU family looks similar. If any
image declares another ID, stop and build and review an exact-ID ROM. For
example, this guide's `8086:46a6` ROM must not be installed or used on an S1290
`8086:4626` iGPU.

Run host commands below as `root`. The VM, storage, ISO, and bridge values are
runnable examples; change them for your environment. Keep the target VM
stopped whenever changing its PCI or display configuration.

The generic IOMMU and bootloader steps follow the
[Proxmox VE Administration Guide](https://pve.proxmox.com/pve-docs/pve-admin-guide.html).
The direct-BDF and mapped-device profiles below are the MS-01-specific
configurations verified by this repository. They use different `hostpci0` and
`args` lines and must not be combined.

## 1. Clone the repository and verify the ROM

Clone the repository on the PVE host:

```bash
cd /root
git clone https://github.com/romansavrulin/proxmox-ms01-igpu-passthrough.git
cd /root/proxmox-ms01-igpu-passthrough
```

Verify the exact artifact before installing it:

```bash
test "$(stat -c %s roms/ms01-adlp-8086-46a6-gop21.0.1066.rom)" = 195072
printf '%s  %s\n' \
  954a0a86ddf2c45edf655d8ff999b3d8855fb3d3a76424a8b91aef2147f5eac9 \
  roms/ms01-adlp-8086-46a6-gop21.0.1066.rom | sha256sum --check
```

Expected output ends with:

```text
roms/ms01-adlp-8086-46a6-gop21.0.1066.rom: OK
```

The checksum verifies artifact identity and integrity, not compatibility. Do
not copy or install the ROM yet. Complete the live PCI-ID, IOMMU-group, and
display-connector gates in step 2 first.

## 2. Verify the host hardware and isolation

Confirm the exact PCI identity and current driver:

```bash
lspci -nnk -s 00:02.0
test "$(cat /sys/bus/pci/devices/0000:00:02.0/vendor)" = 0x8086
test "$(cat /sys/bus/pci/devices/0000:00:02.0/device)" = 0x46a6
```

Inspect the complete iGPU IOMMU group:

```bash
IGD_GROUP=$(readlink -f /sys/bus/pci/devices/0000:00:02.0/iommu_group)
test -n "$IGD_GROUP"
find "$IGD_GROUP/devices" -maxdepth 1 -type l -printf '%f\n' | sort
```

For the verified layout, the only output is:

```text
0000:00:02.0
```

Do not continue if another PCI function appears. Do not assign `00:1f.3`: on
the observed MS-01 layouts it shared an IOMMU group with the eSPI/ISA bridge,
SMBus, and SPI controllers.

Before detaching the host driver, confirm that the intended physical display is
visible to the host:

```bash
for connector in /sys/class/drm/card*-HDMI-A-*/status; do
  printf '%s: ' "$connector"
  cat "$connector"
done
```

At least one intended connector should report `connected`.

### Install the verified exact-ID ROM and portable alias

Continue only after the checks above confirm the live iGPU is exactly
`8086:46a6`, its IOMMU group is suitable, and the intended display connector is
connected. From this repository checkout on the PVE node, use:

```bash
sudo ./tools/manage-node-rom.py install
```

This installs the content-addressed model ROM and atomically points
`/usr/share/kvm/ms01-igd-current.rom` at it. The validator requires the alias
to stay inside `/usr/share/kvm`, resolve to a regular file, match the manifest
size/SHA-256, and contain only PCIR identities matching the live IGD.

## 3. Save the current host and VM configuration

Choose the VM ID now, even if the VM will be created later:

```bash
VMID=101
BACKUP_DIR="/root/ms01-igd-backup-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$BACKUP_DIR"
cp -a /etc/default/grub "$BACKUP_DIR/" 2>/dev/null || true
cp -a /etc/kernel/cmdline "$BACKUP_DIR/" 2>/dev/null || true
cp -a /etc/initramfs-tools/modules "$BACKUP_DIR/"
cp -a /etc/modprobe.d "$BACKUP_DIR/"
cp -a /etc/modules-load.d "$BACKUP_DIR/"
if qm status "$VMID" >/dev/null 2>&1; then
  qm config "$VMID" >"$BACKUP_DIR/vm-${VMID}.conf"
fi
```

Do not store this backup in the Git checkout.

## 4. Enable Intel IOMMU in the active bootloader

First inspect the installed boot setup:

```bash
proxmox-boot-tool status
cat /proc/cmdline
```

Use exactly one of the following bootloader paths. Preserve all existing kernel
arguments and add `intel_iommu=on`; do not replace the whole command line.

### GRUB

Edit `/etc/default/grub` and add `intel_iommu=on` inside the existing
`GRUB_CMDLINE_LINUX_DEFAULT` value. For example:

```text
GRUB_CMDLINE_LINUX_DEFAULT="quiet intel_iommu=on"
```

Regenerate GRUB:

```bash
update-grub
```

### systemd-boot

Edit the single line in `/etc/kernel/cmdline` and append
`intel_iommu=on`, preserving its existing root and boot arguments. Then run:

```bash
proxmox-boot-tool refresh
```

If the host uses GRUB on ESPs managed by `proxmox-boot-tool`, `update-grub`
normally refreshes them. Running this explicit read/sync check is safe:

```bash
proxmox-boot-tool refresh
```

## 5. Choose the host IGD ownership mode

Choose one mode; do not combine them.

### Native-first late handoff (recommended when host-console return is required)

Keep `i915` available and do not create the blacklist or early `vfio-pci` ID
binding described below. The host boots with the IGD and local console. Starting
a VM with the exclusive mapped IGD hands it to `vfio-pci`. After the VM stops,
first verify that no VM owns the IGD, then explicitly rebind the native driver
before expecting the host console to return. Proxmox does not perform that
restoration automatically.

This mode is validated on the sampled S1260 system for host-to-guest,
guest-to-guest, and guest-to-host ownership transitions. Keep remote access
available throughout the operation.

### Early isolation (dedicated-passthrough option)

Use the following procedure when the host is dedicated to IGD passthrough and
does not need a local graphics console or host IGD services.

Refuse to overwrite files from an earlier or unrelated setup:

```bash
test ! -e /etc/modprobe.d/igd-vfio.conf
test ! -e /etc/modules-load.d/igd-vfio.conf
```

Create a dedicated modprobe file:

```bash
cat >/etc/modprobe.d/igd-vfio.conf <<'EOF'
blacklist i915
blacklist xe
options vfio-pci ids=8086:46a6
EOF
```

Load the VFIO modules during normal boot:

```bash
cat >/etc/modules-load.d/igd-vfio.conf <<'EOF'
vfio
vfio_iommu_type1
vfio_pci
EOF
```

Ensure the same modules are included in initramfs without duplicating existing
lines:

```bash
for module in vfio vfio_iommu_type1 vfio_pci; do
  grep -qxF "$module" /etc/initramfs-tools/modules || \
    printf '%s\n' "$module" >>/etc/initramfs-tools/modules
done
```

Do not add `allow_unsafe_interrupts=1` and do not set `disable_vga=1`.

Rebuild all installed initramfs images and synchronize the boot entries:

```bash
update-initramfs -u -k all
proxmox-boot-tool refresh
```

Keep the target VM stopped, then reboot the PVE host:

```bash
qm status "$VMID" 2>/dev/null || true
systemctl reboot
```

## 6. Verify the selected ownership mode after reboot

Reconnect through SSH and verify the effective boot state:

```bash
cat /proc/cmdline
lspci -nnk -s 00:02.0
lsmod | grep -E '^(vfio|i915|xe)' || true
dmesg | grep -E 'DMAR|IOMMU|vfio' | tail -100
/usr/bin/kvm -machine help | grep -F pc-i440fx-11.0
```

For early isolation, required results are:

- `/proc/cmdline` contains `intel_iommu=on`;
- `Kernel driver in use` for `00:02.0` is `vfio-pci`;
- host `i915` and `xe` are not using the iGPU;
- IOMMU initialization has no fatal error.

Stop here and restore the host configuration if `00:02.0` is not owned by
`vfio-pci`.

For native-first late handoff, `Kernel driver in use` should be `i915` before
the VM starts. After the VM stops, verify that no VM owns the IGD, perform the
explicit native-driver rebind, and verify `i915` ownership again before
accepting host-console return.

## 7. Create and install the guest

The easiest clean path is to install the guest with an emulated display first,
then attach the physical iGPU. Set values appropriate for your storage, ISO,
bridge, and desired VM ID:

```bash
VMID=101
VM_NAME=ubuntu-igd
VM_STORAGE=local-zfs
INSTALL_ISO=local:iso/ubuntu-26.04.1-desktop-amd64.iso
VM_BRIDGE=vmbr0
```

Change these examples if your VM ID, storage, ISO volume, or bridge differs.

Create an OVMF VM with no pre-enrolled Secure Boot keys:

```bash
qm create "$VMID" \
  --name "$VM_NAME" \
  --machine pc-i440fx-11.0 \
  --bios ovmf \
  --ostype l26 \
  --cpu host \
  --cores 4 \
  --memory 8192 \
  --scsihw virtio-scsi-single \
  --scsi0 "${VM_STORAGE}:64,discard=on,iothread=1" \
  --efidisk0 "${VM_STORAGE}:1,efitype=4m,pre-enrolled-keys=0" \
  --ide2 "${INSTALL_ISO},media=cdrom" \
  --net0 "virtio,bridge=${VM_BRIDGE}" \
  --vga std \
  --onboot 0
qm set "$VMID" --boot 'order=scsi0;ide2'
```

Install Ubuntu normally through the PVE console. Inside the guest, install the
guest agent and graphics inspection tools:

```bash
sudo apt update
sudo apt install -y qemu-guest-agent mesa-utils
sudo systemctl enable --now qemu-guest-agent
```

Confirm the guest boots normally, then shut it down:

```bash
qm shutdown "$VMID" --timeout 180
qm wait "$VMID" --timeout 180
qm status "$VMID"
```

The final status must be `stopped`. If supported by the VM storage, create a
configuration recovery snapshot:

```bash
qm snapshot "$VMID" pre-igd-passthrough
```

## 8. Choose one iGPU attachment method

Both methods pass the same exclusive physical IGD to one VM. Keep the VM
stopped, choose exactly one method, and do not combine their `hostpci0` or
`args` settings.

For either method, do not add the PCH audio function `00:1f.3`, a second
GOP/audio ROM, Q35, a patched QEMU/OVMF package, or an emulated VGA device.

### Method A: direct PCI address

The direct method is concise and appropriate when the VM will remain on this
node. It stores the physical BDF in the VM configuration and therefore does not
provide the node abstraction of a PVE resource mapping.

Confirm that `hostpci0` and custom `args` are not already used:

```bash
qm config "$VMID" | grep -E '^(hostpci0|args|bios|machine|vga|efidisk0):' || true
```

Apply the verified direct configuration:

```bash
qm set "$VMID" --machine pc-i440fx-11.0
qm set "$VMID" --bios ovmf
qm set "$VMID" --vga none
qm set "$VMID" --hostpci0 \
  '0000:00:02.0,legacy-igd=1,romfile=ms01-adlp-8086-46a6-gop21.0.1066.rom'
qm set "$VMID" --args \
  '-set device.hostpci0.x-igd-opregion=on -set device.hostpci0.x-igd-gms=0x2'
```

The relevant direct VM configuration must be:

```text
bios: ovmf
machine: pc-i440fx-11.0
vga: none
hostpci0: 0000:00:02.0,legacy-igd=1,romfile=ms01-adlp-8086-46a6-gop21.0.1066.rom
args: -set device.hostpci0.x-igd-opregion=on -set device.hostpci0.x-igd-gms=0x2
```

PVE's `legacy-igd=1` supplies the direct method's guest topology. Do not add
`x-igd-legacy-mode=on`; QEMU 11 rejects it for this Gen12 device. A VM using a
direct BDF must be reconfigured and revalidated for a destination node rather
than assuming that the same PCI address identifies a compatible IGD there. The
direct method is also exclusive and not live migratable.

Inspect the generated direct command before starting:

```bash
qm config "$VMID"
qm showcmd "$VMID" --pretty | grep -E 'vfio|romfile|x-igd|00:02'
```

### Method B: PVE PCI resource mapping

#### Create and verify the node-specific mapping

PVE stores a logical PCI resource mapping in cluster configuration, while each
entry inside it identifies the physical device on one specific node. Derive the
node name, IOMMU group, and subsystem identity from the live host; do not copy
any of these values from the reference machine:

```bash
PVE_NODE=$(hostname -s)
IGD_PATH=0000:00:02.0
IGD_MAP=MS01-IGD
IGD_GROUP_PATH=$(readlink -f "/sys/bus/pci/devices/${IGD_PATH}/iommu_group")
IGD_GROUP=${IGD_GROUP_PATH##*/}
IGD_SUBSYSTEM_VENDOR=$(
  sed 's/^0x//' "/sys/bus/pci/devices/${IGD_PATH}/subsystem_vendor"
)
IGD_SUBSYSTEM_DEVICE=$(
  sed 's/^0x//' "/sys/bus/pci/devices/${IGD_PATH}/subsystem_device"
)
IGD_SUBSYSTEM_ID="${IGD_SUBSYSTEM_VENDOR}:${IGD_SUBSYSTEM_DEVICE}"

test -n "$PVE_NODE"
test -n "$IGD_GROUP_PATH"
[[ "$IGD_SUBSYSTEM_VENDOR" =~ ^[[:xdigit:]]{4}$ ]]
[[ "$IGD_SUBSYSTEM_DEVICE" =~ ^[[:xdigit:]]{4}$ ]]
test "$(cat "/sys/bus/pci/devices/${IGD_PATH}/vendor")" = 0x8086
test "$(cat "/sys/bus/pci/devices/${IGD_PATH}/device")" = 0x46a6
test "$(find "${IGD_GROUP_PATH}/devices" -maxdepth 1 -type l -printf '%f\n')" = \
  "$IGD_PATH"
```

Before creating anything, ensure that the logical name is unused:

```bash
(
if pvesh get "/cluster/mapping/pci/${IGD_MAP}" >/dev/null 2>&1; then
  echo "Mapping ${IGD_MAP} already exists; inspect it instead of overwriting it"
  pvesh get "/cluster/mapping/pci/${IGD_MAP}" --output-format json-pretty
  exit 1
fi
)
```

Create the mapping with live migration explicitly disabled:

```bash
pvesh create /cluster/mapping/pci \
  --id "$IGD_MAP" \
  --map \
    "node=${PVE_NODE},path=${IGD_PATH},id=8086:46a6,subsystem-id=${IGD_SUBSYSTEM_ID},iommugroup=${IGD_GROUP}" \
  --description \
    'Exclusive onboard Intel Alder Lake-P IGD 8086:46a6; not live migratable' \
  --live-migration-capable 0

EXPECTED_MAP="node=${PVE_NODE},path=${IGD_PATH},id=8086:46a6,subsystem-id=${IGD_SUBSYSTEM_ID},iommugroup=${IGD_GROUP}"
MAPPING_JSON=$(
  pvesh get "/cluster/mapping/pci/${IGD_MAP}" --output-format json
)
test "$(jq -r '.map | length' <<<"$MAPPING_JSON")" = 1
test "$(jq -r '.map[0]' <<<"$MAPPING_JSON")" = "$EXPECTED_MAP"
test "$(jq -r '."live-migration-capable"' <<<"$MAPPING_JSON")" = 0
printf '%s\n' "$MAPPING_JSON" | jq .

NODE_CHECK_JSON=$(
  pvesh get /cluster/mapping/pci --check-node "$PVE_NODE" \
    --output-format json
)
test "$(
  jq --arg id "$IGD_MAP" '[.[] | select(.id == $id)] | length' \
    <<<"$NODE_CHECK_JSON"
)" = 1
test "$(
  jq --arg id "$IGD_MAP" \
    '[.[] | select(.id == $id) | .checks[]] | length' \
    <<<"$NODE_CHECK_JSON"
)" = 0
printf '%s\n' "$NODE_CHECK_JSON" | jq .
```

Require the returned `MS01-IGD` entry to contain the expected node, path,
`8086:46a6`, live subsystem identity, IOMMU group, and live-migration value
`0`, with an empty `checks` array. PVE 9.2 requires `subsystem-id` even when
the live device reports `0000:0000`; that value is an exact identity, not a
wildcard. Do not omit or invent it.

The same logical mapping may contain entries for several PVE nodes. Each node
must independently pass the PCI-ID, IOMMU-group, VFIO, firmware, and physical
connector gates in this guide. Updating `--map` replaces the mapping's entry
list, so preserve every existing node entry when adding another one. The ROM is
not stored in the resource mapping or replicated by pmxcfs: install the same
checksum-verified file under `/usr/share/kvm/` on every eligible node.

Keep `live-migration-capable=0`. The physical IGD is exclusive to one running
VM on a node, and live migration is not supported by this verified profile.
Offline relocation can only work when the destination has a valid entry under
the same mapping ID, the verified ROM, and the required host VFIO setup.

#### Attach the mapping to the VM

Confirm that `hostpci0` and custom `args` are not already used:

```bash
qm config "$VMID" | grep -E '^(hostpci0|args|bios|machine|vga|efidisk0):' || true
```

Apply the verified mapped configuration:

```bash
qm set "$VMID" --machine pc-i440fx-11.0
qm set "$VMID" --bios ovmf
qm set "$VMID" --vga none
qm set "$VMID" --hostpci0 \
  'mapping=MS01-IGD,romfile=ms01-igd-current.rom,x-vga=1'
qm set "$VMID" --args \
  '-set device.hostpci0.addr=02.0 -set device.hostpci0.x-igd-legacy-mode=off -set device.hostpci0.x-igd-opregion=on -set device.hostpci0.x-igd-gms=0x2'
```

For the mapped method, do not add any of the following:

- `legacy-igd=1` or `x-igd-legacy-mode=on` — this verified UEFI profile uses
  `x-igd-legacy-mode=off`;
- `x-igd-lpc=on` — it conflicts with the PVE i440fx bridge at guest `00:1f.0`;

Inspect the final configuration before starting:

```bash
qm config "$VMID"
qm showcmd "$VMID" --pretty | grep -E 'vfio|romfile|x-igd|00:02'
```

The relevant mapped VM configuration must be:

```text
bios: ovmf
machine: pc-i440fx-11.0
vga: none
hostpci0: mapping=MS01-IGD,romfile=ms01-igd-current.rom,x-vga=1
args: -set device.hostpci0.addr=02.0 -set device.hostpci0.x-igd-legacy-mode=off -set device.hostpci0.x-igd-opregion=on -set device.hostpci0.x-igd-gms=0x2
```

## 9. Start the VM and verify physical output

Connect the display to the MS-01 before starting the VM:

```bash
qm start "$VMID"
qm status "$VMID"
```

The physical display should show guest firmware or Linux output and then GDM.
The PVE noVNC/SPICE console is expected to be unavailable because `vga: none`
removes the emulated display.

If there is no physical output, stop rather than adding unrelated ROMs or
passing the PCH audio group:

```bash
qm shutdown "$VMID" --timeout 180
```

## 10. Verify acceleration inside Ubuntu

Run these commands in the guest through SSH, the physical session, or the QEMU
guest agent:

```bash
lspci -nnk -s 00:02.0
ls -l /dev/dri
for connector in /sys/class/drm/card*-HDMI-A-*/status; do
  printf '%s: ' "$connector"
  cat "$connector"
done
systemctl is-active gdm display-manager
```

In a terminal opened from the physical graphical session, run:

```bash
echo "$XDG_SESSION_TYPE"
glxinfo -B | grep -E 'OpenGL vendor|OpenGL renderer|OpenGL version'
```

Acceptance criteria:

- guest `00:02.0` uses kernel driver `i915`;
- `/dev/dri/card0` and `/dev/dri/renderD128` exist;
- the intended HDMI connector reports `connected`;
- GDM/display-manager is active;
- the physical display shows the GDM or desktop UI;
- the renderer contains Intel Iris Xe/ADL GT2 and does not contain
  `llvmpipe`, `softpipe`, or `Software Rasterizer`.

The verified guest emitted this warning:

```text
Stolen reserved area [mem 0x50200000-0x503fffff] outside stolen memory
[mem 0xb7f00000-0xbbefffff]
```

It did not prevent physical output or hardware acceleration. Treat it as a
stability warning, not by itself as a failed installation.

## Ubuntu 22.04 physical-output fallback without acceleration

Ubuntu 22.04.5 with kernel `5.15.0-97-generic`, Mesa 23.2.1, and Mutter
42.9 exposed the iGPU, render node, EDID, and accelerated ADL GT2 renderer,
but the Wayland greeter could not create its scanout framebuffer:

```text
Failed to lock front buffer on /dev/dri/card0: drmModeAddFB failed: No such device
```

On that older guest stack, physical GDM output was verified only with an Xorg
software-rendered fallback. The same fallback was verified on S1290
`8086:4626`: the guest selected 1600x1200 on HDMI pipe A and the operator
confirmed visible GDM or desktop output. This is not equivalent to the
accelerated result above and does not satisfy the acceleration acceptance
criteria. The S1290 test used its exact model-specific ROM; never substitute
this guide's tracked S1260 `8086:46a6` ROM.

Keep the VM protected by a snapshot. First force GDM to use Xorg by enabling
the existing setting in `/etc/gdm3/custom.conf`:

```ini
[daemon]
WaylandEnable=false
```

Then create `/etc/X11/xorg.conf.d/20-igd-noaccel.conf`:

```text
Section "Device"
    Identifier "IGD"
    Driver "modesetting"
    BusID "PCI:0:2:0"
    Option "AccelMethod" "none"
EndSection
```

Restart GDM:

```bash
systemctl restart gdm
```

The verified fallback reported all of the following:

- `gdm-x-session` and Xorg running on `tty1`;
- `AccelMethod none`, `glamor disabled`, and `ShadowFB enabled YES`;
- HDMI connected and driven by pipe A;
- linear primary and cursor framebuffers allocated by Xorg;
- `swrast_dri.so` loaded instead of `iris_dri.so`;
- no new `drmModeAddFB`, `Import BO`, or modeset failure from the current
  GNOME Shell process;
- operator-visible GDM on the physical HDMI output.

For the verified S1290 run, the connector supplied a 128-byte EDID, 1600x1200
was the active preferred mode, and DRM atomic state showed pipe A active with
primary and cursor framebuffers. The existing stolen-memory warning remained,
but no new AddFB, buffer-import, or modeset failure appeared after enabling the
fallback.

Both files are required. An Xorg `Device` section alone has no effect while
GDM is still running a Wayland greeter. Roll back the VM snapshot to remove
this fallback and restore the previous guest configuration.

## Roll back the VM

Shut down the guest and remove the passthrough-specific settings:

```bash
qm shutdown "$VMID" --timeout 180
qm wait "$VMID" --timeout 180
qm set "$VMID" --delete hostpci0
qm set "$VMID" --delete args
qm set "$VMID" --vga std
qm start "$VMID"
```

Detaching `hostpci0` from one VM does not require deleting the cluster mapping.
Keep it when another VM or node uses the logical device. To retire the mapping,
first stop every VM that could use the IGD and prove that no VM configuration
still references it:

```bash
grep -R -- 'mapping=MS01-IGD' /etc/pve/qemu-server || true
pvesh delete /cluster/mapping/pci/MS01-IGD
```

Run the delete command only when the grep output is empty. Removing the mapping
does not restore host `i915`; that is a separate host rollback below.

Alternatively, while the VM is stopped, roll back the optional snapshot:

```bash
qm rollback "$VMID" pre-igd-passthrough
```

## Roll back the host

First ensure that no VM is using `00:02.0`. Set `BACKUP_DIR` to the exact
directory created in step 3, then remove the dedicated files created by this
guide and restore the original initramfs module list:

```bash
BACKUP_DIR=/root/ms01-igd-backup-YYYYMMDDTHHMMSSZ
test -f "$BACKUP_DIR/modules"
rm -f /etc/modprobe.d/igd-vfio.conf
rm -f /etc/modules-load.d/igd-vfio.conf
install -o root -g root -m 0644 \
  "$BACKUP_DIR/modules" /etc/initramfs-tools/modules
```

Restore the bootloader file used in step 4.

For GRUB:

```bash
test -f "$BACKUP_DIR/grub"
install -o root -g root -m 0644 "$BACKUP_DIR/grub" /etc/default/grub
update-grub
proxmox-boot-tool refresh
```

For systemd-boot:

```bash
test -f "$BACKUP_DIR/cmdline"
install -o root -g root -m 0644 "$BACKUP_DIR/cmdline" /etc/kernel/cmdline
proxmox-boot-tool refresh
```

Finally rebuild initramfs and reboot:

```bash
update-initramfs -u -k all
proxmox-boot-tool refresh
systemctl reboot
```

After reboot, verify that the host reclaimed the iGPU:

```bash
lspci -nnk -s 00:02.0
```

`Kernel driver in use` should again be `i915`.

## Verified and unverified boundaries

Verified:

- S1260-class MS-01 with `8086:46a6`;
- physical HDMI GDM output;
- Wayland and accelerated Mesa Intel Iris Xe rendering;
- official QEMU 11 with i440fx and OVMF;
- the tracked combined ROM and checksum;
- direct PCI-address attachment with `legacy-igd=1`;
- node-specific PVE PCI resource mapping with live migration disabled;
- GPU-only passthrough;
- native-first late handoff with explicit return to the host, including
  repeated ownership transitions between mapped guests.
- S1290 `8086:4626` physical HDMI at 1600x1200 with the exact generated
  ROM, mapped-device profile, and Ubuntu 22.04 Xorg software-rendered fallback.

Not verified:

- HDMI audio passthrough;
- Q35;
- S1290 hardware-accelerated physical output;
- Windows guests;
- simultaneous sharing of the iGPU by multiple VMs;
- live migration or VM hibernation with the iGPU attached. Live migration must
  remain disabled for this mapping.

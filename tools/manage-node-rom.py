#!/usr/bin/env python3
"""Fail-closed node-local ROM alias management for mapped MS-01 IGDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "roms/node-rom-manifest.json"
DEFAULT_ROM_DIR = Path("/usr/share/kvm")
DEFAULT_PCI_ROOT = Path("/sys/bus/pci/devices")
LOCAL_MANIFEST = Path("/etc/ms01-igd/node-rom-manifest.json")


class Refusal(RuntimeError):
    pass


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise Refusal(f"cannot read {path}: {error}") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Refusal(f"cannot load manifest {path}: {error}") from error
    if data.get("schema") != 1:
        raise Refusal("manifest schema must be 1")
    alias = data.get("alias")
    if not isinstance(alias, str) or Path(alias).name != alias:
        raise Refusal("manifest alias must be a single filename")
    if not data.get("profiles"):
        raise Refusal("manifest has no profiles")
    return data


def select_profile(
    manifest: dict[str, Any],
    pci_id: str,
    *,
    allow_candidate: bool = False,
) -> dict[str, Any]:
    matches = [
        profile
        for profile in manifest["profiles"]
        if profile.get("pci_id") == pci_id
    ]
    if len(matches) != 1:
        raise Refusal(f"live IGD PCI ID does not select exactly one profile: {pci_id}")
    profile = matches[0]
    accepted = {"qualified", "candidate"} if allow_candidate else {"qualified"}
    if profile.get("status") not in accepted:
        raise Refusal(f"profile {profile.get('name')!r} is not qualified")
    return profile


def read_subsystem_id(device_root: Path) -> str:
    vendor = read_text(device_root / "subsystem_vendor").removeprefix("0x").lower()
    device = read_text(device_root / "subsystem_device").removeprefix("0x").lower()
    if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(
        r"[0-9a-f]{4}", device
    ):
        raise Refusal("live PCI subsystem identity is malformed")
    return f"{vendor}:{device}"


def pci_identity(pci_root: Path, address: str) -> tuple[str, str, str]:
    device_root = pci_root / address
    vendor = read_text(device_root / "vendor").removeprefix("0x").lower()
    device = read_text(device_root / "device").removeprefix("0x").lower()
    if not re.fullmatch(r"[0-9a-f]{4}", vendor) or not re.fullmatch(
        r"[0-9a-f]{4}", device
    ):
        raise Refusal("live PCI identity is malformed")
    group_link = device_root / "iommu_group"
    try:
        group_root = group_link.resolve(strict=True)
    except OSError as error:
        raise Refusal(f"IGD has no readable IOMMU group: {error}") from error
    members = sorted(path.name for path in (group_root / "devices").iterdir())
    if members != [address]:
        raise Refusal(f"IGD IOMMU group is not isolated: {members!r}")
    return f"{vendor}:{device}", group_root.name, read_subsystem_id(device_root)


def pcir_identities(path: Path) -> list[str]:
    data = path.read_bytes()
    identities: list[str] = []
    offset = 0
    while offset < len(data):
        if data[offset : offset + 2] != b"\x55\xaa":
            raise Refusal(f"missing PCI ROM signature at 0x{offset:x}")
        if offset + 0x1A > len(data):
            raise Refusal("truncated PCI ROM header")
        pcir = offset + struct.unpack_from("<H", data, offset + 0x18)[0]
        if data[pcir : pcir + 4] != b"PCIR":
            raise Refusal(f"missing PCIR signature at 0x{pcir:x}")
        vendor, device = struct.unpack_from("<HH", data, pcir + 4)
        blocks = struct.unpack_from("<H", data, pcir + 0x10)[0]
        indicator = data[pcir + 0x15]
        if blocks == 0:
            raise Refusal("PCIR image has zero length")
        identities.append(f"{vendor:04x}:{device:04x}")
        offset += blocks * 512
        if indicator & 0x80:
            break
    if offset != len(data):
        raise Refusal(f"PCIR images cover {offset} bytes, ROM has {len(data)}")
    return identities


def path_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def verify_rom(path: Path, profile: dict[str, Any], rom_root: Path) -> None:
    resolved_root = rom_root.resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise Refusal(f"ROM path does not resolve: {path}: {error}") from error
    if not path_inside(resolved, resolved_root):
        raise Refusal(f"ROM resolves outside {resolved_root}: {resolved}")
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise Refusal(f"ROM target is not a regular file: {resolved}")
    if resolved.stat().st_size != profile.get("bytes"):
        raise Refusal(
            f"ROM size mismatch: expected {profile.get('bytes')}, got {resolved.stat().st_size}"
        )
    actual_hash = sha256_file(resolved)
    if actual_hash != profile.get("sha256"):
        raise Refusal(
            f"ROM SHA-256 mismatch: expected {profile.get('sha256')}, got {actual_hash}"
        )
    identities = pcir_identities(resolved)
    if not identities or any(item != profile.get("pci_id") for item in identities):
        raise Refusal(
            f"ROM PCIR identities do not all match {profile.get('pci_id')}: {identities!r}"
        )


def verify_node(
    manifest_path: Path,
    rom_root: Path,
    pci_root: Path,
) -> tuple[dict[str, Any], str, str]:
    manifest = load_manifest(manifest_path)
    live_id, group, subsystem_id = pci_identity(
        pci_root, manifest.get("igd_path", "0000:00:02.0")
    )
    profile = select_profile(manifest, live_id)
    verify_rom(rom_root / manifest["alias"], profile, rom_root)
    return profile, group, subsystem_id


def atomic_install(source: Path, target: Path, mode: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as destination, source.open("rb") as origin:
            shutil.copyfileobj(origin, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def verify_source(path: Path, profile: dict[str, Any]) -> None:
    if not path.is_file():
        raise Refusal(f"source ROM is not a regular file: {path}")
    if path.stat().st_size != profile.get("bytes"):
        raise Refusal("source ROM size does not match manifest")
    if sha256_file(path) != profile.get("sha256"):
        raise Refusal("source ROM SHA-256 does not match manifest")
    identities = pcir_identities(path)
    if any(item != profile.get("pci_id") for item in identities):
        raise Refusal(f"source ROM PCIR identity mismatch: {identities!r}")


def install_alias(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    live_id, _, _ = pci_identity(
        args.pci_root, manifest.get("igd_path", "0000:00:02.0")
    )
    profile = select_profile(manifest, live_id, allow_candidate=args.allow_candidate)
    source_rom = args.rom
    if source_rom is None:
        source_rom = args.manifest.parent / profile["source"]
    verify_source(source_rom, profile)
    target = args.rom_root / profile["rom"]
    alias = args.rom_root / manifest["alias"]
    args.rom_root.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256_file(target) != profile["sha256"]:
        raise Refusal(f"refusing to overwrite mismatched content-addressed ROM {target}")
    if not target.exists():
        atomic_install(source_rom, target, 0o644)
    temporary_alias = args.rom_root / f".{manifest['alias']}.{os.getpid()}"
    temporary_alias.unlink(missing_ok=True)
    temporary_alias.symlink_to(target.name)
    os.replace(temporary_alias, alias)
    if args.local_manifest is not None:
        atomic_install(args.manifest, args.local_manifest, 0o644)
    verify_rom(alias, profile, args.rom_root)
    print(
        f"NODE ROM INSTALLED: pci_id={live_id} "
        f"alias={alias} target={target.name} sha256={profile['sha256']}"
    )


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise Refusal(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout


def parse_mapping_entry(entry: str) -> dict[str, str]:
    result = {}
    for field in entry.split(","):
        if "=" not in field:
            raise Refusal(f"malformed PVE mapping field: {field!r}")
        key, value = field.split("=", 1)
        result[key] = value
    return result


def mapping_action(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    profile, group, subsystem_id = verify_node(
        args.manifest,
        args.rom_root,
        args.pci_root,
    )
    node = socket.gethostname().split(".", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", node):
        raise Refusal(f"invalid local PVE node name: {node!r}")
    mapping_id = manifest["mapping_id"]
    address = manifest.get("igd_path", "0000:00:02.0")
    expected = {
        "node": node,
        "path": address,
        "id": profile["pci_id"],
        "subsystem-id": subsystem_id,
        "iommugroup": group,
    }
    mapping_path = f"/cluster/mapping/pci/{mapping_id}"
    existing_result = subprocess.run(
        ["pvesh", "get", mapping_path, "--output-format", "json"],
        text=True,
        capture_output=True,
    )
    if existing_result.returncode == 0:
        try:
            existing = json.loads(existing_result.stdout)
        except json.JSONDecodeError as error:
            raise Refusal("PVE returned malformed mapping JSON") from error
        entries = [parse_mapping_entry(item) for item in existing.get("map", [])]
        other_entries = [item for item in entries if item.get("node") != node]
        current_entries = [item for item in entries if item.get("node") == node]
        if current_entries == [expected] and existing.get("live-migration-capable") == 0:
            print(
                f"PCI MAPPING CHECK PASSED: id={mapping_id} node={node} "
                f"pci_id={profile['pci_id']}"
            )
            return
        new_entries = other_entries + [expected]
        command = ["pvesh", "set", mapping_path, "--digest", existing["digest"]]
    else:
        new_entries = [expected]
        command = ["pvesh", "create", "/cluster/mapping/pci", "--id", mapping_id]
    for entry in new_entries:
        command.extend(
            [
                "--map",
                ",".join(
                    f"{key}={entry[key]}"
                    for key in ("node", "path", "id", "subsystem-id", "iommugroup")
                ),
            ]
        )
    command.extend(
        [
            "--description",
            "Exclusive node-local MS-01 IGD selected by exact PCI ID and ROM manifest",
            "--live-migration-capable",
            "0",
        ]
    )
    run(command)
    checked = json.loads(
        run(
            [
                "pvesh",
                "get",
                "/cluster/mapping/pci",
                "--check-node",
                node,
                "--output-format",
                "json",
            ]
        )
    )
    matches = [item for item in checked if item.get("id") == mapping_id]
    if len(matches) != 1 or matches[0].get("checks"):
        raise Refusal(f"PVE mapping validation failed for {mapping_id} on {node}")
    print(
        f"PCI MAPPING RECONCILED: id={mapping_id} node={node} "
        f"pci_id={profile['pci_id']}"
    )


def vm_config(vmid: int, profile: dict[str, Any], alias: str, mapping_id: str) -> str:
    config = run(["qm", "config", str(vmid), "--current"])
    values = {}
    for line in config.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            values[key] = value
    required_hostpci = f"mapping={mapping_id},romfile={alias},x-vga=1"
    if values.get("bios") != "ovmf":
        raise Refusal(f"VM {vmid} does not use OVMF")
    if values.get("machine") != profile.get("machine"):
        raise Refusal(f"VM {vmid} machine does not match the qualified profile")
    if values.get("vga") != "none":
        raise Refusal(f"VM {vmid} must use vga: none")
    if values.get("hostpci0") != required_hostpci:
        raise Refusal(f"VM {vmid} hostpci0 must be exactly {required_hostpci!r}")
    if values.get("args") != profile.get("qemu_args"):
        raise Refusal(f"VM {vmid} QEMU args do not match the qualified profile")
    efidisks = [value for key, value in values.items() if key.startswith("efidisk")]
    if len(efidisks) != 1 or "pre-enrolled-keys=0" not in efidisks[0]:
        raise Refusal(f"VM {vmid} EFI Secure Boot is not proven disabled")
    return config


def configure_vm_action(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    profile, _, _ = verify_node(
        args.manifest,
        args.rom_root,
        args.pci_root,
    )
    node = socket.gethostname().split(".", 1)[0]
    confirmation = args.confirm_destroy.replace("\\@", "@")
    required_confirmation = f"{args.vmid}@{node}"
    if confirmation != required_confirmation:
        raise Refusal(
            f"destructive confirmation required: --confirm-destroy {required_confirmation}"
        )
    hook = Path("/var/lib/vz/snippets/ms01-igd-pre-start-hook")
    if not hook.is_file() or hook.stat().st_size == 0:
        raise Refusal("installed pre-start hook is missing or empty")
    current = run(["qm", "config", str(args.vmid), "--current"])
    values = dict(
        line.split(": ", 1) for line in current.splitlines() if ": " in line
    )
    if values.get("name") != args.expect_current_vm:
        raise Refusal(
            f"VM name mismatch: expected {args.expect_current_vm!r}, "
            f"got {values.get('name')!r}"
        )
    mac_match = re.search(
        r"(?:^|,)(?:virtio|e1000|vmxnet3)=([0-9A-Fa-f:]{17})(?:,|$)",
        values.get("net0", ""),
    )
    live_mac = mac_match.group(1).upper() if mac_match else None
    if live_mac != args.expect_mac.upper():
        raise Refusal(f"VM MAC mismatch: expected {args.expect_mac}, got {live_mac}")
    if run(["qm", "status", str(args.vmid)]).strip() != "status: stopped":
        raise Refusal(f"VM {args.vmid} must be stopped before portable conversion")
    efidisks = [value for key, value in values.items() if key.startswith("efidisk")]
    if len(efidisks) != 1 or "pre-enrolled-keys=0" not in efidisks[0]:
        raise Refusal(f"VM {args.vmid} EFI Secure Boot is not proven disabled")
    mapping_action(args)
    hostpci = (
        f"mapping={manifest['mapping_id']},romfile={manifest['alias']},x-vga=1"
    )
    run(
        [
            "qm",
            "set",
            str(args.vmid),
            "--bios",
            "ovmf",
            "--machine",
            profile["machine"],
            "--vga",
            "none",
            "--hostpci0",
            hostpci,
            "--args",
            profile["qemu_args"],
            "--hookscript",
            "local:snippets/ms01-igd-pre-start-hook",
        ]
    )
    vm_config(args.vmid, profile, manifest["alias"], manifest["mapping_id"])
    print(
        f"PORTABLE IGD VM CONFIGURED: vmid={args.vmid} node={node} "
        f"name={args.expect_current_vm} mac={live_mac}"
    )


def check_action(args: argparse.Namespace) -> None:
    profile, group, subsystem_id = verify_node(
        args.manifest,
        args.rom_root,
        args.pci_root,
    )
    manifest = load_manifest(args.manifest)
    if args.vmid is not None:
        vm_config(args.vmid, profile, manifest["alias"], args.mapping_id)
    print(
        f"NODE ROM CHECK PASSED: profile={profile['name']} "
        f"pci_id={profile['pci_id']} iommu_group={group} subsystem_id={subsystem_id}"
    )


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    common.add_argument("--rom-root", type=Path, default=DEFAULT_ROM_DIR)
    common.add_argument("--pci-root", type=Path, default=DEFAULT_PCI_ROOT)
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="action", required=True)
    check = commands.add_parser("check", parents=[common])
    check.add_argument("--vmid", type=int)
    check.add_argument("--mapping-id", default="MS01-IGD")
    install = commands.add_parser("install", parents=[common])
    install.add_argument(
        "--rom",
        type=Path,
        help="ROM source; defaults to the profile source beside the manifest",
    )
    install.add_argument(
        "--allow-candidate",
        action="store_true",
        help="install a candidate ROM without admitting it for pre-start checks",
    )
    install.add_argument("--local-manifest", type=Path, default=LOCAL_MANIFEST)
    commands.add_parser("mapping-reconcile", parents=[common])
    configure = commands.add_parser("configure-vm", parents=[common])
    configure.add_argument("--vmid", required=True, type=int)
    configure.add_argument("--expect-current-vm", required=True)
    configure.add_argument("--expect-mac", required=True)
    configure.add_argument("--confirm-destroy", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.action == "check":
            check_action(args)
        elif args.action == "install":
            install_alias(args)
        elif args.action == "mapping-reconcile":
            mapping_action(args)
        elif args.action == "configure-vm":
            configure_vm_action(args)
        else:
            raise Refusal(f"unsupported action {args.action}")
    except Refusal as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

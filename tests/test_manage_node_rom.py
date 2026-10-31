#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/manage-node-rom.py"
SPEC = importlib.util.spec_from_file_location("manage_node_rom", MODULE_PATH)
assert SPEC and SPEC.loader
rom_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rom_manager)


def write_rom(path: Path, vendor: int = 0x8086, device: int = 0x46A6) -> None:
    data = bytearray(512)
    data[0:2] = b"\x55\xaa"
    struct.pack_into("<H", data, 0x18, 0x20)
    data[0x20:0x24] = b"PCIR"
    struct.pack_into("<HH", data, 0x24, vendor, device)
    struct.pack_into("<H", data, 0x30, 1)
    data[0x35] = 0x80
    path.write_bytes(data)


class NodeRomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pci = self.root / "pci"
        self.roms = self.root / "roms"
        self.roms.mkdir()
        device = self.pci / "0000:00:02.0"
        device.mkdir(parents=True)
        (device / "vendor").write_text("0x8086\n")
        (device / "device").write_text("0x46a6\n")
        (device / "subsystem_vendor").write_text("0x0000\n")
        (device / "subsystem_device").write_text("0x0000\n")
        group = self.root / "iommu_groups/0"
        (group / "devices").mkdir(parents=True)
        (group / "devices/0000:00:02.0").symlink_to(device)
        (device / "iommu_group").symlink_to(group)
        self.source = self.root / "source.rom"
        write_rom(self.source)
        digest = rom_manager.sha256_file(self.source)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "alias": "ms01-igd-current.rom",
                    "mapping_id": "MS01-IGD",
                    "igd_path": "0000:00:02.0",
                    "profiles": [
                        {
                            "name": "test",
                            "status": "qualified",
                            "pci_id": "8086:46a6",
                            "rom": f"test-8086-46a6-{digest[:12]}.rom",
                            "source": "source.rom",
                            "sha256": digest,
                            "bytes": 512,
                        }
                    ],
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def args(self):
        return type(
            "Args",
            (),
            {
                "manifest": self.manifest,
                "rom_root": self.roms,
                "pci_root": self.pci,
                "rom": self.source,
                "local_manifest": None,
                "allow_candidate": False,
            },
        )()

    def test_install_and_verify_relative_alias(self) -> None:
        rom_manager.install_alias(self.args())
        alias = self.roms / "ms01-igd-current.rom"
        self.assertTrue(alias.is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(alias)))
        profile, group, subsystem = rom_manager.verify_node(
            self.manifest, self.roms, self.pci
        )
        self.assertEqual(profile["pci_id"], "8086:46a6")
        self.assertEqual((group, subsystem), ("0", "0000:0000"))

    def test_unknown_live_device_id_is_refused(self) -> None:
        (self.pci / "0000:00:02.0/device").write_text("0xa721\n")
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.install_alias(self.args())

    def test_nonisolated_group_is_refused(self) -> None:
        extra = self.root / "iommu_groups/0/devices/0000:00:00.0"
        extra.symlink_to(self.pci / "0000:00:02.0")
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.install_alias(self.args())

    def test_alias_escape_is_refused(self) -> None:
        outside = self.root / "outside.rom"
        write_rom(outside)
        (self.roms / "ms01-igd-current.rom").symlink_to(outside)
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.verify_node(
                self.manifest, self.roms, self.pci
            )

    def test_wrong_pcir_identity_is_refused(self) -> None:
        write_rom(self.source, device=0xA720)
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.install_alias(self.args())

    def test_candidate_requires_explicit_staging_and_fails_admission_check(self) -> None:
        data = json.loads(self.manifest.read_text())
        data["profiles"][0]["status"] = "candidate"
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.install_alias(self.args())
        args = self.args()
        args.allow_candidate = True
        rom_manager.install_alias(args)
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.verify_node(
                self.manifest, self.roms, self.pci
            )

    def test_mapping_entry_parser_is_order_independent(self) -> None:
        parsed = rom_manager.parse_mapping_entry(
            "id=8086:a720,iommugroup=0,node=pve-s1390,"
            "path=0000:00:02.0,subsystem-id=0000:0000"
        )
        self.assertEqual(parsed["node"], "pve-s1390")
        self.assertEqual(parsed["id"], "8086:a720")
        self.assertEqual(parsed["iommugroup"], "0")

    def test_repository_manifest_sources_match_recorded_artifacts(self) -> None:
        repository = MODULE_PATH.parents[1]
        manifest = rom_manager.load_manifest(repository / "roms/node-rom-manifest.json")
        for profile in manifest["profiles"]:
            with self.subTest(profile=profile["name"]):
                source = repository / "roms" / profile["source"]
                self.assertTrue(source.is_file())
                self.assertEqual(source.stat().st_size, profile["bytes"])
                self.assertEqual(rom_manager.sha256_file(source), profile["sha256"])
                self.assertTrue(profile["rom"].endswith(f"-{profile['sha256'][:12]}.rom"))
                self.assertTrue(
                    all(
                        identity == profile["pci_id"]
                        for identity in rom_manager.pcir_identities(source)
                    )
                )

    def test_published_profiles_cover_previously_qualified_models(self) -> None:
        manifest = rom_manager.load_manifest(
            MODULE_PATH.parents[1] / "roms/node-rom-manifest.json"
        )
        expected = {
            "8086:46a6": "ms01-s1260",
            "8086:4626": "ms01-s1290",
            "8086:a720": "ms01-s1390",
        }
        for pci_id, name in expected.items():
            with self.subTest(pci_id=pci_id):
                profile = rom_manager.select_profile(manifest, pci_id)
                self.assertEqual(profile["name"], name)
                self.assertEqual(profile["status"], "qualified")

    def test_similar_model_does_not_authorize_unqualified_pci_id(self) -> None:
        manifest = rom_manager.load_manifest(
            MODULE_PATH.parents[1] / "roms/node-rom-manifest.json"
        )
        with self.assertRaises(rom_manager.Refusal):
            rom_manager.select_profile(manifest, "8086:a7a0")


if __name__ == "__main__":
    unittest.main()

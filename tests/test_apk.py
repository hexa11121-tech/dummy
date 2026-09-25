import os
import tempfile
import unittest

from tests.fixtures import build_test_apk
from apkdeco.core.apk import (ApkError, ApkFile, classify_entry,
                              GROUP_ARSC, GROUP_ASSETS, GROUP_DEX, GROUP_LIB,
                              GROUP_MANIFEST, GROUP_META, GROUP_OTHER, GROUP_RES)


class ClassifyTest(unittest.TestCase):
    def test_groups(self):
        self.assertEqual(classify_entry("AndroidManifest.xml"), GROUP_MANIFEST)
        self.assertEqual(classify_entry("resources.arsc"), GROUP_ARSC)
        self.assertEqual(classify_entry("classes.dex"), GROUP_DEX)
        self.assertEqual(classify_entry("classes2.dex"), GROUP_DEX)
        self.assertEqual(classify_entry("res/layout/main.xml"), GROUP_RES)
        self.assertEqual(classify_entry("assets/x.txt"), GROUP_ASSETS)
        self.assertEqual(classify_entry("lib/arm64-v8a/lib.so"), GROUP_LIB)
        self.assertEqual(classify_entry("META-INF/MANIFEST.MF"), GROUP_META)
        self.assertEqual(classify_entry("kotlin/kotlin.kotlin_builtins"), GROUP_OTHER)


class ApkFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = build_test_apk(os.path.join(self.dir.name, "test.apk"))
        self.apk = ApkFile(self.path)

    def tearDown(self):
        self.apk.close()
        self.dir.cleanup()

    def test_listing(self):
        names = self.apk.names()
        self.assertIn("AndroidManifest.xml", names)
        self.assertIn("classes.dex", names)
        self.assertIn("resources.arsc", names)
        self.assertEqual(self.apk.name, "test.apk")

    def test_manifest_pretty(self):
        text = self.apk.manifest_pretty()
        self.assertIn("com.example.test", text)
        self.assertIn("android.permission.INTERNET", text)

    def test_manifest_summary(self):
        s = self.apk.manifest_summary()
        self.assertEqual(s["package"], "com.example.test")
        self.assertEqual(s["versionName"], "1.2.3")
        self.assertEqual(s["permissions"], ["android.permission.INTERNET"])

    def test_resources_and_dex(self):
        res = self.apk.resources
        self.assertIsNotNone(res)
        self.assertIn("Hello, APKDeco!", res.global_strings)
        dex = self.apk.dex("classes.dex")
        self.assertEqual(dex.info.class_count, 1)

    def test_text_preview(self):
        t = self.apk.text_preview("assets/config.json")
        self.assertIn("debug", t)

    def test_hex_preview(self):
        b = self.apk.hex_preview("lib/arm64-v8a/libnative.so")
        self.assertTrue(b.startswith(b"\x7fELF"))

    def test_missing_entry(self):
        with self.assertRaises(ApkError):
            self.apk.read("nope.bin")

    def test_not_a_zip(self):
        p = os.path.join(self.dir.name, "bad.apk")
        with open(p, "wb") as f:
            f.write(b"this is not a zip")
        with self.assertRaises(ApkError):
            ApkFile(p)


if __name__ == "__main__":
    unittest.main()

import struct
import unittest

from tests.fixtures import build_axml_document, build_string_pool
from apkdeco.core.axml import (AxmlError, manifest_summary, parse_axml,
                               ResValue, TYPE_INT_DEC, TYPE_REFERENCE,
                               _decode_string_pool)
from apkdeco.core.blob import BlobReader


class StringPoolTest(unittest.TestCase):
    def test_utf16_pool(self):
        data = build_string_pool(["hello", "", "wörld", "x" * 100])
        strings = _decode_string_pool(BlobReader(data))
        self.assertEqual(strings, ["hello", "", "wörld", "x" * 100])

    def test_utf8_pool(self):
        data = build_string_pool(["abc", "héllo"], utf8=True)
        strings = _decode_string_pool(BlobReader(data))
        self.assertEqual(strings, ["abc", "héllo"])

    def test_long_utf16_length(self):
        big = "y" * 70000  # forces the two-word length encoding
        data = build_string_pool([big])
        strings = _decode_string_pool(BlobReader(data))
        self.assertEqual(strings[0], big)

    def test_long_utf8_length(self):
        big = "z" * 300  # forces extended 8-bit length encoding
        data = build_string_pool([big], utf8=True)
        strings = _decode_string_pool(BlobReader(data))
        self.assertEqual(strings[0], big)


class AxmlTest(unittest.TestCase):
    def test_manifest_shape(self):
        data = build_axml_document(
            elements=[
                ("uses-permission", [("name", "android.permission.INTERNET")]),
                ("application", [("label", "@string/app_name"),
                                 ("debuggable", "true")]),
            ],
            root_attrs=[("package", "com.example.test"),
                        ("versionName", "1.2.3")],
        )
        doc = parse_axml(data)
        root = doc.root
        self.assertEqual(root.name, "manifest")
        self.assertEqual(root.get("package"), "com.example.test")
        self.assertEqual(len(root.children), 2)
        perm = root.children[0]
        self.assertEqual(perm.name, "uses-permission")
        self.assertEqual(perm.get("name"), "android.permission.INTERNET")
        app = root.children[1]
        self.assertEqual(app.get("label"), "@string/app_name")
        self.assertEqual(app.get("debuggable"), "true")

    def test_pretty_xml(self):
        data = build_axml_document(
            elements=[("uses-permission", [("name", "android.permission.INTERNET")])],
            root_attrs=[("package", "com.example.test")],
        )
        xml = parse_axml(data).pretty_xml()
        self.assertIn('<?xml version="1.0"', xml)
        self.assertIn("<manifest", xml)
        self.assertIn('android:name="android.permission.INTERNET"', xml)
        self.assertIn('package="com.example.test"', xml)
        self.assertIn("</manifest>", xml)

    def test_summary(self):
        data = build_axml_document(
            elements=[
                ("uses-permission", [("name", "android.permission.INTERNET")]),
                ("uses-permission", [("name", "android.permission.CAMERA")]),
                ("uses-sdk", [("minSdkVersion", "21"), ("targetSdkVersion", "34")]),
                ("application", [("label", "App")]),
            ],
            root_attrs=[("package", "com.example.test"),
                        ("versionName", "1.2.3"), ("versionCode", "42")],
        )
        s = manifest_summary(parse_axml(data).root)
        self.assertEqual(s["package"], "com.example.test")
        self.assertEqual(s["versionName"], "1.2.3")
        self.assertEqual(s["versionCode"], "42")
        self.assertEqual(s["permissions"],
                         ["android.permission.CAMERA", "android.permission.INTERNET"])
        self.assertEqual(s["sdk"], {"minSdkVersion": "21", "targetSdkVersion": "34"})

    def test_rejects_garbage(self):
        with self.assertRaises(AxmlError):
            parse_axml(b"\x00" * 32)

    def test_resolver_hook(self):
        # reference-typed attr goes through the resolver callback
        v = ResValue(TYPE_REFERENCE, 0x7F010001)
        self.assertEqual(v.format(resolver=lambda i: "@string/app_name"),
                         "@string/app_name")
        self.assertEqual(v.format(), "@0x7f010001")
        self.assertEqual(ResValue(TYPE_INT_DEC, 30).format(), "30")
        self.assertEqual(ResValue(TYPE_INT_DEC, 0xFFFFFFFE).format(), "-2")


if __name__ == "__main__":
    unittest.main()

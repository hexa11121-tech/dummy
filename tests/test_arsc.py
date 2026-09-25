import unittest

from tests.fixtures import build_arsc_minimal
from apkdeco.core.arsc import parse_arsc, ResourcesError


class ArscTest(unittest.TestCase):
    def setUp(self):
        self.data, self.ids = build_arsc_minimal()
        self.table = parse_arsc(self.data)

    def test_package(self):
        self.assertEqual(len(self.table.packages), 1)
        pkg = self.table.packages[0]
        self.assertEqual(pkg.id, 0x7F)
        self.assertEqual(pkg.name, "com.example.test")

    def test_res_names(self):
        self.assertEqual(self.table.res_name(self.ids["hello"]), "@string/hello")
        self.assertEqual(self.table.res_name(self.ids["app_name"]), "@string/app_name")
        self.assertIsNone(self.table.res_name(0x7F099999))

    def test_display_values(self):
        self.assertEqual(self.table.display_value(self.ids["hello"]),
                         "Hello, APKDeco!")
        self.assertEqual(self.table.display_value(self.ids["app_name"]),
                         "APKDeco Test")
        self.assertIsNone(self.table.display_value(0x12345678))

    def test_lookup(self):
        e = self.table.lookup(self.ids["app_name"])
        self.assertIsNotNone(e)
        self.assertEqual(e.key, "app_name")
        self.assertEqual(e.type_name, "string")

    def test_global_strings(self):
        self.assertIn("Hello, APKDeco!", self.table.global_strings)

    def test_rejects_garbage(self):
        with self.assertRaises(ResourcesError):
            parse_arsc(b"\x00" * 16)

    def test_stats(self):
        s = self.table.stats()
        self.assertIn("com.example.test", s)
        self.assertIn("2 resource entries", s)


if __name__ == "__main__":
    unittest.main()

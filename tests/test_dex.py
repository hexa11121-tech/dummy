import unittest

from tests.fixtures import build_dex_minimal
from apkdeco.core.dex import (DexFile, access_flags_str, split_proto, type_name)


class DexTest(unittest.TestCase):
    def setUp(self):
        self.dex = DexFile(build_dex_minimal(), name="classes.dex")

    def test_header(self):
        i = self.dex.info
        self.assertEqual(i.dex_version, "035")
        self.assertEqual(i.class_count, 1)
        self.assertEqual(i.method_count, 1)
        self.assertEqual(i.field_count, 1)
        self.assertEqual(i.string_count, 13)
        self.assertEqual(i.type_count, 7)

    def test_strings(self):
        self.assertIn("Lcom/example/Main;", self.dex.strings)
        self.assertIn("hello wörld ✓", self.dex.strings)

    def test_classes(self):
        self.assertEqual(len(self.dex.classes), 1)
        c = self.dex.classes[0]
        self.assertEqual(c.name, "com.example.Main")
        self.assertEqual(c.super_name, "Ljava/lang/Object;")
        self.assertEqual(c.interfaces, ["Lcom/example/IFace;"])
        self.assertEqual(c.source_file, "Main.java")
        self.assertEqual(len(c.fields), 1)
        self.assertEqual(c.fields[0].name, "hello")
        self.assertIn("private int hello", c.fields[0].signature())
        self.assertEqual(len(c.methods), 1)
        m = c.methods[0]
        self.assertEqual(m.name, "main")
        sig = m.signature()
        self.assertIn("public static void main(", sig)
        self.assertIn("java.lang.String[]", sig)

    def test_info_text(self):
        t = self.dex.info_text()
        self.assertIn("DEX version", t)
        self.assertIn("classes.dex", t)

    def test_bad_magic(self):
        with self.assertRaises(ValueError):
            DexFile(b"NOTDEX!" + b"\x00" * 200)


class HelpersTest(unittest.TestCase):
    def test_type_name(self):
        self.assertEqual(type_name("I"), "int")
        self.assertEqual(type_name("V"), "void")
        self.assertEqual(type_name("[I"), "int[]")
        self.assertEqual(type_name("[[Ljava/lang/String;"), "java.lang.String[][]")
        self.assertEqual(type_name("Ljava/lang/Object;"), "java.lang.Object")

    def test_split_proto(self):
        ret, params = split_proto("(ILjava/lang/String;)V")
        self.assertEqual(ret, "V")
        self.assertEqual(params, ["I", "Ljava/lang/String;"])
        ret, params = split_proto("()V")
        self.assertEqual(params, [])

    def test_access_flags(self):
        self.assertEqual(access_flags_str(0x9), "public static")
        self.assertIn("interface", access_flags_str(0x200))


if __name__ == "__main__":
    unittest.main()

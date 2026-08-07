import unittest

from scripts.migrate_firebase_user_to_clerk import firebase_password_digest


class ClerkMigrationTests(unittest.TestCase):
    def test_firebase_password_digest_uses_clerk_scrypt_format(self):
        digest = firebase_password_digest(
            {"passwordHash": "hash", "salt": "salt"},
            signer_key="signer",
            salt_separator="separator",
            rounds="8",
            memory_cost="14",
        )
        self.assertEqual(digest, "hash$salt$signer$separator$8$14")

    def test_incomplete_password_hash_fails_closed(self):
        with self.assertRaises(ValueError):
            firebase_password_digest(
                {"passwordHash": "hash", "salt": ""},
                signer_key="signer",
                salt_separator="separator",
                rounds="8",
                memory_cost="14",
            )


if __name__ == "__main__":
    unittest.main()

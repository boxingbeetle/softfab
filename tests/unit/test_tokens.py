# SPDX-License-Identifier: BSD-3-Clause

import unittest

from twisted.cred.error import UnauthorizedLogin

from initconfig import removeDB

from softfab import databases, tokens


class TestTokens(unittest.TestCase):
    """Test access tokens."""

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def reloadDatabases(self):
        databases.reloadDatabases()

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeDB()

    def test0100Params(self):
        """Test token parameters."""

        params = {'PARAM1': '12345', 'PARAM2': 'a b c'}
        token = tokens.Token.create(tokens.TokenRole.RESOURCE, params)
        tokens.tokenDB.add(token)
        tokenId = token.getId()

        def checkParams():
            self.assertEqual(token.getParam('PARAM1'), '12345')
            self.assertEqual(token.getParam('PARAM2'), 'a b c')

        checkParams()

        params['PARAM1'] = '67890'
        del params['PARAM2']
        checkParams()

        self.reloadDatabases()
        token = tokens.tokenDB[tokenId]
        checkParams()

    def test0200Auth(self):
        """Test token authentication."""

        tokenDB = tokens.tokenDB

        token = tokens.Token.create(tokens.TokenRole.RESOURCE, {})
        tokenDB.add(token)
        tokenId = token.getId()

        # Non-existing token.
        with self.assertRaises(KeyError):
            tokens.authenticateToken(tokenDB, 'nosuchtoken', 'letmein')

        # Existing token with no password set.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenDB, tokenId, 'letmein')

        password1 = tokens.resetTokenPassword(tokenDB, token)

        # Existing token with wrong password.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenDB, tokenId, 'letmein')

        # Existing token with correct password.
        token1 = tokens.authenticateToken(tokenDB, tokenId, password1)
        self.assertEqual(token1.getId(), tokenId)

        password2 = tokens.resetTokenPassword(tokenDB, token)
        self.assertNotEqual(password1, password2)

        # Existing token with old password.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenDB, tokenId, password1)

        # Existing token with new password.
        token2 = tokens.authenticateToken(tokenDB, tokenId, password2)
        self.assertEqual(token2.getId(), tokenId)

        self.reloadDatabases()
        tokenDB = tokens.tokenDB

        # Existing token with new password.
        token3 = tokens.authenticateToken(tokenDB, tokenId, password2)
        self.assertEqual(token3.getId(), tokenId)

if __name__ == '__main__':
    unittest.main()

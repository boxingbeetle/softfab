# SPDX-License-Identifier: BSD-3-Clause

import unittest

from twisted.cred.error import UnauthorizedLogin

from initconfig import config

from softfab import databases, tokens
from datageneratorlib import removeRec

class TestTokens(unittest.TestCase):
    """Test access tokens."""

    def __init__(self, methodName = 'runTest'):
        unittest.TestCase.__init__(self, methodName)

    def reloadDatabases(self):
        databases.reloadDatabases()

    def setUp(self):
        self.reloadDatabases()

    def tearDown(self):
        removeRec(config.dbDir)

    def test0100Params(self):
        """Test token parameters."""

        params = {'PARAM1': '12345', 'PARAM2': 'a b c'}
        token = tokens.Token.create(tokens.TokenRole.RESOURCE, params)

        def checkParams():
            self.assertEqual(token.getParam('PARAM1'), '12345')
            self.assertEqual(token.getParam('PARAM2'), 'a b c')

        checkParams()

        params['PARAM1'] = '67890'
        del params['PARAM2']
        checkParams()

        self.reloadDatabases()
        checkParams()

    def test0200Auth(self):
        """Test token authentication."""

        token = tokens.Token.create(tokens.TokenRole.RESOURCE, {})
        tokenId = token.getId()

        # Non-existing token.
        with self.assertRaises(KeyError):
            tokens.authenticateToken('nosuchtoken', 'letmein')

        # Existing token with no password set.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenId, 'letmein')

        password1 = token.resetPassword()

        # Existing token with wrong password.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenId, 'letmein')

        # Existing token with correct password.
        token1 = tokens.authenticateToken(tokenId, password1)
        self.assertEqual(token1.getId(), tokenId)

        password2 = token.resetPassword()
        self.assertNotEqual(password1, password2)

        # Existing token with old password.
        with self.assertRaises(UnauthorizedLogin):
            tokens.authenticateToken(tokenId, password1)

        # Existing token with new password.
        token2 = tokens.authenticateToken(tokenId, password2)
        self.assertEqual(token2.getId(), tokenId)

        self.reloadDatabases()

        # Existing token with new password.
        token3 = tokens.authenticateToken(tokenId, password2)
        self.assertEqual(token3.getId(), tokenId)

if __name__ == '__main__':
    unittest.main()

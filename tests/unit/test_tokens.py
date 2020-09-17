# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path

from pytest import fixture, raises
from twisted.cred.error import UnauthorizedLogin

from softfab.timelib import setTime
from softfab.tokens import (
    Token, TokenDB, TokenRole, authenticateToken, resetTokenPassword
)
from softfab.users import Credentials


@fixture
def tokenDB(tmp_path):
    db = TokenDB(tmp_path)
    db.preload()
    return db

def reloadDB(db):
    db = db.__class__(Path(db.baseDir))
    db.preload()
    return db

def testTokenParams(tokenDB):
    """Test token parameters."""

    params = {'PARAM1': '12345', 'PARAM2': 'a b c'}
    token = Token.create(TokenRole.RESOURCE, params)
    tokenDB.add(token)
    tokenId = token.getId()

    def checkParams():
        assert token.getParam('PARAM1') == '12345'
        assert token.getParam('PARAM2') == 'a b c'

    checkParams()

    params['PARAM1'] = '67890'
    del params['PARAM2']
    checkParams()

    tokenDB = reloadDB(tokenDB)
    token = tokenDB[tokenId]
    checkParams()

def testTokenAuth(tokenDB):
    """Test token authentication."""

    token = Token.create(TokenRole.RESOURCE, {})
    tokenDB.add(token)
    tokenId = token.getId()

    # Non-existing token.
    with raises(KeyError):
        authenticateToken(tokenDB, Credentials('nosuchtoken', 'letmein'))

    # Existing token with no password set.
    with raises(UnauthorizedLogin):
        authenticateToken(tokenDB, Credentials(tokenId, 'letmein'))

    password1 = resetTokenPassword(tokenDB, token)

    # Existing token with wrong password.
    with raises(UnauthorizedLogin):
        authenticateToken(tokenDB, Credentials(tokenId, 'letmein'))

    # Existing token with correct password.
    token1 = authenticateToken(tokenDB, Credentials(tokenId, password1))
    assert token1.getId() == tokenId

    password2 = resetTokenPassword(tokenDB, token)
    assert password1 != password2

    # Existing token with old password.
    with raises(UnauthorizedLogin):
        authenticateToken(tokenDB, Credentials(tokenId, password1))

    # Existing token with new password.
    token2 = authenticateToken(tokenDB, Credentials(tokenId, password2))
    assert token2.getId() == tokenId

    tokenDB = reloadDB(tokenDB)

    # Existing token with new password.
    token3 = authenticateToken(tokenDB, Credentials(tokenId, password2))
    assert token3.getId() == tokenId

def testTokenExpiry(tokenDB):
    """Test token expiry."""

    setTime(12000000)
    token = Token.create(TokenRole.RESOURCE, {}, expireSecs=345678)
    assert not token.expired
    tokenDB.add(token)
    tokenId = token.getId()

    def check():
        assert token.createTime == 12000000
        assert token.expireTime == 12345678
        setTime(12340000)
        assert not token.expired
        setTime(20000000)
        assert token.expired
        setTime(12345677)
        assert not token.expired
        setTime(12345678)
        assert token.expired

    check()
    tokenDB = reloadDB(tokenDB)
    token = tokenDB[tokenId]
    check()

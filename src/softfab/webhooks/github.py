# SPDX-License-Identifier: BSD-3-Clause

from typing import Any, Iterator
import hmac

from twisted.web.http import Request as TwistedRequest


def isRelevantEvent(request: TwistedRequest) -> bool:
    return request.getHeader('X-GitHub-Event') == 'push'

def verifySignature(request: TwistedRequest,
                    payload: bytes,
                    secret: bytes
                    ) -> bool:
    sigHeader = request.getHeader('X-Hub-Signature')
    if not sigHeader:
        return False
    try:
        hashName, remoteSig = sigHeader.split('=', 1)
    except ValueError:
        return False
    if hashName != 'sha1':
        # Only accept the SHA1 hash function that GitHub currently uses.
        return False
    localSig = hmac.new(secret, payload, hashName).hexdigest()
    return hmac.compare_digest(localSig.casefold(), remoteSig.casefold())

def findRepositoryURLs(json: Any) -> Iterator[str]:
    repo = json['repository']
    yield repo['clone_url']
    yield repo['git_url']
    yield repo['ssh_url']

def findBranches(json: Any) -> Iterator[str]:
    ref = json['ref']
    if ref.startswith('refs/heads/'):
        yield ref[len('refs/heads/'):]

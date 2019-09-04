# SPDX-License-Identifier: BSD-3-Clause

import json
import unittest

from softfab.webhooks import gogs


class TestWebhookGogs(unittest.TestCase):
    """Test the webhook used by Gogs."""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)

    def testGogsPushIsRelevant(self):
        """Check whether event is relevant."""
        self.assertFalse(gogs.isRelevantEvent(emptyHeaders))
        self.assertTrue(gogs.isRelevantEvent(pushHeadersGogs))
        self.assertFalse(gogs.isRelevantEvent(
            pushHeadersGogs.replace('X-Gogs-Event', 'beep')
            ))

    def testGogsPushVerifySignature(self):
        """Check signature."""
        self.assertFalse(gogs.verifySignature(
            emptyHeaders, pushBodyGogs, b'12345'
            ))
        self.assertFalse(gogs.verifySignature(
            pushHeadersGogs, pushBodyGogs, b'12345'
            ))
        self.assertTrue(gogs.verifySignature(
            pushHeadersGogs, pushBodyGogs, b'letmein'
            ))

    def testGogsPushFindRepo(self):
        """Find repository URLs in JSON body."""
        payload = json.loads(pushBodyGogs)
        urls = sorted(gogs.findRepositoryURLs(payload))
        self.assertEqual(urls, [
            'gogs@git.boxingbeetle.com:maarten/webhook-test.git',
            'https://git.boxingbeetle.com/maarten/webhook-test.git'
            ])

    def testGogsPushFindBranches(self):
        """Find branch name in JSON body."""
        payload = json.loads(pushBodyGogs)
        branches = sorted(gogs.findBranches(payload))
        self.assertEqual(branches, ['master'])

class Headers:

    def __init__(self, mapping):
        self.mapping = {
            name.casefold(): value
            for name, value in mapping.items()
            }

    def getHeader(self, name):
        return self.mapping.get(name.casefold())

    def replace(self, name, value):
        mapping = dict(self.mapping)
        mapping[name] = value
        return Headers(mapping)

emptyHeaders = Headers({})

pushHeadersGogs = Headers({
    'User-Agent': 'GogsServer',
    'Content-Type': 'application/json',
    'X-Gogs-Delivery': 'cc2fdc56-d5a8-47c6-ba22-5a090ce6e5ae',
    'X-Gogs-Event': 'push',
    'X-Gogs-Signature':
        'c6d8a1e113602376042ccb5c6743026afd9dd1227d1207146b518109c8a2305e',
    })

pushBodyGogs = rb'''
{
  "ref": "refs/heads/master",
  "before": "bfb216870407953f6edbe4471e8e35168847951a",
  "after": "0991f94731e43c58d08a3facbb6e223c5e548f38",
  "compare_url": "https://git.boxingbeetle.com/maarten/webhook-test/compare/bfb216870407953f6edbe4471e8e35168847951a...0991f94731e43c58d08a3facbb6e223c5e548f38",
  "commits": [
    {
      "id": "0991f94731e43c58d08a3facbb6e223c5e548f38",
      "message": "Update README\n",
      "url": "https://git.boxingbeetle.com/maarten/webhook-test/commit/0991f94731e43c58d08a3facbb6e223c5e548f38",
      "author": {
        "name": "Maarten ter Huurne",
        "email": "maarten@boxingbeetle.com",
        "username": "maarten"
      },
      "committer": {
        "name": "Maarten ter Huurne",
        "email": "maarten@boxingbeetle.com",
        "username": "maarten"
      },
      "added": [],
      "removed": [],
      "modified": [
        "README.md"
      ],
      "timestamp": "2019-09-02T16:49:34Z"
    }
  ],
  "repository": {
    "id": 6,
    "owner": {
      "id": 1,
      "username": "maarten",
      "login": "maarten",
      "full_name": "",
      "email": "maarten@boxingbeetle.com",
      "avatar_url": "https://git.boxingbeetle.com/avatars/1"
    },
    "name": "webhook-test",
    "full_name": "maarten/webhook-test",
    "description": "Repository for testing webhooks, no useful content",
    "private": false,
    "fork": false,
    "parent": null,
    "empty": false,
    "mirror": false,
    "size": 24576,
    "html_url": "https://git.boxingbeetle.com/maarten/webhook-test",
    "ssh_url": "gogs@git.boxingbeetle.com:maarten/webhook-test.git",
    "clone_url": "https://git.boxingbeetle.com/maarten/webhook-test.git",
    "website": "",
    "stars_count": 0,
    "forks_count": 0,
    "watchers_count": 1,
    "open_issues_count": 0,
    "default_branch": "master",
    "created_at": "2019-09-02T16:44:12Z",
    "updated_at": "2019-09-02T16:44:13Z"
  },
  "pusher": {
    "id": 1,
    "username": "maarten",
    "login": "maarten",
    "full_name": "",
    "email": "maarten@boxingbeetle.com",
    "avatar_url": "https://git.boxingbeetle.com/avatars/1"
  },
  "sender": {
    "id": 1,
    "username": "maarten",
    "login": "maarten",
    "full_name": "",
    "email": "maarten@boxingbeetle.com",
    "avatar_url": "https://git.boxingbeetle.com/avatars/1"
  }
}
'''.strip()

if __name__ == '__main__':
    unittest.main()

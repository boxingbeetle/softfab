# SPDX-License-Identifier: BSD-3-Clause

import json
import unittest

from softfab.webhooks import WebhookEvents, github, gogs


class TestWebhookGogs(unittest.TestCase):
    """Test the webhook used by Gogs."""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)

    def testGogsPushType(self):
        """Check whether a push event is identified as such."""
        self.assertEqual(
            gogs.getEvent(emptyHeaders),
            WebhookEvents.UNSUPPORTED
            )
        self.assertEqual(
            gogs.getEvent(pushHeadersGogs),
            WebhookEvents.PUSH
            )
        self.assertEqual(
            gogs.getEvent(pushHeadersGogs.replace('X-Gogs-Event', 'beep')),
            WebhookEvents.UNSUPPORTED
            )

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

class TestWebhookGitHub(unittest.TestCase):
    """Test the webhook used by GitHub."""

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName)

    def testGitHubPushType(self):
        """Check whether a push event is identified as such."""
        self.assertEqual(
            github.getEvent(emptyHeaders),
            WebhookEvents.UNSUPPORTED
            )
        self.assertEqual(
            github.getEvent(pushHeadersGitHub),
            WebhookEvents.PUSH
            )
        self.assertEqual(
            github.getEvent(pushHeadersGitHub.replace('X-GitHub-Event', 'beep')),
            WebhookEvents.UNSUPPORTED
            )

    def testGitHubPushVerifySignature(self):
        """Check signature."""
        self.assertFalse(github.verifySignature(
            emptyHeaders, pushBodyGitHub, b'12345'
            ))
        self.assertFalse(github.verifySignature(
            pushHeadersGitHub, pushBodyGitHub, b'12345'
            ))
        self.assertTrue(github.verifySignature(
            pushHeadersGitHub, pushBodyGitHub, b'letmein'
            ))

    def testGitHubPushFindRepo(self):
        """Find repository URLs in JSON body."""
        payload = json.loads(pushBodyGitHub)
        urls = sorted(github.findRepositoryURLs(payload))
        self.assertEqual(urls, [
            'git://github.com/boxingbeetle/webhook-test.git',
            'git@github.com:boxingbeetle/webhook-test.git',
            'https://github.com/boxingbeetle/webhook-test.git'
            ])

    def testGitHubPushFindBranches(self):
        """Find branch name in JSON body."""
        payload = json.loads(pushBodyGitHub)
        branches = sorted(github.findBranches(payload))
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

pushHeadersGitHub = Headers({
    'User-Agent': 'GitHub-Hookshot/a5788b1',
    'X-Github-Event': 'push',
    'X-Github-Delivery': 'c53b7bda-cf25-11e9-9fa8-9f1a19ef7c29',
    'Content-Type': 'application/json',
    'X-Hub-Signature': 'sha1=5c8a6cbebf4c136d07aada4f21bd1c4d18030b6e',
    })

pushBodyGitHub = rb'''
{"commits":[{"id":"6493f6550a7feb0fbbe1c933d02899dd8a2cc42e","tree_id":"2f962eb8a4e4e00b27e73005f1ca0b07d73ba0a2","distinct":true,"message":"Update README","timestamp":"2019-09-04T17:07:39+02:00","url":"https://github.com/boxingbeetle/webhook-test/commit/6493f6550a7feb0fbbe1c933d02899dd8a2cc42e","author":{"name":"Maarten ter Huurne","email":"maarten@boxingbeetle.com","username":"mthuurne"},"committer":{"name":"Maarten ter Huurne","email":"maarten@boxingbeetle.com","username":"mthuurne"},"added":[],"removed":[],"modified":["README.md"]}],"head_commit":{"id":"6493f6550a7feb0fbbe1c933d02899dd8a2cc42e","tree_id":"2f962eb8a4e4e00b27e73005f1ca0b07d73ba0a2","distinct":true,"message":"Update README","timestamp":"2019-09-04T17:07:39+02:00","url":"https://github.com/boxingbeetle/webhook-test/commit/6493f6550a7feb0fbbe1c933d02899dd8a2cc42e","author":{"name":"Maarten ter Huurne","email":"maarten@boxingbeetle.com","username":"mthuurne"},"committer":{"name":"Maarten ter Huurne","email":"maarten@boxingbeetle.com","username":"mthuurne"},"added":[],"removed":[],"modified":["README.md"]},"ref":"refs/heads/master","before":"5c1817b2df65ad4a3ac3ad06c530649b7e044d5c","after":"6493f6550a7feb0fbbe1c933d02899dd8a2cc42e","created":false,"deleted":false,"forced":false,"base_ref":null,"compare":"https://github.com/boxingbeetle/webhook-test/compare/5c1817b2df65...6493f6550a7f","repository":{"id":204648295,"node_id":"MDEwOlJlcG9zaXRvcnkyMDQ2NDgyOTU=","name":"webhook-test","full_name":"boxingbeetle/webhook-test","private":false,"owner":{"name":"boxingbeetle","email":null,"login":"boxingbeetle","id":46841979,"node_id":"MDEyOk9yZ2FuaXphdGlvbjQ2ODQxOTc5","avatar_url":"https://avatars0.githubusercontent.com/u/46841979?v=4","gravatar_id":"","url":"https://api.github.com/users/boxingbeetle","html_url":"https://github.com/boxingbeetle","followers_url":"https://api.github.com/users/boxingbeetle/followers","following_url":"https://api.github.com/users/boxingbeetle/following{/other_user}","gists_url":"https://api.github.com/users/boxingbeetle/gists{/gist_id}","starred_url":"https://api.github.com/users/boxingbeetle/starred{/owner}{/repo}","subscriptions_url":"https://api.github.com/users/boxingbeetle/subscriptions","organizations_url":"https://api.github.com/users/boxingbeetle/orgs","repos_url":"https://api.github.com/users/boxingbeetle/repos","events_url":"https://api.github.com/users/boxingbeetle/events{/privacy}","received_events_url":"https://api.github.com/users/boxingbeetle/received_events","type":"Organization","site_admin":false},"html_url":"https://github.com/boxingbeetle/webhook-test","description":"Repository for testing webhooks, no useful content","fork":false,"url":"https://github.com/boxingbeetle/webhook-test","forks_url":"https://api.github.com/repos/boxingbeetle/webhook-test/forks","keys_url":"https://api.github.com/repos/boxingbeetle/webhook-test/keys{/key_id}","collaborators_url":"https://api.github.com/repos/boxingbeetle/webhook-test/collaborators{/collaborator}","teams_url":"https://api.github.com/repos/boxingbeetle/webhook-test/teams","hooks_url":"https://api.github.com/repos/boxingbeetle/webhook-test/hooks","issue_events_url":"https://api.github.com/repos/boxingbeetle/webhook-test/issues/events{/number}","events_url":"https://api.github.com/repos/boxingbeetle/webhook-test/events","assignees_url":"https://api.github.com/repos/boxingbeetle/webhook-test/assignees{/user}","branches_url":"https://api.github.com/repos/boxingbeetle/webhook-test/branches{/branch}","tags_url":"https://api.github.com/repos/boxingbeetle/webhook-test/tags","blobs_url":"https://api.github.com/repos/boxingbeetle/webhook-test/git/blobs{/sha}","git_tags_url":"https://api.github.com/repos/boxingbeetle/webhook-test/git/tags{/sha}","git_refs_url":"https://api.github.com/repos/boxingbeetle/webhook-test/git/refs{/sha}","trees_url":"https://api.github.com/repos/boxingbeetle/webhook-test/git/trees{/sha}","statuses_url":"https://api.github.com/repos/boxingbeetle/webhook-test/statuses/{sha}","languages_url":"https://api.github.com/repos/boxingbeetle/webhook-test/languages","stargazers_url":"https://api.github.com/repos/boxingbeetle/webhook-test/stargazers","contributors_url":"https://api.github.com/repos/boxingbeetle/webhook-test/contributors","subscribers_url":"https://api.github.com/repos/boxingbeetle/webhook-test/subscribers","subscription_url":"https://api.github.com/repos/boxingbeetle/webhook-test/subscription","commits_url":"https://api.github.com/repos/boxingbeetle/webhook-test/commits{/sha}","git_commits_url":"https://api.github.com/repos/boxingbeetle/webhook-test/git/commits{/sha}","comments_url":"https://api.github.com/repos/boxingbeetle/webhook-test/comments{/number}","issue_comment_url":"https://api.github.com/repos/boxingbeetle/webhook-test/issues/comments{/number}","contents_url":"https://api.github.com/repos/boxingbeetle/webhook-test/contents/{+path}","compare_url":"https://api.github.com/repos/boxingbeetle/webhook-test/compare/{base}...{head}","merges_url":"https://api.github.com/repos/boxingbeetle/webhook-test/merges","archive_url":"https://api.github.com/repos/boxingbeetle/webhook-test/{archive_format}{/ref}","downloads_url":"https://api.github.com/repos/boxingbeetle/webhook-test/downloads","issues_url":"https://api.github.com/repos/boxingbeetle/webhook-test/issues{/number}","pulls_url":"https://api.github.com/repos/boxingbeetle/webhook-test/pulls{/number}","milestones_url":"https://api.github.com/repos/boxingbeetle/webhook-test/milestones{/number}","notifications_url":"https://api.github.com/repos/boxingbeetle/webhook-test/notifications{?since,all,participating}","labels_url":"https://api.github.com/repos/boxingbeetle/webhook-test/labels{/name}","releases_url":"https://api.github.com/repos/boxingbeetle/webhook-test/releases{/id}","deployments_url":"https://api.github.com/repos/boxingbeetle/webhook-test/deployments","created_at":1566891789,"updated_at":"2019-08-27T07:43:12Z","pushed_at":1567609673,"git_url":"git://github.com/boxingbeetle/webhook-test.git","ssh_url":"git@github.com:boxingbeetle/webhook-test.git","clone_url":"https://github.com/boxingbeetle/webhook-test.git","svn_url":"https://github.com/boxingbeetle/webhook-test","homepage":null,"size":0,"stargazers_count":0,"watchers_count":0,"language":null,"has_issues":true,"has_projects":true,"has_downloads":true,"has_wiki":true,"has_pages":false,"forks_count":0,"mirror_url":null,"archived":false,"disabled":false,"open_issues_count":0,"license":null,"forks":0,"open_issues":0,"watchers":0,"default_branch":"master","stargazers":0,"master_branch":"master","organization":"boxingbeetle"},"pusher":{"name":"mthuurne","email":"maarten@treewalker.org"},"organization":{"login":"boxingbeetle","id":46841979,"node_id":"MDEyOk9yZ2FuaXphdGlvbjQ2ODQxOTc5","url":"https://api.github.com/orgs/boxingbeetle","repos_url":"https://api.github.com/orgs/boxingbeetle/repos","events_url":"https://api.github.com/orgs/boxingbeetle/events","hooks_url":"https://api.github.com/orgs/boxingbeetle/hooks","issues_url":"https://api.github.com/orgs/boxingbeetle/issues","members_url":"https://api.github.com/orgs/boxingbeetle/members{/member}","public_members_url":"https://api.github.com/orgs/boxingbeetle/public_members{/member}","avatar_url":"https://avatars0.githubusercontent.com/u/46841979?v=4","description":"Toolchain Solutions"},"sender":{"login":"mthuurne","id":246676,"node_id":"MDQ6VXNlcjI0NjY3Ng==","avatar_url":"https://avatars3.githubusercontent.com/u/246676?v=4","gravatar_id":"","url":"https://api.github.com/users/mthuurne","html_url":"https://github.com/mthuurne","followers_url":"https://api.github.com/users/mthuurne/followers","following_url":"https://api.github.com/users/mthuurne/following{/other_user}","gists_url":"https://api.github.com/users/mthuurne/gists{/gist_id}","starred_url":"https://api.github.com/users/mthuurne/starred{/owner}{/repo}","subscriptions_url":"https://api.github.com/users/mthuurne/subscriptions","organizations_url":"https://api.github.com/users/mthuurne/orgs","repos_url":"https://api.github.com/users/mthuurne/repos","events_url":"https://api.github.com/users/mthuurne/events{/privacy}","received_events_url":"https://api.github.com/users/mthuurne/received_events","type":"User","site_admin":false}}
'''.strip()

if __name__ == '__main__':
    unittest.main()
